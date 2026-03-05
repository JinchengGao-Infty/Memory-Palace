import json

import pytest

import main


def test_resolve_cors_disables_credentials_for_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    origins, allow_credentials = main._resolve_cors_config()

    assert origins == ["*"]
    assert allow_credentials is False


def test_resolve_cors_keeps_credentials_for_explicit_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,https://example.com",
    )
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    origins, allow_credentials = main._resolve_cors_config()

    assert origins == ["http://localhost:5173", "https://example.com"]
    assert allow_credentials is True


@pytest.mark.asyncio
async def test_health_hides_internal_exception_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom():
        raise RuntimeError("boom-secret-detail")

    monkeypatch.setattr(main, "get_sqlite_client", _boom)

    payload = await main.health()
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["status"] == "degraded"
    assert payload["index"]["reason"] == "internal_error"
    assert payload["index"]["error_type"] == "RuntimeError"
    assert payload["runtime"]["write_lanes"]["reason"] == "internal_error"
    assert payload["runtime"]["index_worker"]["reason"] == "internal_error"
    assert "boom-secret-detail" not in serialized
