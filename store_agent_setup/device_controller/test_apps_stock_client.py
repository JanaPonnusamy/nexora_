"""StockClientApp discovery/update tests (NEXORA MEDIQ Phase 5.1).

PRODUCT_NAME became load-bearing for the rebrand's fleet-safety story in
Phase 5 (ef4192c) -- apps.py had zero test coverage before this file. These
tests exercise exe()/_candidate_dirs()/update() against real temporary
directories (never the live registry or a real install), proving the
new-name, legacy-name, and dual-install-coexistence behavior the Phase 5.1
authorization asked to be tested rather than assumed.

Run: backend/.venv/Scripts/python.exe -m pytest store_agent_setup/device_controller/test_apps_stock_client.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from store_agent_setup.device_controller import apps as apps_mod
from store_agent_setup.device_controller.apps import StockClientApp


NEW_NAME = apps_mod.PRODUCT_NAME  # "NEXORA MEDIQ"
LEGACY_NAME = apps_mod._LEGACY_PRODUCT_NAMES[0]  # "Axythic Supplier Stock"


@pytest.fixture(autouse=True)
def _never_touch_real_registry(monkeypatch):
    """CRITICAL isolation guard: this dev machine has a real, locally
    installed Axythic Supplier Stock registered in HKLM\\...\\Uninstall
    (from earlier npm run dist / local install work on this project), and
    _candidate_dirs() opens the REAL `winreg` module by default. Every test
    in this file must be isolated from whatever happens to be installed on
    the machine running them, or results become machine-dependent and could
    silently read real local registry state. Applied to every test
    automatically; test_registry_* tests additionally call _patch_winreg
    with their own fake subkeys, which overrides this default (empty) one."""
    _patch_winreg(monkeypatch, [])


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """A fake ProgramFiles + LOCALAPPDATA root, isolated per test."""
    program_files = tmp_path / "Program Files"
    localappdata = tmp_path / "LocalAppData"
    program_files.mkdir()
    localappdata.mkdir()
    monkeypatch.setenv("ProgramFiles", str(program_files))
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.setattr(apps_mod.host, "user_localappdata", lambda: localappdata)
    return {"program_files": program_files, "localappdata": localappdata}


def _write_exe_with_version(exe_path: Path, version: str, asar_unpacked=False):
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_bytes(b"fake-pe")
    rel = "resources/app.asar.unpacked" if asar_unpacked else "resources/app"
    pkg_dir = exe_path.parent / rel
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. New NEXORA MEDIQ installation discovered successfully.
# ---------------------------------------------------------------------------

def test_discovers_new_product_name_install_in_programfiles(fake_env):
    exe_path = fake_env["program_files"] / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    app = StockClientApp()
    found = app.exe()

    assert found == exe_path
    assert app.installed() is True
    assert app.version() == "0.1.72"


def test_discovers_new_product_name_install_in_localappdata(fake_env):
    exe_path = fake_env["localappdata"] / "Programs" / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    app = StockClientApp()
    assert app.exe() == exe_path


# ---------------------------------------------------------------------------
# 2. Legacy Axythic installation discovered successfully.
# ---------------------------------------------------------------------------

def test_discovers_legacy_product_name_install(fake_env):
    exe_path = fake_env["program_files"] / LEGACY_NAME / f"{LEGACY_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.71")

    app = StockClientApp()
    found = app.exe()

    assert found == exe_path
    assert app.version() == "0.1.71"


def test_discovers_legacy_slug_install_in_localappdata(fake_env):
    """Pre-rebrand electron-builder slugified LOCALAPPDATA folder name."""
    exe_path = fake_env["localappdata"] / "Programs" / "axythic-supplier-stock" / f"{LEGACY_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.60")

    app = StockClientApp()
    assert app.exe() == exe_path


# ---------------------------------------------------------------------------
# 3 & 4. Registry DisplayName matches new / legacy product name.
# ---------------------------------------------------------------------------

class _FakeWinregSub:
    def __init__(self, display_name, install_location=""):
        self._values = {"DisplayName": display_name, "InstallLocation": install_location}

    def query(self, name):
        if name not in self._values or not self._values[name]:
            raise OSError(f"no value {name}")
        return self._values[name]


def _patch_winreg(monkeypatch, subkeys):
    """subkeys: list of _FakeWinregSub. Patches the `winreg` module used
    inside apps._candidate_dirs() (imported locally there) so no real
    registry key is ever opened."""
    import types

    fake_winreg = types.SimpleNamespace()
    fake_winreg.HKEY_LOCAL_MACHINE = object()
    fake_winreg.KEY_WOW64_64KEY = 1
    fake_winreg.KEY_WOW64_32KEY = 2
    fake_winreg.KEY_READ = 4

    class _RootKey:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

    def _open_key(hive, path, flags, access):
        if access & 1:  # only the 64-bit view call returns entries, avoids double-count
            return _RootKey()
        return _RootKey()

    def _query_info_key(root):
        return (len(subkeys), 0, 0)

    def _enum_key(root, i):
        return str(i)

    _open_key_for_sub_calls = {"n": 0}

    def _open_key_dispatch(hive_or_root, path_or_name, *rest):
        # First form: OpenKey(hive, base_path, 0, flags) -> root uninstall key
        # Second form: OpenKey(root, enum_name) -> one subkey
        if isinstance(path_or_name, str) and path_or_name.isdigit():
            idx = int(path_or_name)
            sub = subkeys[idx]
            ctx = _RootKey()
            ctx._sub = sub
            return ctx
        return _RootKey()

    def _query_value_ex(key_ctx, name):
        sub = getattr(key_ctx, "_sub", None)
        if sub is None:
            raise OSError("not a subkey")
        return (sub.query(name), None)

    fake_winreg.OpenKey = _open_key_dispatch
    fake_winreg.QueryInfoKey = _query_info_key
    fake_winreg.EnumKey = _enum_key
    fake_winreg.QueryValueEx = _query_value_ex

    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)


def test_registry_displayname_matches_new_product_name(fake_env, monkeypatch, tmp_path):
    install_dir = tmp_path / "custom_install_new"
    install_dir.mkdir()
    exe_path = install_dir / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    _patch_winreg(monkeypatch, [
        _FakeWinregSub(f"{NEW_NAME} 0.1.72", install_location=str(install_dir)),
    ])

    app = StockClientApp()
    assert app.exe() == exe_path


def test_registry_displayname_matches_legacy_product_name(fake_env, monkeypatch, tmp_path):
    install_dir = tmp_path / "custom_install_legacy"
    install_dir.mkdir()
    exe_path = install_dir / f"{LEGACY_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.71")

    _patch_winreg(monkeypatch, [
        _FakeWinregSub(f"{LEGACY_NAME} 0.1.71", install_location=str(install_dir)),
    ])

    app = StockClientApp()
    assert app.exe() == exe_path


def test_registry_entry_for_unrelated_app_is_ignored(fake_env, monkeypatch, tmp_path):
    """An unrelated app's registry DisplayName must never be treated as a
    Stock Client install, however similarly its folder is laid out."""
    unrelated_dir = tmp_path / "unrelated_app"
    unrelated_dir.mkdir()
    (unrelated_dir / f"{NEW_NAME}.exe").write_bytes(b"not actually the stock client")

    _patch_winreg(monkeypatch, [
        _FakeWinregSub("Some Other Product 2.0", install_location=str(unrelated_dir)),
    ])

    app = StockClientApp()
    # No real candidate dir contains it either (fake_env dirs are empty), and
    # the registry match legitimately failed to add unrelated_dir as a
    # candidate -- so nothing is found, proving the mismatch was not papered
    # over by some other, broader match.
    assert app.exe() is None


# ---------------------------------------------------------------------------
# 5. Installation directory discovered through supported paths.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subdir", [
    lambda env: env["program_files"] / NEW_NAME,
    lambda env: env["program_files"] / "Nexora Supplier Stock" / NEW_NAME,
    lambda env: env["localappdata"] / "Programs" / NEW_NAME,
])
def test_all_supported_candidate_paths_are_discoverable(fake_env, subdir):
    exe_path = subdir(fake_env) / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    app = StockClientApp()
    assert app.exe() == exe_path


# ---------------------------------------------------------------------------
# 6. Executable missing.
# ---------------------------------------------------------------------------

def test_exe_missing_returns_none(fake_env):
    # Directory exists, but no .exe inside it.
    (fake_env["program_files"] / NEW_NAME).mkdir()

    app = StockClientApp()
    assert app.exe() is None
    assert app.installed() is False
    assert app.version() is None


# ---------------------------------------------------------------------------
# 7. Registry entry missing (covered implicitly by fake_env's bare
#    winreg-absent default, asserted explicitly here).
# ---------------------------------------------------------------------------

def test_no_registry_entries_falls_back_to_filesystem_guesses(fake_env, monkeypatch):
    _patch_winreg(monkeypatch, [])  # zero subkeys -- registry present but empty
    exe_path = fake_env["program_files"] / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    app = StockClientApp()
    assert app.exe() == exe_path


# ---------------------------------------------------------------------------
# 8. Invalid installation directory (InstallLocation points at a path that
#    does not exist / is not readable).
# ---------------------------------------------------------------------------

def test_invalid_install_location_is_skipped_safely(fake_env, monkeypatch, tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    exe_path = fake_env["program_files"] / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    _patch_winreg(monkeypatch, [
        _FakeWinregSub(f"{NEW_NAME} 0.1.72", install_location=str(missing_dir)),
    ])

    app = StockClientApp()
    # The bogus registry-reported directory must not crash discovery, and
    # the real filesystem-guess candidate must still be found.
    assert app.exe() == exe_path


# ---------------------------------------------------------------------------
# 9. Multiple candidate directories (several empty/unrelated dirs plus one
#    real install -- the real one must still be found).
# ---------------------------------------------------------------------------

def test_multiple_candidate_directories_real_one_is_found(fake_env):
    (fake_env["program_files"] / NEW_NAME).mkdir()  # exists, empty
    (fake_env["program_files"] / "Nexora Supplier Stock" / NEW_NAME).mkdir(parents=True)  # exists, empty
    exe_path = fake_env["localappdata"] / "Programs" / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    app = StockClientApp()
    assert app.exe() == exe_path


# ---------------------------------------------------------------------------
# 10. Old and new installations coexisting -- the dual-install ambiguity.
# ---------------------------------------------------------------------------

def test_dual_install_programfiles_new_name_preferred_over_localappdata_legacy(fake_env):
    """When both a new-named ProgramFiles install and a legacy-named
    LOCALAPPDATA install exist, _candidate_dirs()'s ordering (every
    ProgramFiles-family path before any LOCALAPPDATA path) means the
    ProgramFiles install wins -- regardless of which name each one carries.
    This is deterministic today; it is NOT "newest version wins" or
    "current PRODUCT_NAME wins" in general, only "ProgramFiles-family wins
    over LOCALAPPDATA family". Documented explicitly, not assumed silently."""
    new_in_programfiles = fake_env["program_files"] / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(new_in_programfiles, "0.1.72")
    legacy_in_localappdata = fake_env["localappdata"] / "Programs" / LEGACY_NAME / f"{LEGACY_NAME}.exe"
    _write_exe_with_version(legacy_in_localappdata, "0.1.71")

    app = StockClientApp()
    assert app.exe() == new_in_programfiles


