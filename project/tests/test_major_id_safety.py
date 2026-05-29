"""Security: major_id must not escape data/majors via path traversal."""

from __future__ import annotations

from pathlib import Path

from utils.major_requirements import load_major_markdown, resolve_major_id


def test_load_major_markdown_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    """student_major_id like ../memory/<uid> must not read other users' memory files."""
    majors_dir = tmp_path / "majors"
    majors_dir.mkdir()
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    secret = memory_dir / "1.md"
    secret.write_text("SECRET_USER_MEMORY", encoding="utf-8")

    monkeypatch.setattr(
        "utils.major_requirements._MAJORS_DIR",
        majors_dir,
    )

    leaked = load_major_markdown("../memory/1")
    assert leaked is None


def test_resolve_major_id_rejects_path_traversal() -> None:
    assert resolve_major_id(confirmed_major_id="../memory/1") is None


def test_load_major_markdown_reads_valid_major(tmp_path, monkeypatch) -> None:
    majors_dir = tmp_path / "majors"
    majors_dir.mkdir()
    (majors_dir / "csen.md").write_text("# CSEN bulletin", encoding="utf-8")

    monkeypatch.setattr(
        "utils.major_requirements._MAJORS_DIR",
        majors_dir,
    )

    assert load_major_markdown("csen") == "# CSEN bulletin"
