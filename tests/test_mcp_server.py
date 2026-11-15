import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.schemas.rag import ChunkResult
import mcp_server

@pytest.mark.asyncio
async def test_targeted_active_scan_requires_human_approval():
    result = await mcp_server.zap_targeted_active_scan(
        "http://target.local",
        human_approved=False,
    )
    assert "BLOCKED: Active scan memerlukan persetujuan manusia" in result

@pytest.mark.asyncio
async def test_targeted_active_scan_enforces_scope():
    result = await mcp_server.zap_targeted_active_scan(
        "http://evil.com/api",
        human_approved=True,
    )
    assert "BLOCKED" in result
    assert "ALLOWED_HOSTS" in result

@pytest.mark.asyncio
async def test_targeted_active_scan_success():
    with patch("mcp_server.ZapClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.ascan_start.return_value = "scan-123"
        mock_client_cls.return_value.__aenter__.return_value = mock_instance

        result = await mcp_server.zap_targeted_active_scan(
            "http://target.local",
            endpoint_path="/login",
            human_approved=True,
        )
        assert "scan-123" in result
        mock_instance.ascan_start.assert_called_once_with(
            "http://target.local/login",
            scan_policy_name="",
        )

@pytest.mark.asyncio
async def test_triage_alerts_filters_noise_and_assigns_vrt():
    raw_alerts = [
        {"pluginId": "10038", "alert": "CSP Missing", "risk": "Low", "url": "http://target.local"},
        {"pluginId": "40012", "alert": "Reflected XSS", "risk": "High", "url": "http://target.local/search", "param": "q", "evidence": "<script>"},
        {"pluginId": "10096", "alert": "Timestamp Disclosure", "risk": "Low", "url": "http://target.local/ts"},
    ]
    with patch("mcp_server.ZapClient") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.alerts.return_value = raw_alerts
        mock_client_cls.return_value.__aenter__.return_value = mock_instance

        result = await mcp_server.zap_triage_alerts(base_url="http://target.local")
        assert "Reflected XSS" in result
        assert "VRT P1-P2" in result
        assert "CSP Missing" not in result
        assert "Timestamp Disclosure" not in result

@pytest.mark.asyncio
async def test_generate_poc_xss():
    result = await mcp_server.zap_generate_poc(
        target_url="http://target.local/search",
        vuln_type="xss",
        param="q",
    )
    assert "[PoC - Manual Verification Required]" in result
    assert "curl -i -s -k -X GET" in result
    assert "alert" in result

@pytest.mark.asyncio
async def test_generate_poc_from_json():
    alert_payload = json.dumps({
        "url": "http://target.local/users",
        "param": "id",
        "alert": "SQL Injection",
        "method": "POST",
    })
    result = await mcp_server.zap_generate_poc(alert_json=alert_payload)
    assert "Vulnerability Type: SQLI" in result
    assert "id=" in result

@pytest.mark.asyncio
async def test_rag_lookup():
    mock_chunk = ChunkResult(
        content="Bypass XSS via data-attribute",
        source="skills/bug-bounty",
        category="xss",
        score=0.92,
    )
    with patch("mcp_server.retrieve", new_callable=AsyncMock) as mock_retrieve, \
         patch("mcp_server.AsyncSessionLocal") as mock_session_local:
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        mock_retrieve.return_value = [mock_chunk]

        result = await mcp_server.zap_rag_lookup("xss bypass", category="xss")
        assert "skills/bug-bounty" in result
        assert "0.92" in result
        assert "Bypass XSS" in result

@pytest.mark.asyncio
async def test_recon_scope_triage():
    assets_input = """
    https://target.local/app
    http://api.target.local
    https://target-group.com
    target.local/.env
    https://unrelated-domain.com
    """
    result = await mcp_server.zap_recon_scope_triage(
        assets_raw=assets_input,
        canonical_domain="target.local",
    )
    assert "In-Scope: 3" in result
    assert "Quarantined: 2" in result
    assert "Collision risk" in result
    assert "Peringatan Soft-404 Kontrol Wajib" in result
    assert ".env" in result

@pytest.mark.asyncio
async def test_osint_fingerprint_scope_blocked():
    result = await mcp_server.zap_osint_fingerprint("http://unauthorized.com")
    assert "BLOCKED" in result

@pytest.mark.asyncio
async def test_osint_fingerprint_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {
        "server": "nginx/1.24.0",
        "cf-ray": "82347abcde",
        "strict-transport-security": "max-age=31536000",
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        result = await mcp_server.zap_osint_fingerprint("http://target.local")
        assert "[OSINT Passive Fingerprint]" in result
        assert "Cloudflare CDN/WAF" in result
        assert "Nginx" in result
        assert "Strict-Transport-Security: Ada" in result