def test_dual_install_same_directory_current_name_preferred_over_legacy(fake_env):
    """When both a current-named and legacy-named exe exist in the SAME
    candidate directory (the realistic in-place-upgrade-gone-wrong case),
    exe() checks PRODUCT_NAME before any _LEGACY_PRODUCT_NAMES entry within
    that directory -- so the current name always wins at equal directory
    precedence. This is the one ordering guarantee the implementation does
    give deterministically."""
    install_dir = fake_env["program_files"] / NEW_NAME
    new_exe = install_dir / f"{NEW_NAME}.exe"
    legacy_exe = install_dir / f"{LEGACY_NAME}.exe"
    _write_exe_with_version(new_exe, "0.1.72")
    _write_exe_with_version(legacy_exe, "0.1.71")

    app = StockClientApp()
    assert app.exe() == new_exe


def test_dual_install_localappdata_new_name_preferred_over_legacy_slug(fake_env):
    """Within LOCALAPPDATA/Programs, the current-PRODUCT_NAME-named folder
    is probed before the legacy literal slug folder (axythic-supplier-stock),
    so a dual install there also resolves deterministically to the new one."""
    new_exe = fake_env["localappdata"] / "Programs" / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(new_exe, "0.1.72")
    legacy_exe = fake_env["localappdata"] / "Programs" / "axythic-supplier-stock" / f"{LEGACY_NAME}.exe"
    _write_exe_with_version(legacy_exe, "0.1.60")

    app = StockClientApp()
    assert app.exe() == new_exe


