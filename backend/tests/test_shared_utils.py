from shared_utils import env_bool, env_int, is_loopback_hostname, utc_iso_now


def test_env_bool_uses_shared_truthy_values(monkeypatch) -> None:
    monkeypatch.setenv("MP_SHARED_BOOL", "enabled")
    assert env_bool("MP_SHARED_BOOL", False) is True
    monkeypatch.setenv("MP_SHARED_BOOL", "off")
    assert env_bool("MP_SHARED_BOOL", True) is False


def test_env_int_keeps_runtime_style_default_fallback(monkeypatch) -> None:
    monkeypatch.delenv("MP_SHARED_INT", raising=False)
    assert env_int("MP_SHARED_INT", 3, minimum=5) == 3
    monkeypatch.setenv("MP_SHARED_INT", "2")
    assert env_int("MP_SHARED_INT", 3, minimum=5) == 5


def test_env_int_supports_sse_style_clamped_default(monkeypatch) -> None:
    monkeypatch.delenv("MP_SHARED_INT", raising=False)
    assert env_int("MP_SHARED_INT", 3, minimum=5, clamp_default=True) == 5
    monkeypatch.setenv("MP_SHARED_INT", "invalid")
    assert env_int("MP_SHARED_INT", 3, minimum=5, clamp_default=True) == 5


def test_is_loopback_hostname_handles_ipv6_and_host_ports() -> None:
    assert is_loopback_hostname("[::1]:8000") is True
    assert is_loopback_hostname("127.0.0.1:5173") is True
    assert is_loopback_hostname("memory-palace.example") is False


def test_utc_iso_now_returns_utc_z_suffix() -> None:
    assert utc_iso_now().endswith("Z")
