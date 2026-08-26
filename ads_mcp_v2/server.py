import os
from datetime import date
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

    cfg: dict[str, Any] = {**required, "use_proto_plus": True}
    login_customer_id = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if login_customer_id:
        cfg["login_customer_id"] = login_customer_id.replace("-", "")
    return cfg


def _client() -> GoogleAdsClient:
    return GoogleAdsClient.load_from_dict(_config())


def _normalize_customer_id(customer_id: str) -> str:
    normalized = customer_id.replace("-", "").strip()
    if not normalized.isdigit():
        raise ValueError("customer_id must contain digits only")
    return normalized


def _validate_dates(start_date: str, end_date: str) -> tuple[str, str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    return start.isoformat(), end.isoformat()


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


def _metric_payload(metrics: Any) -> dict[str, Any]:
    cost = metrics.cost_micros / 1_000_000
    conversion_value = float(metrics.conversions_value)
    return {
        "impressions": int(metrics.impressions),
        "clicks": int(metrics.clicks),
        "cost": cost,
        "conversions": float(metrics.conversions),
        "conversion_value": conversion_value,
        "roas": conversion_value / cost if cost else None,
    }


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check server availability and whether required Google Ads credentials are configured."""
    keys = [
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    ]
    configured = {key: bool(os.getenv(key)) for key in keys}
    required_ok = all(configured[key] for key in keys[:4])
    return {
        "ok": True,
        "server": "Google Ads MCP v2",
        "credentials_ready": required_ok,
        "configured": configured,
    }


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
        manager_customer_id = _normalize_customer_id(manager_customer_id)
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
        return {
            "ok": True,
            "manager_customer_id": manager_customer_id,
            "accounts": accounts,
            "count": len(accounts),
        }
    except Exception as exc:
        return _error_payload(exc)


@mcp.tool()
def get_account_performance(customer_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Get account-level Google Ads performance for YYYY-MM-DD through YYYY-MM-DD."""
    try:
        customer_id = _normalize_customer_id(customer_id)
        start_date, end_date = _validate_dates(start_date, end_date)
        service = _client().get_service("GoogleAdsService")
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
            return {
                "ok": True,
                "customer_id": customer_id,
                "start_date": start_date,
                "end_date": end_date,
                "data": None,
            }
        row = rows[0]
        return {
            "ok": True,
            "customer_id": str(row.customer.id),
            "account_name": row.customer.descriptive_name,
            "currency": row.customer.currency_code,
            "timezone": row.customer.time_zone,
            "start_date": start_date,
            "end_date": end_date,
            **_metric_payload(row.metrics),
        }
    except Exception as exc:
        return _error_payload(exc)


@mcp.tool()
def get_daily_performance(customer_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Get one account-level performance row per day for a finite date range."""
    try:
        customer_id = _normalize_customer_id(customer_id)
        start_date, end_date = _validate_dates(start_date, end_date)
        service = _client().get_service("GoogleAdsService")
        query = f"""
            SELECT
              segments.date,
              metrics.impressions,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions,
              metrics.conversions_value
            FROM customer
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY segments.date
        """
        rows = service.search(customer_id=customer_id, query=query)
        daily = [
            {"date": row.segments.date, **_metric_payload(row.metrics)}
            for row in rows
        ]
        return {
            "ok": True,
            "customer_id": customer_id,
            "start_date": start_date,
            "end_date": end_date,
            "daily": daily,
            "count": len(daily),
        }
    except Exception as exc:
        return _error_payload(exc)


@mcp.tool()
def get_campaign_performance(customer_id: str, start_date: str, end_date: str, limit: int = 100) -> dict[str, Any]:
    """Get campaign-level performance ordered by spend."""
    try:
        customer_id = _normalize_customer_id(customer_id)
        start_date, end_date = _validate_dates(start_date, end_date)
        limit = max(1, min(limit, 1000))
        service = _client().get_service("GoogleAdsService")
        query = f"""
            SELECT
              campaign.id,
              campaign.name,
              campaign.status,
              campaign.advertising_channel_type,
              metrics.impressions,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions,
              metrics.conversions_value
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY metrics.cost_micros DESC
            LIMIT {limit}
        """
        rows = service.search(customer_id=customer_id, query=query)
        campaigns = []
        for row in rows:
            campaigns.append({
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "status": row.campaign.status.name,
                "channel_type": row.campaign.advertising_channel_type.name,
                **_metric_payload(row.metrics),
            })
        return {
            "ok": True,
            "customer_id": customer_id,
            "start_date": start_date,
            "end_date": end_date,
            "campaigns": campaigns,
            "count": len(campaigns),
        }
    except Exception as exc:
        return _error_payload(exc)


@mcp.tool()
def get_ad_group_performance(customer_id: str, start_date: str, end_date: str, limit: int = 200) -> dict[str, Any]:
    """Get ad-group-level performance ordered by spend."""
    try:
        customer_id = _normalize_customer_id(customer_id)
        start_date, end_date = _validate_dates(start_date, end_date)
        limit = max(1, min(limit, 2000))
        service = _client().get_service("GoogleAdsService")
        query = f"""
            SELECT
              campaign.id,
              campaign.name,
              ad_group.id,
              ad_group.name,
              ad_group.status,
              metrics.impressions,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions,
              metrics.conversions_value
            FROM ad_group
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY metrics.cost_micros DESC
            LIMIT {limit}
        """
        rows = service.search(customer_id=customer_id, query=query)
        ad_groups = []
        for row in rows:
            ad_groups.append({
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "ad_group_id": str(row.ad_group.id),
                "ad_group_name": row.ad_group.name,
                "status": row.ad_group.status.name,
                **_metric_payload(row.metrics),
            })
        return {
            "ok": True,
            "customer_id": customer_id,
            "start_date": start_date,
            "end_date": end_date,
            "ad_groups": ad_groups,
            "count": len(ad_groups),
        }
    except Exception as exc:
        return _error_payload(exc)


@mcp.tool()
def get_ad_performance(customer_id: str, start_date: str, end_date: str, limit: int = 500) -> dict[str, Any]:
    """Get ad-level performance ordered by spend."""
    try:
        customer_id = _normalize_customer_id(customer_id)
        start_date, end_date = _validate_dates(start_date, end_date)
        limit = max(1, min(limit, 5000))
        service = _client().get_service("GoogleAdsService")
        query = f"""
            SELECT
              campaign.id,
              campaign.name,
              ad_group.id,
              ad_group.name,
              ad_group_ad.ad.id,
              ad_group_ad.ad.name,
              ad_group_ad.status,
              ad_group_ad.ad.type,
              metrics.impressions,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions,
              metrics.conversions_value
            FROM ad_group_ad
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY metrics.cost_micros DESC
            LIMIT {limit}
        """
        rows = service.search(customer_id=customer_id, query=query)
        ads = []
        for row in rows:
            ad = row.ad_group_ad.ad
            ads.append({
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "ad_group_id": str(row.ad_group.id),
                "ad_group_name": row.ad_group.name,
                "ad_id": str(ad.id),
                "ad_name": ad.name,
                "status": row.ad_group_ad.status.name,
                "ad_type": ad.type_.name,
                **_metric_payload(row.metrics),
            })
        return {
            "ok": True,
            "customer_id": customer_id,
            "start_date": start_date,
            "end_date": end_date,
            "ads": ads,
            "count": len(ads),
        }
    except Exception as exc:
        return _error_payload(exc)


def run_server() -> None:
    port = int(os.getenv("PORT", "8080"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_server()
