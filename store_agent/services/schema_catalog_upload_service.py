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
