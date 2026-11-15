import pytest
from app.core.config import settings
from app.core.scope import ScopeViolation, enforce_scope

def test_enforce_scope_allowed():
    # settings default: allowed_hosts="target.local"
    enforce_scope("http://target.local")
    enforce_scope("https://target.local/path?q=1")

def test_enforce_scope_disallowed_host():
    with pytest.raises(ScopeViolation):
        enforce_scope("http://google.com")

def test_enforce_scope_disallowed_scheme():
    with pytest.raises(ScopeViolation):
        enforce_scope("file:///etc/passwd")
    with pytest.raises(ScopeViolation):
        enforce_scope("ftp://target.local")

def test_enforce_scope_subdomain_spoof():
    with pytest.raises(ScopeViolation):
        enforce_scope("http://target.local.evil.com")
