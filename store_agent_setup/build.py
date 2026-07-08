"""Package the Store Agent into a SELF-CONTAINED deployment with PyInstaller.

    python -m store_agent_setup.build            # build everything
    python -m store_agent_setup.build agent      # only the agent

Outputs in E:\\Nexora\\dist\\:
    NexoraStoreAgent.exe              (onefile: single self-contained binary)
    NexoraStoreAgentSettings.exe      (standalone settings utility)
    NexoraStoreAgentSetup.exe         (the wizard; bundles the two above)

Design notes (SYNC-029B, revised for onefile):
* The agent is built ONEFILE: a single distributable binary, no accompanying
  _internal folder. Onefile self-extracts into a fresh per-launch temp dir
  (sys._MEIPASS), so anything that must survive a restart (the SQLite sync
  cache) is anchored to NEXORA_INSTALL_PATH / sys.executable's real, stable
  location instead of __file__ -- see SqliteCacheService and
  store_agent_setup.paths.resource_root / agent_service._agent_install_path,
  which already used that pattern.
* store_agent is shipped as COMPILED BYTECODE inside the bundle (collected
  submodules in the PYZ). The .py source tree is NEVER added as data, so no
  source code is deployed to stores.
* The exe embeds its own Python; target machines need NO Python installed.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "store_agent_setup"
DIST = REPO / "dist"
BUILD = REPO / "build"
SEP = ";"  # Windows add-data separator

FERNET = REPO / "store_agent" / "config" / "fernet.key"

# Imports PyInstaller cannot always discover statically.
_HIDDEN = [
    "win32timezone",
    "pyodbc",
    "store_agent.run_agent",
    "store_agent.run_sync_runtime",
]


def _pyinstaller(*args):
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", *args]
    print(">>", subprocess.list2cmdline(cmd))
    subprocess.run(cmd, check=True, cwd=str(REPO))


def build_agent():
    """Standalone ONEFILE service host. Embeds Python + the whole store_agent
    runtime as bytecode. No machine Python, no .py source on disk."""
    args = ["--onefile", "--name", "NexoraStoreAgent", "--console",
            "--paths", str(REPO), "--collect-submodules", "store_agent"]
    for h in _HIDDEN:
        args += ["--hidden-import", h]
    if FERNET.is_file():
        # The fernet key is data (not source) the runtime needs to decrypt creds.
        args += ["--add-data", f"{FERNET}{SEP}store_agent/config"]
    args.append(str(PKG / "launch_agent_service.py"))
    _pyinstaller(*args)


def build_settings():
    """Standalone settings utility (onefile is fine for a manual tool)."""
    _pyinstaller(
        "--onefile", "--windowed", "--name", "NexoraStoreAgentSettings",
        "--paths", str(REPO),
        str(PKG / "launch_settings.py"),
    )


def build_wizard():
    """The distributable wizard (onefile). Bundles the standalone agent exe
    and the settings exe as DATA so the installer can deploy them as-is."""
    args = ["--onefile", "--windowed", "--name", "NexoraStoreAgentSetup",
            "--paths", str(REPO)]
    agent_exe = DIST / "NexoraStoreAgent.exe"
    settings_exe = DIST / "NexoraStoreAgentSettings.exe"
    if agent_exe.is_file():
        # Single agent binary -> _MEIPASS/agent/NexoraStoreAgent.exe.
        args += ["--add-data", f"{agent_exe}{SEP}agent"]
    if settings_exe.is_file():
        args += ["--add-data", f"{settings_exe}{SEP}."]
    args.append(str(PKG / "launch_wizard.py"))
    _pyinstaller(*args)


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found; installing...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"], check=True
        )


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    target = argv[0] if argv else "all"
    ensure_pyinstaller()
    DIST.mkdir(exist_ok=True)
    if target in ("all", "agent"):
        build_agent()
    if target in ("all", "settings"):
        build_settings()
    if target in ("all", "wizard"):
        build_wizard()
    if BUILD.exists():
        shutil.rmtree(BUILD, ignore_errors=True)
    print("\nArtifacts in", DIST)
    for item in sorted(DIST.iterdir()):
        kind = "dir " if item.is_dir() else "file"
        print(f"   [{kind}] {item.name}")


if __name__ == "__main__":
    main()
