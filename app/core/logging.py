"""Logging konfigurasi untuk zaplang.

Stub - setup handler dan formatter akan ditambahkan di sini.
Audit log untuk ScopeViolation dan aksi berisiko dikirim ke logger terpisah
agar mudah difilter oleh SIEM / log aggregator.
"""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Konfigurasi root logger dan audit logger.

    TODO:
    - Tambah JSON formatter untuk structured logging.
    - Tambah handler audit terpisah (misal ke file atau external sink).
    """
    logging.basicConfig(level=level.upper())

