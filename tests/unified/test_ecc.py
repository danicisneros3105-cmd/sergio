"""ECC library: sparse download commands, index, search, safe reading, tool."""

import subprocess

import pytest

from openjarvis.tools.skill_guide_tool import SkillGuideTool
from openjarvis.unified import ecc


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "ecc"
    _write(
        root / "skills/deep-research/SKILL.md",
        "---\nname: deep-research\ndescription: Produce cited research reports from "
        "multiple web sources.\nmetadata:\n  origin: ECC\n---\n# Deep Research\nPlan, "
        "search, synthesize.",
    )
    _write(root / "skills/deep-research/references/checklist.md", "1. Ask why")
    _write(
        root / "skills/article-writing/SKILL.md",
        "---\nname: article-writing\ndescription: Write articles and blog posts in a "
        "distinctive voice.\n---\nWrite well. " + "x" * 9000,
    )
    _write(
        root / "agents/chief-of-staff.md",
        "---\nname: chief-of-staff\ndescription: Triage email and research "
        "follow-ups.\ntools: Read\n---\nBe a chief of staff.",
    )
    _write(root / "agents/no-frontmatter.md", "Just text")
    _write(tmp_path / "secret.txt", "top secret")
    return ecc.Library(root)


def test_index_reads_skills_and_agents(lib):
    names = {(g.name, g.kind) for g in lib.guides()}
    assert ("deep-research", "skill") in names
    assert ("chief-of-staff", "agent") in names
    assert ("no-frontmatter", "agent") in names


def test_search_ranks_name_matches_first_and_skills_over_agents(lib):
    hits = lib.search("deep research")
    assert [g.name for g in hits][:2] == ["deep-research", "chief-of-staff"]
    assert lib.search("zz") == [] and lib.search("quantum") == []


def test_read_strips_frontmatter_truncates_and_lists_extras(lib):
    body = lib.read("deep-research")
    assert body.startswith("# Deep Research") and "origin" not in body
    assert lib.extra_files(lib.find("deep-research")) == ["references/checklist.md"]
    assert lib.read("deep-research", "references/checklist.md") == "1. Ask why"
    long = lib.read("article-writing")
    assert len(long) < 8100 and long.endswith("longer ...]")


@pytest.mark.parametrize("bad", ["../../secret.txt", "/etc/passwd", "SKILL.md/../.."])
def test_read_cannot_escape_the_skill_folder(lib, bad):
    with pytest.raises(ecc.ECCError):
        lib.read("deep-research", bad)


def test_tool_search_then_read(lib):
    tool = SkillGuideTool(library=lib)
    found = tool.execute(query="research reports")
    assert found.success and "- deep-research [skill]" in found.content
    read = tool.execute(name="deep-research")
    assert read.success and "Plan, search, synthesize." in read.content
    assert "Extra files: references/checklist.md" in read.content
    assert "own tools" in read.content  # adapt-to-Sergio note
    assert not tool.execute(name="nope").success
    assert not tool.execute().success


def test_tool_when_not_downloaded(tmp_path):
    result = SkillGuideTool(library=ecc.Library(tmp_path / "missing")).execute(
        query="x"
    )
    assert not result.success and "sergio ecc actualizar" in result.content


def test_sync_first_time_is_sparse_shallow_clone(tmp_path):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="abc1234\n", stderr="")

    assert ecc.sync(tmp_path / "ecc", runner) == "abc1234"
    clone = calls[0]
    assert clone[:2] == ["git", "clone"] and "--sparse" in clone and "--depth" in clone
    assert ecc.ECC_REPO in clone
    assert calls[1][-3:] == ["set", "skills", "agents"]


def test_sync_update_and_failure(tmp_path):
    (tmp_path / "ecc" / ".git").mkdir(parents=True)
    calls = []

    def ok(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="def5678", stderr="")

    ecc.sync(tmp_path / "ecc", ok)
    assert calls[0][3:] == ["fetch", "--depth", "1", "origin"]
    assert calls[1][3:] == ["reset", "--hard", "FETCH_HEAD"]

    def fail(cmd):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="network down")

    with pytest.raises(ecc.ECCError, match="network down"):
        ecc.sync(tmp_path / "ecc", fail)


def test_enable_tool_in_config(tmp_path):
    from openjarvis.cli.ecc_cmd import enable_tool

    cfg = tmp_path / "config.toml"
    cfg.write_text('[tools]\nenabled = ["think"]\n')
    assert enable_tool(cfg) is True
    assert 'enabled = ["think", "skill_guide"]' in cfg.read_text()
    assert enable_tool(cfg) is False
    cfg.write_text("[agent]\nmax_turns = 10\n")
    assert enable_tool(cfg) is False  # no explicit list: server defaults apply
