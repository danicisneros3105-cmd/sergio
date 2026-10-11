"""SkillImporter — install ResolvedSkill instances into ~/.openjarvis/skills/.

Steps performed by ``import_skill``:

1. Parse the source SKILL.md through SkillParser (strict + tolerant).
2. Reject symlinks in directories that would be copied into the install.
3. Translate tool references in the markdown body via ToolTranslator.
4. Decide on scripts (default-skip; opt-in via with_scripts=True).
5. Write to disk at <target_root>/<source>/<name>/:
   - translated SKILL.md
   - references/, assets/, templates/ (always copied)
   - scripts/ (only if approved)
   - .source metadata file
6. Return ImportResult with status, warnings, translated/missing tools.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import yaml

from openjarvis.core.paths import get_config_dir
from openjarvis.skills.audit import audit_resources, audit_text, read_skill_text
from openjarvis.skills.parser import SkillParser
from openjarvis.skills.security import (
    TrustTier,
    classify_trust_tier,
    has_dangerous_capabilities,
)
from openjarvis.skills.sources.base import ResolvedSkill
from openjarvis.skills.tool_translator import ToolTranslator

# Subdirectories of a skill that are always copied (never gated by --with-scripts)
COPIED_SUBDIRS = ("references", "assets", "templates")


@dataclass(slots=True)
class ImportResult:
    """Result of importing a single skill."""

    success: bool = True
    skipped: bool = False
    target_path: Path | None = None
    translated_tools: List[str] = field(default_factory=list)
    untranslated_tools: List[str] = field(default_factory=list)
    scripts_imported: bool = False
    warnings: List[str] = field(default_factory=list)
    trust_tier: TrustTier = TrustTier.UNREVIEWED
    dangerous_capabilities: List[str] = field(default_factory=list)
    requires_confirmation: bool = False


class SkillImporter:
    """Install resolved skills into the user skills directory."""

    def __init__(
        self,
        parser: SkillParser,
        tool_translator: ToolTranslator,
        target_root: Path | None = None,
    ) -> None:
        self._parser = parser
        self._translator = tool_translator
        if target_root is None:
            target_root = get_config_dir() / "skills"
        self._target_root = Path(target_root)

    def import_skill(
        self,
        resolved: ResolvedSkill,
        *,
        with_scripts: bool = False,
        force: bool = False,
        confirm_dangerous: bool = False,
    ) -> ImportResult:
        """Install *resolved* into ``<target_root>/<source>/<name>/``.

        Returns an :class:`ImportResult` with status, paths, translated
        tools, untranslated tools, and warnings.
        """
        result = ImportResult()
        if any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", part)
            for part in (resolved.source, resolved.name)
        ):
            result.success = False
            result.warnings.append("Refusing invalid skill source/name path components")
            return result
        target_dir = self._target_root / resolved.source / resolved.name
        if target_dir.is_symlink() or target_dir.parent.is_symlink():
            result.success = False
            result.warnings.append("Refusing a symlinked skill destination")
            return result
        if not target_dir.resolve().is_relative_to(self._target_root.resolve()):
            result.success = False
            result.warnings.append(
                "Refusing a skill destination outside the install root"
            )
            return result
        result.target_path = target_dir

        # Skip if already installed and force is False
        if target_dir.exists() and not force:
            result.skipped = True
            result.warnings.append(
                f"Skill already installed at {target_dir} (use force=True to overwrite)"
            )
            return result

        # 1. Parse source SKILL.md
        source_md = resolved.path / "SKILL.md"
        if not source_md.exists():
            source_md = resolved.path / "skill.md"
            if not source_md.exists():
                result.success = False
                result.warnings.append(f"No SKILL.md found in {resolved.path}")
                return result

        try:
            if resolved.path.is_symlink():
                raise ValueError("Refusing a symlinked skill source")
            raw = read_skill_text(source_md)
            report = audit_text(raw)
            if report.findings:
                raise ValueError(
                    "Static skill audit requires correction: "
                    + "; ".join(report.findings)
                )
            frontmatter, body = self._read_skill_md(source_md, raw=raw)
            manifest = self._parser.parse_frontmatter(
                frontmatter, markdown_content=body
            )
        except Exception as exc:
            result.success = False
            result.warnings.append(f"Parse error: {exc}")
            return result

        # 1a. Classify trust and check for dangerous capabilities *before*
        # writing anything to disk. Everything the importer handles comes from
        # an external source (github/hermes/openclaw), so the BUNDLED and
        # WORKSPACE tiers never apply here, and no resolver verifies index
        # membership yet — a signature alone still classifies as UNREVIEWED.
        # Community skills get no special treatment just because they came
        # from a named source.
        result.trust_tier = classify_trust_tier(
            has_signature=bool(manifest.signature),
        )
        result.dangerous_capabilities = has_dangerous_capabilities(manifest)

        if result.dangerous_capabilities and result.trust_tier == TrustTier.UNREVIEWED:
            result.requires_confirmation = True
            if not confirm_dangerous:
                result.success = False
                result.warnings.append(
                    "Refusing to install: this unreviewed skill requests "
                    f"dangerous capabilities {result.dangerous_capabilities}. "
                    "Re-run with confirm_dangerous=True (or `--yes-dangerous` "
                    "on the CLI) only if you trust the source and have "
                    "reviewed what it does."
                )
                return result
            result.warnings.append(
                "Installed with dangerous capabilities "
                f"{result.dangerous_capabilities} — confirmed by caller. "
                "This skill can run shell commands, open network listeners, "
                "and/or write to the filesystem."
            )

        # 2. Validate copied resources and translate tool references
        copied_subdirs = list(COPIED_SUBDIRS)
        if with_scripts:
            copied_subdirs.append("scripts")
        try:
            findings = audit_resources(resolved.path, copied_subdirs)
            if findings:
                raise ValueError(
                    "Static resource audit requires correction: " + "; ".join(findings)
                )
        except (ValueError, OSError, UnicodeError) as exc:
            result.success = False
            result.warnings.append(str(exc))
            return result

        translated_body, untranslated = self._translator.translate_markdown(body)
        result.untranslated_tools = untranslated
        # Compute the list of translations actually applied
        applied: List[str] = []
        for ext, internal in self._translator._table.items():
            if ext in body and ext not in translated_body:
                applied.append(f"{ext}->{internal}")
        result.translated_tools = applied

        # Build and audit a private staging copy before replacing an install.
        # Copy links as links, so a link introduced during copying is rejected
        # by the second audit rather than dereferenced into another file.
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=".sergio-import-", dir=target_dir.parent)
        )
        fresh, previous = staging / "new", staging / "previous"
        cleanup = True
        try:
            fresh.mkdir()
            new_md = self._render_skill_md(frontmatter, translated_body)
            (fresh / "SKILL.md").write_text(new_md, encoding="utf-8")
            for subdir in copied_subdirs:
                src_sub = resolved.path / subdir
                if src_sub.exists():
                    shutil.copytree(src_sub, fresh / subdir, symlinks=True)
            findings = audit_resources(fresh, copied_subdirs)
            if findings:
                raise ValueError(
                    "Static staged-resource audit requires correction: "
                    + "; ".join(findings)
                )
            result.scripts_imported = with_scripts and (fresh / "scripts").exists()
            if (resolved.path / "scripts").exists() and not with_scripts:
                result.warnings.append(
                    "Skipped scripts/ directory (use with_scripts=True to import)"
                )
            self._write_source_metadata(fresh, resolved, result)
            if target_dir.is_symlink() or target_dir.parent.is_symlink():
                raise ValueError("Refusing a symlinked skill destination")
            if target_dir.exists():
                if not force:
                    result.skipped = True
                    return result
                target_dir.rename(previous)
            fresh.rename(target_dir)
        except (OSError, ValueError, UnicodeError) as exc:
            result.success = False
            result.scripts_imported = False
            result.warnings.append(f"Skill import failed: {exc}")
            if previous.exists() and not target_dir.exists():
                try:
                    previous.rename(target_dir)
                except OSError:
                    cleanup = False
                    result.warnings.append(f"Previous install preserved at {previous}")
        finally:
            if cleanup:
                shutil.rmtree(staging, ignore_errors=True)

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_symlinks(root: Path) -> list[Path]:
        """Return symlinks below *root* without following them."""
        if not root.exists() and not root.is_symlink():
            return []
        if root.is_symlink():
            return [root]
        return [path for path in root.rglob("*") if path.is_symlink()]

    def _read_skill_md(self, path: Path, *, raw: str | None = None) -> tuple[dict, str]:
        """Parse a SKILL.md file into (frontmatter dict, markdown body)."""
        raw = read_skill_text(path) if raw is None else raw
        if not raw.startswith("---"):
            return {}, raw
        rest = raw[3:].lstrip("\n")
        end = rest.find("\n---")
        if end == -1:
            return {}, raw
        fm_text = rest[:end]
        body = rest[end + 4 :].lstrip("\n")
        try:
            fm = yaml.safe_load(fm_text)
            if not isinstance(fm, dict):
                fm = {}
        except yaml.YAMLError:
            fm = {}
        return fm, body

    def _render_skill_md(self, frontmatter: dict, body: str) -> str:
        """Re-serialize a SKILL.md file from frontmatter dict + body."""
        fm_text = yaml.safe_dump(frontmatter, sort_keys=False, default_flow_style=False)
        return f"---\n{fm_text}---\n\n{body}"

    def _write_source_metadata(
        self,
        target_dir: Path,
        resolved: ResolvedSkill,
        result: ImportResult,
    ) -> None:
        """Write the .source TOML provenance file."""
        installed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        translated_str = ", ".join(f'"{t}"' for t in result.translated_tools)
        missing_str = ", ".join(f'"{t}"' for t in result.untranslated_tools)
        scripts_lower = "true" if result.scripts_imported else "false"
        dangerous_str = ", ".join(f'"{c}"' for c in result.dangerous_capabilities)

        content = (
            f'source = "{resolved.source}:{resolved.name}"\n'
            f'commit = "{resolved.commit}"\n'
            f'category = "{resolved.category}"\n'
            f'installed_at = "{installed_at}"\n'
            f"translated_tools = [{translated_str}]\n"
            f"missing_tools = [{missing_str}]\n"
            f"scripts_imported = {scripts_lower}\n"
            f'trust_tier = "{result.trust_tier.value}"\n'
            f"dangerous_capabilities = [{dangerous_str}]\n"
        )
        (target_dir / ".source").write_text(content, encoding="utf-8")


__all__ = ["ImportResult", "SkillImporter"]
