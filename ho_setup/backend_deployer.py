"""Backend file installation (wizard STEP 7).

Deploys the SELF-CONTAINED HO backend distribution (HO_Backend.exe + _internal,
built by ho_setup.build) to the install folder, creates the required sub-folders
and stages the bundled NEXORA_PLATFORM.bak where SQL Server can read it. No
Python source and no machine Python are required on the target, exactly as the
Store Agent does.
"""
import shutil
from pathlib import Path

from . import (
    BACKEND_EXE_NAME,
    BACKUP_FILE_NAME,
    INSTALL_SUBDIRS,
    UNINSTALL_EXE_NAME,
)
from .paths import assets_dir, repo_root, resource_root


class BackendDeployer:
    def __init__(self, config, log=None):
        self.cfg = config
        self.root = Path(config.install_path)
        self._log = log or (lambda msg: None)

    def log(self, msg):
        self._log(msg)

    # ---- directories ------------------------------------------------------

    def create_directories(self):
        self.root.mkdir(parents=True, exist_ok=True)
        for name in INSTALL_SUBDIRS:
            path = self.root / name
            path.mkdir(parents=True, exist_ok=True)
            self.log(f"created {path}")

    # ---- backend distribution --------------------------------------------

    def _locate_backend_distribution(self):
        candidates = [
            resource_root() / "backend_dist",          # bundled in HO_Setup.exe
            repo_root() / "dist" / "HO_Backend",        # local build (dev)
        ]
        for candidate in candidates:
            if (candidate / BACKEND_EXE_NAME).is_file():
                return candidate
        return None

    def copy_backend_files(self):
        dist = self._locate_backend_distribution()
        if dist is None:
            raise FileNotFoundError(
                "HO backend distribution not found. Build it first with "
                "`python -m ho_setup.build backend` (produces dist/HO_Backend)."
            )
        for entry in dist.iterdir():
            target = self.root / entry.name
            if entry.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)
        self.log(f"deployed backend from {dist}")
        self._verify_standalone()

    def _verify_standalone(self):
        exe = self.root / BACKEND_EXE_NAME
        if not exe.is_file():
            raise FileNotFoundError(f"{BACKEND_EXE_NAME} missing after deploy")
        if not (self.root / "_internal").is_dir():
            raise FileNotFoundError("_internal runtime folder missing after deploy")
        self.log("verified standalone backend (exe + _internal present)")

    def deploy_uninstaller(self):
        """Copy HO_Uninstall.exe into the install root (best-effort)."""
        for base in (resource_root(), repo_root() / "dist"):
            src = base / UNINSTALL_EXE_NAME
            if src.is_file():
                dst = self.root / UNINSTALL_EXE_NAME
                shutil.copy2(src, dst)
                self.log(f"copied {dst.name}")
                return dst
        self.log(f"NOTE: {UNINSTALL_EXE_NAME} not found to bundle; skipping")
        return None

    # ---- bundled backup ---------------------------------------------------

    def _locate_backup(self):
        candidates = [
            resource_root() / "assets" / BACKUP_FILE_NAME,  # bundled in HO_Setup
            assets_dir() / BACKUP_FILE_NAME,                # source/dev
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def stage_backup(self):
        """Copy NEXORA_PLATFORM.bak into <install>\\backups and return its path."""
        src = self._locate_backup()
        if src is None:
            raise FileNotFoundError(
                f"{BACKUP_FILE_NAME} not bundled. Place it in ho_setup/assets/ "
                "before building (see ho_setup/assets/README.md)."
            )
        dst = self.root / "backups" / BACKUP_FILE_NAME
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        self.log(f"staged backup at {dst}")
        return dst

    # ---- configuration ----------------------------------------------------

    def write_config(self):
        return self.cfg.write_config_files(log=self.log)
