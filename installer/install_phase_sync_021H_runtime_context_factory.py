# SYNC-021H Runtime Context Factory Installer

from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(r"E:\Nexora")

def backup_file(path: Path):
    if path.exists():
        backup_dir = ROOT / "backup" / f"sync021H_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_file(path)
    path.write_text(content.strip() + "\n", encoding="utf-8")

factory_code = """
from store_agent.runtime_context import StoreAgentRuntimeContext

class RuntimeContextFactory:

    def create(self, runtime_config):

        return StoreAgentRuntimeContext(
            runtime_config
        )
"""

test_code = """
from store_agent.runtime_context_factory import RuntimeContextFactory

def test_runtime_context_factory():

    factory = RuntimeContextFactory()

    ctx = factory.create({})

    assert ctx is not None
"""

write_file(
    ROOT / "store_agent" / "runtime_context_factory.py",
    factory_code
)

write_file(
    ROOT / "tests" / "test_runtime_context_factory.py",
    test_code
)

print("SYNC-021H INSTALL COMPLETE")
