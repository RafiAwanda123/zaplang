"""Endpoint /health.

Mengembalikan status aplikasi. Digunakan oleh Docker healthcheck dan
load balancer untuk memverifikasi aplikasi berjalan.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Kembalikan status ok."""
    return {"status": "ok"}

