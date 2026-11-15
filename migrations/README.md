"""Migrasi database dengan Alembic.

Jalankan:
    alembic init migrations       # (sudah dilakukan)
    alembic revision --autogenerate -m "init"
    alembic upgrade head

Pastikan pgvector extension sudah aktif di database sebelum migrasi pertama:
    CREATE EXTENSION IF NOT EXISTS vector;
"""

