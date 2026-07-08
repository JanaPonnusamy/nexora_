"""File-system installation for the SELF-CONTAINED Store Agent (SYNC-029B).

Final layout under <install_path> (no Python source, no machine Python needed):
    NexoraStoreAgent.exe          <- standalone service host (embedded Python, onefile)
    NexoraStoreAgentSettings.exe  <- standalone settings utility
    agent_config.json             <- per-store identity (STEP 6)
    cache/  logs/  updates/  backups/

(A legacy onedir build would also carry an _internal/ folder next to the exe;
copy_runtime_files() still deploys it if present, but it is not required.)

The agent runtime is shipped INSIDE the exe as bytecode; this installer copies
the prebuilt standalone distribution and never deploys .py source files.
"""
import json
import shutil
from pathlib import Path

from . import AGENT_EXE_NAME, SETTINGS_EXE_NAME
from .agent_config import write_config
from .paths import repo_root, resource_root

SUBDIRS = ("cache", "logs", "updates", "backups")


class Installer:
    def __init__(self, install_path, log=None):
        self.root = Path(install_path)
        self._log = log or (lambda msg: None)

    def log(self, msg):
        self._log(msg)

    # ---- STEP 5/7: directories -------------------------------------------

    def create_directories(self):
        self.root.mkdir(parents=True, exist_ok=True)
        created = []
        for name in SUBDIRS:
            path = self.root / name
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
            self.log(f"created {path}")
        return created

    # ---- STEP 6: persist downloaded HO configuration ----------------------

    def save_agent_config_json(self, config):
        path = write_config(self.root, config)
        self.log(f"wrote {path}")
        return path

    def save_ho_agent_config(self, ho_agent_config):
        """Raw GET /agent-config payload, kept under cache/ for reference only
        (the agent re-fetches it from HO at runtime)."""
        path = self.root / "cache" / "ho_agent_config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ho_agent_config, indent=2), encoding="utf-8")
        self.log(f"wrote {path}")
        return path

    # ---- STEP 7: standalone runtime --------------------------------------

    def _locate_agent_distribution(self):
        """Find the prebuilt standalone agent: a single onefile exe (current),
        or a legacy onedir bundle (exe + _internal) if one is still present."""
        candidates = [
            resource_root() / "agent",                 # bundled in the wizard exe
            repo_root() / "dist",                       # local onefile build (dev)
            repo_root() / "dist" / "NexoraStoreAgent",  # local onedir build (legacy)
        ]
        for candidate in candidates:
            if (candidate / AGENT_EXE_NAME).is_file():
                return candidate
        return None

    def copy_runtime_files(self):
        """Deploy the standalone agent exe (+ _internal, only if this is a
        legacy onedir build) and the settings exe. No .py source is ever
        written. Only the agent exe (and its _internal, if any) are copied --
        never the whole source `dist` folder, which may also contain the
        Settings/Setup executables during a local dev build."""
        copied = []
        dist = self._locate_agent_distribution()
        if dist is None:
            raise FileNotFoundError(
                "Standalone agent distribution not found. Build it first with "
                "`python -m store_agent_setup.build` (produces dist/NexoraStoreAgent.exe)."
            )
        exe_target = self.root / AGENT_EXE_NAME
        shutil.copy2(dist / AGENT_EXE_NAME, exe_target)
        copied.append(exe_target)
        internal_src = dist / "_internal"
        if internal_src.is_dir():
            internal_target = self.root / "_internal"
            if internal_target.exists():
                shutil.rmtree(internal_target)
            shutil.copytree(internal_src, internal_target)
            copied.append(internal_target)
        self.log(f"deployed standalone agent from {dist}")

        # Settings utility (standalone exe) if present alongside the bundle.
        for base in (resource_root(), repo_root() / "dist"):
            settings = base / SETTINGS_EXE_NAME
            if settings.is_file():
                dst = self.root / SETTINGS_EXE_NAME
                shutil.copy2(settings, dst)
                copied.append(dst)
                self.log(f"copied {dst.name}")
                break

        self._verify_standalone()
        return copied

    def _verify_standalone(self):
        """Guarantee the target is a true standalone deploy with NO source.

        _internal is a legacy-onedir artifact, not required for a onefile
        deploy, so its presence is only checked when the source dist has it.
        """
        exe = self.root / AGENT_EXE_NAME
        if not exe.is_file():
            raise FileNotFoundError(f"{AGENT_EXE_NAME} missing after deploy")
        stray = [str(p.relative_to(self.root)) for p in self.root.rglob("*.py")]
        if stray:
            raise RuntimeError(
                "deployment leaked Python source files: " + ", ".join(stray[:10])
            )
        self.log("verified standalone deploy (exe present, no .py source)")

    # ---- full install -----------------------------------------------------

    def install(self, agent_config_json, ho_agent_config):
        self.create_directories()
        self.copy_runtime_files()
        self.save_ho_agent_config(ho_agent_config)
        cfg_path = self.save_agent_config_json(agent_config_json)
        return cfg_path
