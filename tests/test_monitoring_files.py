import pytest

from core.monitoring.dashboard import render_document, render_files
from core.monitoring.files import PAGE_SIZE, list_documents, read_document


def test_file_browser_reads_only_allowlisted_markdown_and_escapes_html(tmp_path):
    root = tmp_path / "memory/persistent/threads"
    root.mkdir(parents=True)
    (root / "thread-1.md").write_text("# Title\n<script>alert(1)</script>\n")
    (root / "hidden.json").write_text("secret")
    (root / "external.md").symlink_to(tmp_path / "outside.md")
    (tmp_path / "outside.md").write_text("secret outside")

    assert list_documents(tmp_path, "threads") == ["thread-1.md"]
    content = read_document(tmp_path, "threads", "thread-1.md")
    page = render_document("threads", "thread-1.md", content)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "thread-1.md" in render_files(tmp_path, "threads")
    assert "external.md" not in render_files(tmp_path, "threads")
    with pytest.raises(ValueError):
        read_document(tmp_path, "threads", "../outside.md")
    with pytest.raises(ValueError):
        read_document(tmp_path, "threads", "external.md")
    with pytest.raises(ValueError):
        list_documents(tmp_path, "unknown")


def test_pagination_and_preview_limit(tmp_path):
    root = tmp_path / "memory/working"
    root.mkdir(parents=True)
    for number in range(PAGE_SIZE + 1):
        (root / f"info-{number:03}.md").write_text("x")
    assert len(list_documents(tmp_path, "working")) == PAGE_SIZE
    assert list_documents(tmp_path, "working", PAGE_SIZE) == ["info-100.md"]
    with pytest.raises(ValueError, match="negative"):
        list_documents(tmp_path, "working", -1)
    (root / "large.md").write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="preview limit"):
        read_document(tmp_path, "working", "large.md")
