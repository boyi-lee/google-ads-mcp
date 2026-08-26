import os

from ads_mcp_v2 import server


def test_health_check_without_credentials(monkeypatch):
    for key in [
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    ]:
        monkeypatch.delenv(key, raising=False)

    result = server.health_check.fn()
    assert result["ok"] is True
    assert result["credentials_ready"] is False


def test_config_requires_credentials(monkeypatch):
    for key in [
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
    ]:
        monkeypatch.delenv(key, raising=False)

    try:
        server._config()
    except RuntimeError as exc:
        message = str(exc)
        assert "developer_token" in message
        assert "client_id" in message
        assert "client_secret" in message
        assert "refresh_token" in message
    else:
        raise AssertionError("_config() should fail when credentials are missing")


def test_config_normalizes_manager_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "dev")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_ID", "client")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_ADS_REFRESH_TOKEN", "refresh")
    monkeypatch.setenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "163-362-3493")

    cfg = server._config()
    assert cfg["login_customer_id"] == "1633623493"


def test_plain_exception_is_structured():
    result = server._error_payload(RuntimeError("boom"))
    assert result == {
        "ok": False,
        "type": "RuntimeError",
        "message": "boom",
    }
