-- migrations/001_rag.sql
-- Jalankan satu kali sebelum menjalankan aplikasi.
-- Pastikan user DB memiliki hak CREATE EXTENSION (superuser atau rds_superuser).

BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id      UUID        NOT NULL,
    content     TEXT        NOT NULL,
    -- Dimensi 768 sesuai EMBED_MODEL default (nomic-embed-text via Ollama).
    -- Ganti angka ini jika EMBED_MODEL menghasilkan dimensi berbeda.
    embedding   vector(768) NOT NULL,
    source      TEXT        NOT NULL,
    category    TEXT        NOT NULL CHECK (category IN ('xss', 'idor', 'sqli', 'general')),
    trust       TEXT        NOT NULL DEFAULT 'unverified'
                    CHECK (trust IN ('curated', 'unverified')),
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index HNSW untuk cosine similarity search (pgvector ≥ 0.5)
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_hnsw_idx
    ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Index B-tree pada category untuk filter cepat
CREATE INDEX IF NOT EXISTS knowledge_chunks_category_idx
    ON knowledge_chunks (category);

-- Index B-tree pada trust untuk filter default query
CREATE INDEX IF NOT EXISTS knowledge_chunks_trust_idx
    ON knowledge_chunks (trust);

COMMIT;
