# Google Ads MCP v2 Rebuild

## Current scope

Read-only first. No Google Ads mutations are enabled.

Tools:
- `health_check`
- `list_accessible_customers`
- `list_customer_clients`
- `get_account_performance`
- `get_daily_performance`
- `get_campaign_performance`
- `get_ad_group_performance`
- `get_ad_performance`

## Required runtime environment

- `GOOGLE_ADS_DEVELOPER_TOKEN`
- `GOOGLE_ADS_CLIENT_ID`
- `GOOGLE_ADS_CLIENT_SECRET`
- `GOOGLE_ADS_REFRESH_TOKEN`
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (manager account, currently expected `1633623493`)
- `PORT` (optional, defaults to `8080`)

Never commit real secrets to this repository.

## Acceptance gates

### Gate 1: Build
- package installs successfully
- `ads_mcp_v2/server.py` passes Python syntax check
- unit tests pass

### Gate 2: Credentials
- `health_check` returns `credentials_ready: true`

### Gate 3: Account discovery
- `list_accessible_customers` succeeds
- `list_customer_clients` for the manager account returns actual child accounts

### Gate 4: Performance read
For one known client account, verify:
- account performance
- daily performance
- campaign performance
- ad group performance
- ad performance

Required metrics:
- impressions
- clicks
- cost
- conversions
- conversion value
- ROAS

### Gate 5: ChatGPT connection
Deploy the Streamable HTTP endpoint, connect it to ChatGPT, then run:
- list all Google Ads child accounts
- query yesterday's performance for a known account
- query 7-day daily ROAS

No write capability is added until all read-only gates pass reliably.
