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
