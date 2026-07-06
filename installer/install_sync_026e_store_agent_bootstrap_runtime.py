"""
install_sync_026e_store_agent_bootstrap_runtime.py
"""

from pathlib import Path
import shutil

ROOT = Path(r"E:\Nexora")

FILES = {
    "store_agent/runtime/runtime_bootstrap.py": """
from store_agent.config import STORE_ID, HO_API_URL
from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.sql_connection_verification_service import SqlConnectionVerificationService

class RuntimeBootstrap:

    def bootstrap(self):

        config_url = (
            f"{HO_API_URL}/api/stores/{STORE_ID}/agent-config"
        )

        runtime_config = (
            RuntimeConfigurationLoader()
            .load(config_url)
        )

        runtime_context = (
            RuntimeContextFactory()
            .create(runtime_config)
        )

        connection = (
            RuntimeSqlConnectionService()
            .connect(runtime_context)
        )

        verification = (
            SqlConnectionVerificationService()
            .verify(connection)
        )

        return {
            "runtime_context": runtime_context,
            "verification": verification
        }
""",
    "store_agent/runtime/runtime_ready_service.py": """
class RuntimeReadyService:

    def build(self, verification):

        return {
            "runtime_ready": verification.get("is_connected", False)
        }
""",
    "tests/test_runtime_bootstrap_import.py": """
def test_runtime_bootstrap_import():
    from store_agent.runtime.runtime_bootstrap import RuntimeBootstrap
    assert RuntimeBootstrap is not None
""",
    "docs/SYNC-026E.md": "# SYNC-026E Store Agent Bootstrap Runtime\n"
}

for rel, content in FILES.items():
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\\n", encoding="utf-8")

print("SYNC-026E INSTALL COMPLETE")