# ---------------------------------------------------------------------------
# 11. Correct executable selected for update operations.
# ---------------------------------------------------------------------------

def test_update_targets_the_discovered_install_directory(fake_env, monkeypatch, tmp_path):
    exe_path = fake_env["program_files"] / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.71")

    staged = tmp_path / "staged" / "NEXORA-MEDIQ-Setup-0.1.72.exe"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"fake-installer")

    monkeypatch.setattr(apps_mod, "fetch_package", lambda ctx, key, pkg: staged)
    # is_running() calls host.is_running(exe); False here since nothing in
    # this test actually launches a process -- exercises the real method
    # (apps.py previously had none at all; see StockClientApp.is_running,
    # added in this phase as a proven pre-existing defect fix).
    monkeypatch.setattr(apps_mod.host, "is_running", lambda exe: False)
    # BACKUP_DIR defaults to a real C:\ProgramData path requiring admin
    # rights to write -- redirect to an isolated temp dir for this test.
    monkeypatch.setattr(apps_mod, "BACKUP_DIR", tmp_path / "backups_root")

    captured_cmdline = {}

    def fake_run(cmdline, timeout=900):
        captured_cmdline["value"] = cmdline
        return (0, "")

    monkeypatch.setattr(apps_mod, "run", fake_run)
    monkeypatch.setattr(apps_mod, "wait_until", lambda *a, **k: True)

    class _Ctx:
        def maintenance(self, key):
            class _CM:
                def __enter__(self2):
                    return self2

                def __exit__(self2, *a):
                    return False

            return _CM()

        def progress(self, msg):
            pass

    app = StockClientApp()
    result = app.update(_Ctx(), {"version": "0.1.72"})

    assert str(exe_path.parent) in captured_cmdline["value"]
    assert "0.1.71" in result
    assert "0.1.72" in result


