import json

import pytest

from openjarvis.plugins.claude_format import ClaudePluginError, ClaudePlugins


@pytest.mark.parametrize(
    "name", ["../../keep", "../..//keep", "/tmp", ".", "..", "x\\..\\keep", "unknown"]
)
def test_remove_preserves_unregistered_and_outside_folders(tmp_path, name):
    outside = tmp_path / "keep"
    outside.mkdir()
    (outside / "important.txt").write_text("keep")
    plugins = ClaudePlugins(tmp_path / "config")
    plugins.markets_dir.mkdir(parents=True)
    with pytest.raises(ClaudePluginError):
        plugins.remove_marketplace(name)
    assert (outside / "important.txt").read_text() == "keep"


def test_registered_symlink_preserves_outside_folder(tmp_path):
    outside = tmp_path / "keep"
    outside.mkdir()
    plugins = ClaudePlugins(tmp_path / "config")
    plugins.markets_dir.mkdir(parents=True)
    (plugins.markets_dir / "linked").symlink_to(outside, target_is_directory=True)
    plugins._save({"marketplaces": {"linked": {}}, "installed": {}})
    with pytest.raises(ClaudePluginError):
        plugins.remove_marketplace("linked")
    assert outside.exists() and "linked" in plugins._state()["marketplaces"]


def test_registered_marketplace_can_be_removed(tmp_path):
    plugins = ClaudePlugins(tmp_path)
    (plugins.markets_dir / "valid").mkdir(parents=True)
    plugins._save({"marketplaces": {"valid": {}}, "installed": {}})
    plugins.remove_marketplace("valid")
    assert not (plugins.markets_dir / "valid").exists()


def test_homonymous_plugins_have_independent_skills_and_report_connector_failures(
    tmp_path,
):
    from openjarvis.mcp.hub import ConnectorHub

    plugins = ClaudePlugins(
        tmp_path / "home", hub=ConnectorHub(tmp_path / "connectors")
    )
    for name in ("one", "two"):
        market = tmp_path / name
        (market / ".claude-plugin").mkdir(parents=True)
        (market / "demo/skills/example").mkdir(parents=True)
        (market / "demo/skills/example/SKILL.md").write_text(f"Skill from {name}")
        (market / "demo/.mcp.json").write_text(
            json.dumps({"mcpServers": {"bad": {"url": "file:///bad"}}})
        )
        (market / ".claude-plugin/marketplace.json").write_text(
            json.dumps(
                {"name": name, "plugins": [{"name": "demo", "source": "./demo"}]}
            )
        )
        plugins.add_marketplace(str(market))
    with pytest.raises(ClaudePluginError, match="nombre@marketplace"):
        plugins.install("demo")
    one = plugins.install("demo@one")
    two = plugins.install("demo@two")
    assert one["skill_root"] != two["skill_root"]
    assert one["connector_errors"] and two["connector_errors"]
    from openjarvis.skills.loader import discover_skills

    loaded = discover_skills(plugins.skills_dir)
    assert len(loaded) == 2 and loaded[0].name != loaded[1].name
    assert all(len("skill_" + skill.name) <= 64 for skill in loaded)
    plugins.remove("demo@one")
    assert (
        plugins.skills_dir / two["skill_root"] / "example/SKILL.md"
    ).read_text() == "Skill from two"
