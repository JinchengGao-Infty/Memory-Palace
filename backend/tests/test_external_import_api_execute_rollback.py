from pathlib import Path
from typing import Dict, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import maintenance as maintenance_api


class _ImportClientStub:
    def __init__(self) -> None:
        self._next_id = 1
        self.memories: Dict[int, Dict[str, str]] = {}
        self.paths: Dict[Tuple[str, str], int] = {}
        self.meta: Dict[str, str] = {}
        self.guard_action = "ADD"

    def counts(self) -> Tuple[int, int]:
        return len(self.memories), len(self.paths)

    async def set_runtime_meta(self, key: str, value: str) -> None:
        self.meta[key] = value

    async def get_runtime_meta(self, key: str):
        return self.meta.get(key)

    async def get_memory_by_path(self, path: str, domain: str, reinforce_access: bool = False):
        _ = reinforce_access
        memory_id = self.paths.get((domain, path))
        if memory_id is None:
            return None
        memory = self.memories.get(memory_id)
        if not isinstance(memory, dict):
            return None
        return {
            "id": memory_id,
            "domain": domain,
            "path": path,
            "content": memory.get("content") or "",
        }

    async def write_guard(self, **kwargs):
        _ = kwargs
        return {
            "action": self.guard_action,
            "method": "stub",
            "reason": "stubbed",
        }

    async def create_memory(
        self,
        *,
        parent_path: str,
        content: str,
        priority: int,
        title: str,
        domain: str,
    ):
        _ = priority
        normalized_parent = str(parent_path or "").strip().strip("/")
        normalized_title = str(title or "").strip()
        path = (
            f"{normalized_parent}/{normalized_title}"
            if normalized_parent
            else normalized_title
        )
        if not path:
            raise ValueError("path is required")
        key = (domain, path)
        if key in self.paths:
            raise ValueError("path already exists")
        memory_id = self._next_id
        self._next_id += 1
        self.memories[memory_id] = {"content": content, "domain": domain, "path": path}
        self.paths[key] = memory_id
        return {
            "id": memory_id,
            "domain": domain,
            "path": path,
            "uri": f"{domain}://{path}",
        }

    async def permanently_delete_memory(
        self,
        memory_id: int,
        *,
        require_orphan: bool = False,
    ):
        _ = require_orphan
        if memory_id not in self.memories:
            raise ValueError("memory not found")
        del self.memories[memory_id]
        for key, value in list(self.paths.items()):
            if value == memory_id:
                self.paths.pop(key, None)
        return {"deleted_memory_id": memory_id}


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(maintenance_api.router)
    return TestClient(app)


def _prepare_payload(file_path: Path) -> dict:
    return {
        "file_paths": [str(file_path)],
        "actor_id": "actor-a",
        "session_id": "session-1",
        "source": "manual_import",
        "reason": "execute and rollback",
        "domain": "notes",
        "parent_path": "",
        "priority": 2,
    }


@pytest.fixture(autouse=True)
def _reset_import_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(maintenance_api, "_IMPORT_JOBS", {})
    monkeypatch.setattr(maintenance_api, "_EXTERNAL_IMPORT_GUARD", None)
    monkeypatch.setattr(maintenance_api, "_EXTERNAL_IMPORT_GUARD_FINGERPRINT", None)


def test_external_import_execute_and_rollback_restores_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client_stub = _ImportClientStub()
    monkeypatch.setattr(maintenance_api, "get_sqlite_client", lambda: client_stub)
    monkeypatch.setenv("MCP_API_KEY", "import-secret")
    monkeypatch.setenv("EXTERNAL_IMPORT_ENABLED", "true")
    monkeypatch.setenv("EXTERNAL_IMPORT_ALLOWED_ROOTS", str(tmp_path))
    headers = {"X-MCP-API-Key": "import-secret"}

    file_path = tmp_path / "memo.md"
    file_path.write_text("Import content v1", encoding="utf-8")
    before_counts = client_stub.counts()

    with _build_client() as client:
        prepare = client.post(
            "/maintenance/import/prepare",
            headers=headers,
            json=_prepare_payload(file_path),
        )
        assert prepare.status_code == 200
        job_id = prepare.json().get("job_id")
        assert isinstance(job_id, str) and job_id

        execute = client.post(
            "/maintenance/import/execute",
            headers=headers,
            json={"job_id": job_id},
        )
        assert execute.status_code == 200
        assert execute.json().get("status") == "executed"
        after_execute_counts = client_stub.counts()
        assert after_execute_counts[0] == before_counts[0] + 1

        status = client.get(f"/maintenance/import/jobs/{job_id}", headers=headers)
        assert status.status_code == 200
        assert status.json().get("status") == "executed"

        rollback = client.post(
            f"/maintenance/import/jobs/{job_id}/rollback",
            headers=headers,
            json={"reason": "manual_rollback"},
        )
        assert rollback.status_code == 200
        assert rollback.json().get("status") == "rolled_back"
        rollback_summary = rollback.json().get("rollback") or {}
        assert rollback_summary.get("attempted_memory_ids") == [1]
        assert rollback_summary.get("side_effects_audit_required") is True
        assert rollback_summary.get("residual_artifacts_review_required") is True

    after_rollback_counts = client_stub.counts()
    assert after_rollback_counts == before_counts


