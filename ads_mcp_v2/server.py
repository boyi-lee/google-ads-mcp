import os
from typing import Any

from fastmcp import FastMCP
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

mcp = FastMCP("Google Ads MCP v2")


def _config() -> dict[str, Any]:
    required = {
        "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    cfg: dict[str, Any] = {
        **required,
        "use_proto_plus": True,
    }
    login_customer_id = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if login_customer_id:
        cfg["login_customer_id"] = login_customer_id.replace("-", "")
    return cfg


def _client() -> GoogleAdsClient:
    return GoogleAdsClient.load_from_dict(_config())


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, GoogleAdsException):
        errors = []
        for error in exc.failure.errors:
            errors.append({
                "message": error.message,
                "error_code": str(error.error_code),
                "location": str(error.location) if error.location else None,
            })
        return {
            "ok": False,
            "type": "GoogleAdsException",
            "request_id": getattr(exc, "request_id", None),
            "errors": errors,
        }
    return {"ok": False, "type": exc.__class__.__name__, "message": str(exc)}


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check whether the MCP server is alive and whether required Google Ads credentials are configured."""
    keys = [
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    ]
    configured = {key: bool(os.getenv(key)) for key in keys}
    required_ok = all(configured[key] for key in keys[:4])
    return {"ok": True, "server": "Google Ads MCP v2", "credentials_ready": required_ok, "configured": configured}


@mcp.tool()
def list_accessible_customers() -> dict[str, Any]:
    """List Google Ads customer IDs directly accessible by the authenticated Google account."""
    try:
        client = _client()
        service = client.get_service("CustomerService")
        response = service.list_accessible_customers()
        ids = [name.split("/")[-1] for name in response.resource_names]
        return {"ok": True, "customer_ids": ids, "count": len(ids)}
    except Exception as exc:
        return _error_payload(exc)


@mcp.tool()
def list_customer_clients(manager_customer_id: str) -> dict[str, Any]:
    """List child accounts visible under a Google Ads manager account."""
    try:
        manager_customer_id = manager_customer_id.replace("-", "")
        client = _client()
        service = client.get_service("GoogleAdsService")
        query = """
            SELECT
              customer_client.id,
              customer_client.descriptive_name,
              customer_client.level,
              customer_client.manager,
              customer_client.currency_code,
              customer_client.time_zone,
              customer_client.status
            FROM customer_client
            WHERE customer_client.level <= 1
            ORDER BY customer_client.level, customer_client.id
        """
        rows = service.search(customer_id=manager_customer_id, query=query)
        accounts = []
        for row in rows:
            cc = row.customer_client
            accounts.append({
                "customer_id": str(cc.id),
                "name": cc.descriptive_name,
                "level": cc.level,
                "is_manager": cc.manager,
                "currency": cc.currency_code,
                "timezone": cc.time_zone,
                "status": cc.status.name,
            })
        return {"ok": True, "manager_customer_id": manager_customer_id, "accounts": accounts, "count": len(accounts)}
    except Exception as exc:
        return _error_payload(exc)


@mcp.tool()
def get_account_performance(customer_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Get account-level Google Ads performance for a finite date range YYYY-MM-DD to YYYY-MM-DD."""
    try:
        customer_id = customer_id.replace("-", "")
        client = _client()
        service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT
              customer.id,
              customer.descriptive_name,
              customer.currency_code,
              customer.time_zone,
              metrics.impressions,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions,
              metrics.conversions_value
            FROM customer
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """
        rows = list(service.search(customer_id=customer_id, query=query))
        if not rows:
            return {"ok": True, "customer_id": customer_id, "start_date": start_date, "end_date": end_date, "data": None}

        row = rows[0]
        cost = row.metrics.cost_micros / 1_000_000
        conversion_value = float(row.metrics.conversions_value)
        roas = conversion_value / cost if cost else None
        return {
            "ok": True,
            "customer_id": str(row.customer.id),
            "account_name": row.customer.descriptive_name,
            "currency": row.customer.currency_code,
            "timezone": row.customer.time_zone,
            "start_date": start_date,
            "end_date": end_date,
            "impressions": int(row.metrics.impressions),
            "clicks": int(row.metrics.clicks),
            "cost": cost,
            "conversions": float(row.metrics.conversions),
            "conversion_value": conversion_value,
            "roas": roas,
        }
    except Exception as exc:
        return _error_payload(exc)


def run_server() -> None:
    port = int(os.getenv("PORT", "8080"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_server()
