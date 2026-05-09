from __future__ import annotations

import requests
from ..config import settings


class MarketInfoService:
    """Best-effort company profile and corporate events lookup.

    If `settings.company_info_api_url` is configured, this service will attempt
    to query it with the provided symbol. Otherwise it returns an empty dict.
    """

    def __init__(self) -> None:
        self.base = getattr(settings, "company_info_api_url", None)

    def get_company_profile(self, symbol: str) -> dict:
        if not self.base:
            return {}
        try:
            url = f"{self.base.rstrip('/')}/company/{symbol}"
            resp = requests.get(url, timeout=6)
            if resp.status_code != 200:
                return {}
            data = resp.json()
            # Normalize expected keys
            return {
                "sector": data.get("sector") or data.get("industry_sector") or None,
                "industry": data.get("industry") or data.get("industry_group") or None,
                "market_cap": data.get("market_cap") or data.get("marketCapitalization") or None,
                "corporate_events": data.get("corporate_events") or data.get("events") or None,
            }
        except Exception:
            return {}