# ---------------------------------------------------------------------------
# 12. Incorrect or unrelated executable rejected.
# ---------------------------------------------------------------------------

def test_unrelated_exe_with_similar_name_not_matched(fake_env):
    """An exe whose name merely contains the product name as a substring
    (but is not an exact '<name>.exe' match) must not be discovered."""
    decoy_dir = fake_env["program_files"] / NEW_NAME
    decoy_dir.mkdir(parents=True)
    (decoy_dir / f"{NEW_NAME} Uninstaller.exe").write_bytes(b"not the main exe")

    app = StockClientApp()
    assert app.exe() is None


# ---------------------------------------------------------------------------
# 13. No installation found.
# ---------------------------------------------------------------------------

def test_no_installation_found_anywhere(fake_env):
    app = StockClientApp()
    assert app.exe() is None
    assert app.installed() is False
    assert app.status() == "stopped"
    assert app.version() is None


# ---------------------------------------------------------------------------
# 14. Malformed registry information handled safely.
# ---------------------------------------------------------------------------

def test_malformed_registry_display_name_missing_handled_safely(fake_env, monkeypatch):
    """A subkey with no DisplayName value at all (OSError on query) must be
    skipped without raising, and must not prevent other candidates from
    being found."""
    class _NoDisplayNameSub(_FakeWinregSub):
        def __init__(self):
            super().__init__(display_name=None)

        def query(self, name):
            raise OSError("no DisplayName")

    _patch_winreg(monkeypatch, [_NoDisplayNameSub()])

    exe_path = fake_env["program_files"] / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    app = StockClientApp()
    assert app.exe() == exe_path  # malformed subkey did not crash discovery


def test_malformed_registry_install_location_empty_falls_through(fake_env, monkeypatch):
    """A matched DisplayName with an empty InstallLocation (and no
    DisplayIcon/UninstallString either) contributes zero candidate dirs from
    the registry, but must not raise and must not block the filesystem-guess
    fallback from still finding a real install."""
    _patch_winreg(monkeypatch, [
        _FakeWinregSub(f"{NEW_NAME} 0.1.72", install_location=""),
    ])

    exe_path = fake_env["program_files"] / NEW_NAME / f"{NEW_NAME}.exe"
    _write_exe_with_version(exe_path, "0.1.72")

    app = StockClientApp()
    assert app.exe() == exe_path