def test_external_import_job_status_recovers_from_runtime_meta_after_memory_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client_stub = _ImportClientStub()
    monkeypatch.setattr(maintenance_api, "get_sqlite_client", lambda: client_stub)
    monkeypatch.setenv("MCP_API_KEY", "import-secret")
    monkeypatch.setenv("EXTERNAL_IMPORT_ENABLED", "true")
    monkeypatch.setenv("EXTERNAL_IMPORT_ALLOWED_ROOTS", str(tmp_path))
    headers = {"X-MCP-API-Key": "import-secret"}

    file_path = tmp_path / "memo.md"
    file_path.write_text("Import content v1", encoding="utf-8")

    with _build_client() as client:
        prepare = client.post(
            "/maintenance/import/prepare",
            headers=headers,
            json=_prepare_payload(file_path),
        )
        assert prepare.status_code == 200
        job_id = str(prepare.json().get("job_id") or "")
        assert job_id

        monkeypatch.setattr(maintenance_api, "_IMPORT_JOBS", {})
        status = client.get(f"/maintenance/import/jobs/{job_id}", headers=headers)
        assert status.status_code == 200
        assert status.json().get("status") == "prepared"


def test_external_import_execute_and_rollback_recover_from_runtime_meta_after_memory_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client_stub = _ImportClientStub()
    monkeypatch.setattr(maintenance_api, "get_sqlite_client", lambda: client_stub)
    monkeypatch.setenv("MCP_API_KEY", "import-secret")
    monkeypatch.setenv("EXTERNAL_IMPORT_ENABLED", "true")
    monkeypatch.setenv("EXTERNAL_IMPORT_ALLOWED_ROOTS", str(tmp_path))
    headers = {"X-MCP-API-Key": "import-secret"}

    file_path = tmp_path / "memo.md"
    file_path.write_text("Import content v1", encoding="utf-8")

    with _build_client() as client:
        prepare = client.post(
            "/maintenance/import/prepare",
            headers=headers,
            json=_prepare_payload(file_path),
        )
        assert prepare.status_code == 200
        job_id = str(prepare.json().get("job_id") or "")
        assert job_id

        monkeypatch.setattr(maintenance_api, "_IMPORT_JOBS", {})
        execute = client.post(
            "/maintenance/import/execute",
            headers=headers,
            json={"job_id": job_id},
        )
        assert execute.status_code == 200
        assert execute.json().get("status") == "executed"

        monkeypatch.setattr(maintenance_api, "_IMPORT_JOBS", {})
        rollback = client.post(
            f"/maintenance/import/jobs/{job_id}/rollback",
            headers=headers,
            json={"reason": "restart_rollback"},
        )
        assert rollback.status_code == 200
        assert rollback.json().get("status") == "rolled_back"


def test_external_import_execute_rejects_when_source_changed_since_prepare(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client_stub = _ImportClientStub()
    monkeypatch.setattr(maintenance_api, "get_sqlite_client", lambda: client_stub)
    monkeypatch.setenv("MCP_API_KEY", "import-secret")
    monkeypatch.setenv("EXTERNAL_IMPORT_ENABLED", "true")
    monkeypatch.setenv("EXTERNAL_IMPORT_ALLOWED_ROOTS", str(tmp_path))
    headers = {"X-MCP-API-Key": "import-secret"}

    file_path = tmp_path / "memo.md"
    file_path.write_text("Import content v1", encoding="utf-8")

    with _build_client() as client:
        prepare = client.post(
            "/maintenance/import/prepare",
            headers=headers,
            json=_prepare_payload(file_path),
        )
        assert prepare.status_code == 200
        job_id = str(prepare.json().get("job_id") or "")
        assert job_id

        file_path.write_text("Import content changed", encoding="utf-8")
        execute = client.post(
            "/maintenance/import/execute",
            headers=headers,
            json={"job_id": job_id},
        )
        assert execute.status_code == 409
        detail = execute.json().get("detail") or {}
        assert detail.get("reason") == "source_changed_since_prepare"

        status = client.get(f"/maintenance/import/jobs/{job_id}", headers=headers)
        assert status.status_code == 200
        assert status.json().get("status") == "failed"


def test_external_import_execute_fail_closed_when_write_guard_blocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client_stub = _ImportClientStub()
    client_stub.guard_action = "NOOP"
    monkeypatch.setattr(maintenance_api, "get_sqlite_client", lambda: client_stub)
    monkeypatch.setenv("MCP_API_KEY", "import-secret")
    monkeypatch.setenv("EXTERNAL_IMPORT_ENABLED", "true")
    monkeypatch.setenv("EXTERNAL_IMPORT_ALLOWED_ROOTS", str(tmp_path))
    headers = {"X-MCP-API-Key": "import-secret"}

    file_path = tmp_path / "memo.md"
    file_path.write_text("Import content v1", encoding="utf-8")

    with _build_client() as client:
        prepare = client.post(
            "/maintenance/import/prepare",
            headers=headers,
            json=_prepare_payload(file_path),
        )
        assert prepare.status_code == 200
        job_id = str(prepare.json().get("job_id") or "")
        assert job_id

        execute = client.post(
            "/maintenance/import/execute",
            headers=headers,
            json={"job_id": job_id},
        )
        assert execute.status_code == 409
        detail = execute.json().get("detail") or {}
        assert detail.get("reason") == "write_guard_blocked"
        assert client_stub.counts() == (0, 0)
