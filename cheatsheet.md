# Postman API Cheatsheet - zaplang

File ini berisi panduan cepat dan payload siap pakai untuk testing endpoint `zaplang` via Postman.

> **Catatan Autentikasi:**
> Untuk header `X-RAG-Api-Key`, salin nilai `RAG_API_KEY` dari file `.env` Anda.

---

## 1. Healthcheck

Memverifikasi bahwa server backend FastAPI aktif dan sehat.

* **Method:** `GET`
* **URL:** `http://127.0.0.1:8000/health`
* **Headers:** *(Tidak ada)*
* **Body:** *(None)*
* **Expected Response (200 OK):**
  ```json
  {
    "status": "ok"
  }
  ```

---

## 2. Ingest Dokumen RAG (Simpan Pengetahuan Ke pgvector)

Menyimpan referensi teknik keamanan ke dalam vector database (pgvector) menggunakan embedding lokal Ollama.

* **Method:** `POST`
* **URL:** `http://127.0.0.1:8000/rag/documents`
* **Headers:**
  | Key | Value |
  |---|---|
  | `Content-Type` | `application/json` |
  | `X-RAG-Api-Key` | *<isi dengan RAG_API_KEY dari .env>* |

### Contoh Payload 1 (Kategori: XSS)
```json
{
  "source": "owasp_xss_prevention.md",
  "content": "Cross-Site Scripting (XSS) terjadi ketika aplikasi memasukkan data yang tidak tepercaya ke dalam halaman web tanpa validasi atau encoding yang tepat. Pencegahan utama adalah menggunakan context-sensitive output encoding dan menerapkan Content Security Policy (CSP).",
  "category": "xss",
  "trust": "curated"
}
```

### Contoh Payload 2 (Kategori: SQL Injection)
```json
{
  "source": "owasp_sqli_cheatsheet.md",
  "content": "SQL Injection (SQLi) adalah kerentanan di mana penyerang dapat memanipulasi query database. Mitigasi utama SQLi adalah dengan menggunakan parameterized queries atau prepared statements secara konsisten di seluruh lapisan akses data.",
  "category": "sqli",
  "trust": "curated"
}
```

### Contoh Payload 3 (Kategori: IDOR)
```json
{
  "source": "owasp_idor_guide.md",
  "content": "Insecure Direct Object References (IDOR) terjadi ketika aplikasi menggunakan input yang disediakan pengguna untuk mengakses objek langsung tanpa pemeriksaan otorisasi tingkat objek. Mitigasi dilakukan dengan memvalidasi kepemilikan data pengguna saat ini sebelum mereturn objek.",
  "category": "idor",
  "trust": "curated"
}
```

* **Expected Response (201 Created):**
  ```json
  {
    "doc_id": "0df83749-8c63-4796-857c-255d645f74a0",
    "chunks_saved": 1
  }
  ```

---

## 3. Query Dokumen RAG (Semantic Search dengan pgvector)

Mencari dokumen pengetahuan berdasarkan kemiripan arti kata (cosine similarity search).

* **Method:** `POST`
* **URL:** `http://127.0.0.1:8000/rag/query`
* **Headers:**
  | Key | Value |
  |---|---|
  | `Content-Type` | `application/json` |
  | `X-RAG-Api-Key` | *<isi dengan RAG_API_KEY dari .env>* |

### Contoh Payload Query 1 (Tanya pencegahan XSS)
```json
{
  "question": "Bagaimana cara mencegah celah XSS?",
  "top_k": 2,
  "category": "xss"
}
```

### Contoh Payload Query 2 (Tanya celah database SQL)
```json
{
  "question": "Apa mitigasi terbaik untuk SQL injection?",
  "top_k": 2,
  "category": "sqli"
}
```

* **Expected Response (200 OK):**
  ```json
  {
    "answer": "Cross-Site Scripting (XSS) terjadi ketika aplikasi memasukkan data yang tidak tepercaya...",
    "sources": [
      "owasp_xss_prevention.md"
    ]
  }
  ```

---

## 4. Test Error Handling (Validasi Keamanan)

### Tes Tanpa API Key (Harus Ditolak)
* **Method:** `POST`
* **URL:** `http://127.0.0.1:8000/rag/documents`
* **Headers:** *(Kosongkan X-RAG-Api-Key)*
* **Body:** *(Gunakan payload Ingest)*
* **Expected Response:** `401 Unauthorized` atau `422 Unprocessable Entity` (header missing).

