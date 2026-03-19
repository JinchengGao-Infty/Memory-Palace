from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_vite_dev_proxy_covers_api_and_sse_routes() -> None:
    config_text = (PROJECT_ROOT / "frontend" / "vite.config.js").read_text(
        encoding="utf-8"
    )

    assert "MEMORY_PALACE_API_PROXY_TARGET" in config_text
    assert "MEMORY_PALACE_SSE_PROXY_TARGET" in config_text
    assert "'/api'" in config_text
    assert "'/sse/messages'" in config_text
    assert "'/messages'" in config_text
    assert "'/sse'" in config_text
