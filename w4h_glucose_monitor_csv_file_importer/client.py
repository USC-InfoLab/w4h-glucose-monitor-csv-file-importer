"""HTTP client for W4H API (personal API key only)."""

import requests

from .config import api_base, require_api_key


class W4HClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or api_base()).rstrip("/")
        key = (api_key or require_api_key()).strip()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-W4H-API-Key": key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _get(self, path: str, timeout: int = 30) -> object:
        resp = self.session.get(f"{self.base_url}{path}", timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict, timeout: int) -> dict:
        resp = self.session.post(f"{self.base_url}{path}", json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def list_datasets(self) -> list[dict]:
        """Datasets the API key can see (GET /datasets)."""
        payload = self._get("/datasets")
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return payload.get("datasets") or payload.get("data") or []
        return []

    def import_csv_batch(self, dataset_id: str, payload: dict) -> dict:
        return self._post(f"/datasets/{dataset_id}/import/csv-batch", payload, timeout=120)
