# install_sync_025b_b_schema_catalog_upload_runtime.py

from pathlib import Path
import textwrap

ROOT = Path(r"E:\Nexora")

SERVICE_FILE = (
    ROOT
    / "store_agent"
    / "services"
    / "schema_catalog_upload_service.py"
)

RUNNER_FILE = (
    ROOT
    / "store_agent"
    / "run_schema_catalog_upload.py"
)

SERVICE_CODE = """
import json
from pathlib import Path

import requests


class SchemaCatalogUploadService:

    def __init__(self):

        self.base_path = (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )

        self.schema_path = (
            self.base_path
            / "schema"
        )

        self.payload_file = (
            self.schema_path
            / "schema_catalog_payload.json"
        )

        self.result_file = (
            self.schema_path
            / "schema_upload_result.json"
        )

        self.endpoint = (
            "http://127.0.0.1:8000"
            "/api/sync/schema/register"
        )

    def upload(self):

        payload = json.loads(
            self.payload_file.read_text(
                encoding="utf-8"
            )
        )

        response = requests.post(
            self.endpoint,
            json=payload,
            timeout=3600
        )

        response.raise_for_status()

        result = response.json()

        self.result_file.write_text(
            json.dumps(
                result,
                indent=4
            ),
            encoding="utf-8"
        )

        return result
"""

RUNNER_CODE = """
from services.schema_catalog_upload_service import (
    SchemaCatalogUploadService
)


def main():

    result = (
        SchemaCatalogUploadService()
        .upload()
    )

    print()
    print("=" * 80)
    print("SYNC-025B-B")
    print("Schema Catalog Upload")
    print("=" * 80)

    print()

    for key, value in result.items():
        print(
            f"{key}: {value}"
        )


if __name__ == "__main__":
    main()
"""


def write_file(path, content):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        textwrap.dedent(content).strip()
        + "\\n",
        encoding="utf-8"
    )

    print(
        f"[CREATED] {path}"
    )


write_file(
    SERVICE_FILE,
    SERVICE_CODE
)

write_file(
    RUNNER_FILE,
    RUNNER_CODE
)

print()
print("=" * 80)
print("SYNC-025B-B INSTALL COMPLETE")
print("=" * 80)

print()
print("RUN")
print(
    r"python E:\Nexora\store_agent\run_schema_catalog_upload.py"
)

print()
print("VERIFY")
print(
    r"type E:\Nexora\store_agent\schema\schema_upload_result.json"
)