"""Server-side Markdown of the newer Workspace blocks (shares, exports)."""

from openjarvis.workspace.markdown import blocks_markdown


def test_equation_bookmark_and_index_export():
    blocks = (
        b
        for b in [
            {"type": "toc", "text": ""},
            {"type": "h1", "text": "Energía"},
            {"type": "equation", "text": "E = mc^2"},
            {"type": "h2", "text": "Fuentes"},
            {"type": "bookmark", "text": "https://example.com/a"},
            "basura",
        ]
    )  # a generator: the index needs to read the blocks twice
    md = blocks_markdown(blocks)
    assert "- Energía\n  - Fuentes" in md
    assert "$$\nE = mc^2\n$$" in md
    assert "<https://example.com/a>" in md
