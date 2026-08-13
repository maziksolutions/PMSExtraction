import datetime
import httpx
from typing import Any, Dict
from app.core.config import settings

async def fetch_anthropic_console_data() -> Dict[str, Any]:
    """
    Queries the Anthropic Admin API for real organization usage and cost reports.
    Requires an Admin API key (prefixed with sk-ant-admin...).
    """
    # Use Admin key if explicitly configured, otherwise fall back to regular key (in case they supplied an admin key there)
    api_key = settings.ANTHROPIC_ADMIN_API_KEY or settings.ANTHROPIC_API_KEY
    if not api_key:
        return {
            "status": "not_configured",
            "message": "No API key configured. Provide ANTHROPIC_ADMIN_API_KEY (sk-ant-admin...) in your environment to fetch live console stats."
        }

    # Format 30 days ago to ISO format
    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    starting_at = thirty_days_ago.strftime("%Y-%m-%dT00:00:00Z")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        async with httpx.AsyncClient() as client:
            # Query Usage endpoint
            usage_url = f"https://api.anthropic.com/v1/organizations/usage_report/messages?starting_at={starting_at}&bucket_width=1d"
            usage_resp = await client.get(usage_url, headers=headers, timeout=8.0)

            # Query Costs endpoint
            cost_url = f"https://api.anthropic.com/v1/organizations/cost_report?starting_at={starting_at}&bucket_width=1d"
            cost_resp = await client.get(cost_url, headers=headers, timeout=8.0)

            if usage_resp.status_code == 403 or usage_resp.status_code == 401:
                return {
                    "status": "unauthorized",
                    "status_code": usage_resp.status_code,
                    "message": "Access Denied. A standard API key cannot read billing reports. Please configure a valid Admin API Key (sk-ant-admin...)."
                }

            if usage_resp.status_code != 200 or cost_resp.status_code != 200:
                return {
                    "status": "error",
                    "status_code": usage_resp.status_code,
                    "message": f"Anthropic console API error. Usage Status: {usage_resp.status_code}, Cost Status: {cost_resp.status_code}."
                }

            return {
                "status": "success",
                "usage_report": usage_resp.json(),
                "cost_report": cost_resp.json()
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Network error when calling Anthropic Admin API: {str(e)}"
        }
