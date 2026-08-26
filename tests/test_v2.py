import pytest

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

    result = server.health_check()
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

    with pytest.raises(RuntimeError) as exc_info:
        server._config()

    message = str(exc_info.value)
    assert "developer_token" in message
    assert "client_id" in message
    assert "client_secret" in message
    assert "refresh_token" in message


def test_config_normalizes_manager_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "dev")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_ID", "client")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_ADS_REFRESH_TOKEN", "refresh")
    monkeypatch.setenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "163-362-3493")

    cfg = server._config()
    assert cfg["login_customer_id"] == "1633623493"


def test_customer_id_normalization():
    assert server._normalize_customer_id("163-362-3493") == "1633623493"
    with pytest.raises(ValueError):
        server._normalize_customer_id("abc")


def test_date_validation():
    assert server._validate_dates("2026-08-01", "2026-08-26") == (
        "2026-08-01",
        "2026-08-26",
    )
    with pytest.raises(ValueError):
        server._validate_dates("2026-08-26", "2026-08-01")
    with pytest.raises(ValueError):
        server._validate_dates("2026/08/01", "2026-08-26")


def test_metric_payload():
    class Metrics:
        impressions = 1000
        clicks = 50
        cost_micros = 2_000_000
        conversions = 4.0
        conversions_value = 10.0

    result = server._metric_payload(Metrics())
    assert result["cost"] == 2.0
    assert result["conversion_value"] == 10.0
    assert result["roas"] == 5.0


def test_metric_payload_zero_cost():
    class Metrics:
        impressions = 0
        clicks = 0
        cost_micros = 0
        conversions = 0.0
        conversions_value = 0.0

    result = server._metric_payload(Metrics())
    assert result["roas"] is None


def test_plain_exception_is_structured():
    result = server._error_payload(RuntimeError("boom"))
    assert result == {
        "ok": False,
        "type": "RuntimeError",
        "message": "boom",
    }
