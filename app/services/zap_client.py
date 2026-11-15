from typing import Any
import httpx
from app.core.config import settings
from app.core.scope import enforce_scope

_MAX_ALERT_COUNT = 200
_REQUEST_TIMEOUT = 30.0

class ZapClient:
    def __init__(self) -> None:
        self._base = settings.zap_base.rstrip("/")
        self._headers = {"X-ZAP-Api-Key": settings.zap_api_key}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ZapClient":
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers=self._headers,
            follow_redirects=False,
            timeout=_REQUEST_TIMEOUT,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        assert self._client is not None, "Gunakan ZapClient sebagai context manager"
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def version(self) -> str:
        data = await self._get("/JSON/core/view/version/")
        return str(data.get("version", "unknown"))

    async def spider_start(self, target_url: str, *, subtree_only: bool = True) -> str:
        enforce_scope(target_url)
        data = await self._get(
            "/JSON/spider/action/scan/",
            params={"url": target_url, "subtreeOnly": str(subtree_only).lower()},
        )
        return str(data.get("scan", ""))

    async def spider_status(self, scan_id: str) -> int:
        data = await self._get("/JSON/spider/view/status/", params={"scanId": scan_id})
        return int(data.get("status", 0))

    async def ascan_start(
        self,
        target_url: str,
        *,
        recurse: bool = False,
        in_scope_only: bool = True,
        scan_policy_name: str = "",
    ) -> str:
        enforce_scope(target_url)
        params: dict[str, Any] = {
            "url": target_url,
            "recurse": str(recurse).lower(),
            "inScopeOnly": str(in_scope_only).lower(),
        }
        if scan_policy_name:
            params["scanPolicyName"] = scan_policy_name
        data = await self._get("/JSON/ascan/action/scan/", params=params)
        return str(data.get("scan", ""))

    async def ascan_status(self, scan_id: str) -> int:
        data = await self._get("/JSON/ascan/view/status/", params={"scanId": scan_id})
        return int(data.get("status", 0))

    async def alerts(self, base_url: str = "", start: int = 0, count: int = _MAX_ALERT_COUNT) -> list[dict[str, Any]]:
        if base_url:
            enforce_scope(base_url)
        params: dict[str, Any] = {"start": start, "count": min(count, _MAX_ALERT_COUNT)}
        if base_url:
            params["baseurl"] = base_url
        data = await self._get("/JSON/alert/view/alerts/", params=params)
        return list(data.get("alerts", []))
