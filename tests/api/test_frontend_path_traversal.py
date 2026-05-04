"""Regression: SPA static fallback must never escape `_FRONTEND_DIST`."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api import main as main_module


@pytest.fixture
def frontend_root(tmp_path: Path) -> Path:
    """Minimal fake frontend tree."""
    root = tmp_path / "frontend_dist"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    sub = root / "assets"
    sub.mkdir()
    (sub / "ok.txt").write_text("inside", encoding="utf-8")
    return root


@pytest.mark.parametrize(
    ("path", "expect_name"),
    [
        ("index.html", "index.html"),
        ("assets/ok.txt", "ok.txt"),
    ],
)
def test_safe_frontend_allows_inside_files(
    frontend_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    expect_name: str,
) -> None:
    monkeypatch.setattr(main_module, "_FRONTEND_DIST", frontend_root)
    resolved = main_module._safe_frontend_file(path)
    assert resolved is not None
    assert resolved.name == expect_name


@pytest.mark.parametrize(
    "evil",
    [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
        "/etc/passwd",
    ],
)
def test_safe_frontend_blocks_escape(
    frontend_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    evil: str,
) -> None:
    monkeypatch.setattr(main_module, "_FRONTEND_DIST", frontend_root)
    assert main_module._safe_frontend_file(evil) is None


def test_safe_frontend_unknown_file_returns_none(
    frontend_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "_FRONTEND_DIST", frontend_root)
    assert main_module._safe_frontend_file("no-such-path.png") is None
