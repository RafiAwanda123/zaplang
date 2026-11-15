import logging
from urllib.parse import urlparse
from app.core.config import settings

logger = logging.getLogger(__name__)
_ALLOWED_SCHEMES = frozenset({"http", "https"})

class ScopeViolation(Exception):
    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"ScopeViolation: {reason} - url={url!r}")

def enforce_scope(url: str) -> None:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower()

    if scheme not in _ALLOWED_SCHEMES:
        logger.warning("SCOPE_VIOLATION url=%r reason='invalid scheme'", url)
        raise ScopeViolation(url=url, reason=f"skema tidak diizinkan: {scheme!r}")

    allowed = settings.allowed_hosts_list
    if not allowed or hostname not in allowed:
        logger.warning("SCOPE_VIOLATION url=%r reason='hostname not allowed'", url)
        raise ScopeViolation(url=url, reason=f"hostname {hostname!r} tidak ada dalam ALLOWED_HOSTS")
