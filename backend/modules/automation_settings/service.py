from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = REPO_ROOT / "automation" / "config" / "runtime_settings.json"


def _run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _split_command(command: str) -> list[str]:
    parts = shlex.split(command, posix=False)
    return [part.strip('"') for part in parts if part.strip()]


def _command_exists(parts: list[str]) -> bool:
    if not parts:
        return False
    try:
        proc = _run([parts[0], "--version"])
    except OSError:
        return False
    return proc.returncode == 0


def _normalize_repo_path(repo_path: str | None) -> str:
    value = (repo_path or "").strip()
    if not value:
        return str(REPO_ROOT)
    return str(Path(value).expanduser().resolve())


def _candidate_python_commands() -> list[str]:
    candidates: list[str] = []
    for path in (
        REPO_ROOT / ".buildvenv" / "Scripts" / "python.exe",
        REPO_ROOT / "backend" / ".venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    ):
        if path.is_file():
            candidates.append(str(path.resolve()))
    candidates.extend(["python", "py -3", "py"])
    return list(dict.fromkeys(candidates))


def _detect_python_command() -> str:
    for candidate in _candidate_python_commands():
        parts = _split_command(candidate)
        if not parts:
            continue
        try:
            version = _run(parts + ["--version"])
        except OSError:
            continue
        if version.returncode != 0:
            continue
        probe = _run(parts + ["-m", "automation", "--help"], cwd=REPO_ROOT)
        if probe.returncode == 0:
            return candidate
    return ""


def _load_saved_settings() -> dict[str, str]:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "repo_path": str(payload.get("repo_path", "")).strip(),
        "python_command": str(payload.get("python_command", "")).strip(),
    }


def _write_settings(repo_path: str, python_command: str) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(
            {
                "repo_path": _normalize_repo_path(repo_path),
                "python_command": python_command.strip(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _ensure_settings_file(repo_path: str, python_command: str) -> None:
    if SETTINGS_PATH.is_file():
        return
    if repo_path and python_command:
        _write_settings(repo_path, python_command)


def _git_status(repo_path: str) -> dict[str, object]:
    normalized = _normalize_repo_path(repo_path)
    repo_dir = Path(normalized)
    if not repo_dir.exists():
        return {"ok": False, "message": "Repository path does not exist.", "root": normalized}

    probe = _run(["git", "rev-parse", "--show-toplevel"], cwd=repo_dir)
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or "Git repository not found.").strip()
        return {"ok": False, "message": detail, "root": normalized}

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    return {
        "ok": True,
        "message": "Git repository detected.",
        "root": probe.stdout.strip(),
        "branch": branch.stdout.strip() if branch.returncode == 0 else "",
    }


def _python_status(python_command: str, repo_path: str) -> dict[str, object]:
    value = python_command.strip()
    if not value:
        return {"ok": False, "message": "Python command is not configured.", "command": ""}

    parts = _split_command(value)
    if not parts:
        return {"ok": False, "message": "Python command is invalid.", "command": value}

    try:
        version = _run(parts + ["--version"])
    except OSError as exc:
        return {"ok": False, "message": str(exc), "command": value}
    if version.returncode != 0:
        detail = (version.stderr or version.stdout or "Python command failed.").strip()
        return {"ok": False, "message": detail, "command": value}

    automation = _run(parts + ["-m", "automation", "--help"], cwd=Path(_normalize_repo_path(repo_path)))
    if automation.returncode != 0:
        detail = (automation.stderr or automation.stdout or "Automation module could not start.").strip()
        return {
            "ok": False,
            "message": detail,
            "command": value,
            "version": (version.stdout or version.stderr).strip(),
        }

    return {
        "ok": True,
        "message": "Python runtime can launch the automation module.",
        "command": value,
        "version": (version.stdout or version.stderr).strip(),
    }


def _automation_status(repo_path: str, python_command: str) -> dict[str, object]:
    git = _git_status(repo_path)
    python = _python_status(python_command, repo_path)
    if not git["ok"]:
        return {"ok": False, "message": "Automation is blocked until the git repository is valid."}
    if not python["ok"]:
        return {"ok": False, "message": "Automation is blocked until the Python command is valid."}

    parts = _split_command(python_command)
    probe = _run(parts + ["-m", "automation", "version", "show"], cwd=Path(_normalize_repo_path(repo_path)))
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or "Automation validation failed.").strip()
        return {"ok": False, "message": detail}

    return {"ok": True, "message": (probe.stdout or "").strip() or "Automation is ready."}


def get_settings() -> dict[str, object]:
    saved = _load_saved_settings()
    detected_repo = str(REPO_ROOT)
    detected_python = _detect_python_command()

    repo_path = saved.get("repo_path") or detected_repo
    python_command = saved.get("python_command") or detected_python
    _ensure_settings_file(repo_path, python_command)

    return {
        "settings": {
            "repo_path": _normalize_repo_path(repo_path),
            "python_command": python_command,
        },
        "detected": {
            "repo_path": detected_repo,
            "python_command": detected_python,
        },
        "status": {
            "git": _git_status(repo_path),
            "python": _python_status(python_command, repo_path),
            "automation": _automation_status(repo_path, python_command),
        },
        "config_file": str(SETTINGS_PATH),
    }


def save_settings(repo_path: str, python_command: str) -> dict[str, object]:
    normalized_repo = _normalize_repo_path(repo_path)
    normalized_python = python_command.strip()
    _write_settings(normalized_repo, normalized_python)
    return get_settings()
