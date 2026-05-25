"""Tests for scripts/_workday_browser.py (the headed Workday pull helper).

A real Playwright browser can't run in CI, so the browser-driving paths are
exercised against lightweight fakes. These pin the acceptance criteria:

  * the module imports
  * launch / wait_for_login / export_to_excel have the agreed signatures
  * first run creates the profile directory (and uses a headed, downloads-on,
    persistent context)
  * export_to_excel runs the navigate callback and returns the downloaded bytes
  * wait_for_login blocks-then-returns on success and raises on timeout
  * the module never handles SCU credentials
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("playwright.sync_api")  # skip module if Playwright absent

from scripts import _workday_browser as wb  # noqa: E402


# ── Signatures (the two pull scripts depend on these) ────────────────────────


def test_public_api_exported():
    assert wb.__all__ == ["launch", "wait_for_login", "export_to_excel"]
    for name in wb.__all__:
        assert callable(getattr(wb, name))


def test_launch_signature():
    params = inspect.signature(wb.launch).parameters
    assert list(params) == ["profile_dir"]


def test_wait_for_login_signature():
    sig = inspect.signature(wb.wait_for_login)
    assert list(sig.parameters) == ["page", "timeout_s"]
    timeout_s = sig.parameters["timeout_s"]
    assert timeout_s.kind is inspect.Parameter.KEYWORD_ONLY
    assert timeout_s.default == 300


def test_export_to_excel_signature():
    assert list(inspect.signature(wb.export_to_excel).parameters) == ["page", "navigate"]


# ── launch: profile dir + persistent-context options ─────────────────────────


class _FakeLaunchPage:
    def __init__(self, url=wb.WORKDAY_HOME):
        self.url = url
        self.goto_calls: list[str] = []

    def goto(self, url, **_kw):
        self.goto_calls.append(url)


class _FakeContext:
    def __init__(self, launch_kwargs):
        self.launch_kwargs = launch_kwargs
        self.pages = [_FakeLaunchPage()]


class _FakeChromium:
    def launch_persistent_context(self, **kwargs):
        return _FakeContext(kwargs)


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeChromium()
        self.stopped = False

    def stop(self):
        self.stopped = True


def _patch_playwright(monkeypatch):
    pw = _FakePlaywright()
    monkeypatch.setattr(wb, "sync_playwright", lambda: SimpleNamespace(start=lambda: pw))
    return pw


def test_launch_creates_profile_dir_first_run(tmp_path, monkeypatch):
    _patch_playwright(monkeypatch)
    profile = tmp_path / "nested" / ".workday_profile"
    assert not profile.exists()

    context, page = wb.launch(profile)

    assert profile.is_dir()  # created on first run
    assert context.launch_kwargs["user_data_dir"] == str(profile)
    assert page.goto_calls == [wb.WORKDAY_HOME]


def test_launch_is_headed_with_downloads(tmp_path, monkeypatch):
    _patch_playwright(monkeypatch)
    context, _page = wb.launch(tmp_path / "profile")
    assert context.launch_kwargs["headless"] is False  # never headless
    assert context.launch_kwargs["accept_downloads"] is True


def test_launch_keeps_driver_reference(tmp_path, monkeypatch):
    """The Playwright driver must stay referenced so it isn't GC'd mid-session."""
    pw = _patch_playwright(monkeypatch)
    context, _page = wb.launch(tmp_path / "profile")
    assert context._playwright is pw


# ── wait_for_login ───────────────────────────────────────────────────────────


def _fake_page(url="", pages=None):
    page = SimpleNamespace()
    page.url = url
    page.context = SimpleNamespace(pages=pages if pages is not None else [page])
    return page


def test_wait_for_login_returns_when_logged_in(monkeypatch, capsys):
    monkeypatch.setattr(wb.time, "sleep", lambda _s: pytest.fail("should not sleep"))
    page = _fake_page(url="https://www.myworkday.com/scu/d/home.htmld")
    assert wb.wait_for_login(page) is None
    assert "log in" in capsys.readouterr().out.lower()


def test_wait_for_login_times_out(monkeypatch):
    monkeypatch.setattr(wb.time, "sleep", lambda _s: None)
    stuck = _fake_page(url="https://login.scu.edu/sso")
    with pytest.raises(TimeoutError):
        wb.wait_for_login(stuck, timeout_s=0)


def test_wait_for_login_detects_workday_in_secondary_tab(monkeypatch):
    monkeypatch.setattr(wb.time, "sleep", lambda _s: pytest.fail("should not sleep"))
    sso = _fake_page(url="https://login.scu.edu/sso")
    workday = _fake_page(url="https://www.myworkday.com/scu/d/home.htmld")
    sso.context.pages = [sso, workday]
    assert wb.wait_for_login(sso) is None


# ── export_to_excel ──────────────────────────────────────────────────────────


class _FakeDownload:
    def __init__(self, path):
        self._path = path

    def path(self):
        return self._path


class _DownloadCtx:
    def __init__(self, download):
        self._download = download

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    @property
    def value(self):
        return self._download


class _FakeExportPage:
    """Fake page where the first direct selector yields a download."""

    def __init__(self, download_path):
        self.url = "https://www.myworkday.com/scu/d/task/X.htmld"
        self._download_path = download_path

    def wait_for_load_state(self, *_a, **_k):
        pass

    def wait_for_timeout(self, *_a, **_k):
        pass

    def wait_for_selector(self, *_a, **_k):
        return None  # selector "found"

    def expect_download(self, *_a, **_k):
        return _DownloadCtx(_FakeDownload(self._download_path))

    def click(self, *_a, **_k):
        pass


def test_export_to_excel_runs_navigate_and_returns_bytes(tmp_path):
    xlsx = tmp_path / "academic_progress.xlsx"
    xlsx.write_bytes(b"PK\x03\x04 fake xlsx bytes")

    page = _FakeExportPage(str(xlsx))
    visited: list[object] = []

    data = wb.export_to_excel(page, lambda pg: visited.append(pg))

    assert data == b"PK\x03\x04 fake xlsx bytes"
    assert visited == [page]  # navigate callback ran with the page


class _NoExportPage:
    """Fake page where no export control is ever found."""

    def __init__(self):
        self.url = "https://www.myworkday.com/scu/d/task/X.htmld"
        self.screenshot_calls = 0

    def wait_for_load_state(self, *_a, **_k):
        pass

    def wait_for_timeout(self, *_a, **_k):
        pass

    def wait_for_selector(self, *_a, **_k):
        raise wb.PWTimeout("not found")

    def click(self, *_a, **_k):
        raise wb.PWTimeout("not found")

    def keyboard_press(self, *_a, **_k):
        pass

    @property
    def keyboard(self):
        return SimpleNamespace(press=lambda *_a, **_k: None)

    def evaluate(self, *_a, **_k):
        return []

    def screenshot(self, *_a, **_k):
        self.screenshot_calls += 1


def test_export_to_excel_raises_when_no_control_found():
    page = _NoExportPage()
    with pytest.raises(RuntimeError, match="Export to Excel"):
        wb.export_to_excel(page, lambda _pg: None)
    assert page.screenshot_calls == 1  # debug screenshot attempted


# ── Safety: never handles credentials ────────────────────────────────────────


def test_module_never_handles_credentials():
    """Acceptance constraint: zero credential handling anywhere in the module.

    Checked at the AST level (not prose) so the docstring's "never stores
    passwords" copy doesn't trip it. The module must never prompt for secrets
    (``input`` / ``getpass``) nor type into form fields (``.fill`` — the human
    types their own credentials).
    """
    tree = ast.parse(Path(wb.__file__).read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "getpass" not in imported

    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                called.add(fn.attr)
    for forbidden in ("input", "getpass", "fill"):
        assert forbidden not in called, f"credential-handling call {forbidden!r} present"
