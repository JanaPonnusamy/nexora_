"""
install_sync_026d_store_agent_runtime_host.py
"""

import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd().parent
LOG_DIR = ROOT / "logs"
BACKUP_DIR = ROOT / "backup" / "sync_026d"

FILES = {
    "store_agent/main.py": """from store_agent.runtime.runtime_host import RuntimeHost

def main():
    RuntimeHost().start()

if __name__ == "__main__":
    main()
""",
    "store_agent/runtime/runtime_host.py": """class RuntimeHost:

    def start(self):
        from store_agent.runtime.store_agent_runtime import StoreAgentRuntime
        StoreAgentRuntime().run_forever()
""",
    "store_agent/runtime/store_agent_runtime.py": """import time

class StoreAgentRuntime:

    def run_forever(self):

        while True:
            time.sleep(60)
""",
    "store_agent/runtime/runtime_scheduler.py": """class RuntimeScheduler:

    def run(self):
        return True
""",
    "tests/test_store_agent_runtime.py": """def test_runtime_import():
    from store_agent.runtime.store_agent_runtime import StoreAgentRuntime
    assert StoreAgentRuntime is not None
""",
    "docs/SYNC-026D.md": "# SYNC-026D Store Agent Runtime Entry Point\n"
}

def log(msg):
    print(msg)

def backup_file(path):
    if path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, BACKUP_DIR / path.name)

def write_file(rel_path, content):
    file_path = ROOT / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if file_path.exists():
        backup_file(file_path)
        action = "[UPDATE]"
    else:
        action = "[CREATE]"

    file_path.write_text(content, encoding="utf-8")
    log(f"{action} {rel_path}")

def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for rel_path, text in FILES.items():
        write_file(rel_path, text)

    log("[SUCCESS] SYNC-026D COMPLETE")

if __name__ == "__main__":
    main()
