"""Anatomy ships with its real kit and is available internally, not as a menu."""

from pathlib import Path

from openjarvis.core.events import EventBus
from openjarvis.skills.design_policy import ANATOMY_POLICY
from openjarvis.skills.manager import SkillManager


def test_anatomy_internal_discovery_and_instruction_execution(tmp_path):
    manager = SkillManager(EventBus())
    manager.discover([tmp_path])
    skill = manager.resolve("anatomy")
    assert not skill.user_invocable
    assert "anatomy" not in manager.skill_names()
    assert "anatomy" in manager.skill_names(include_internal=True)
    tool = next(
        t
        for t in manager.get_skill_tools(include_internal=True)
        if t.spec.name == "skill_anatomy"
    )
    result = tool.execute()
    assert result.success and "references/upstream-skill.md" in result.content
    root = Path(__file__).parents[2] / "src/openjarvis/skills/bundled/anatomy"
    assert (root / "kit/iso-kit.ts").is_file()
    assert (root / "examples/desk-computer/build.mjs").is_file()
    assert "MIT License" in (root / "LICENSE").read_text()
    assert "Anatomy" in ANATOMY_POLICY
