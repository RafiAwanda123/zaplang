# Tutorial Pengujian Keamanan API Manual dengan OWASP ZAP dan Postman

Panduan ini menjelaskan alur kerja pengujian keamanan backend API secara manual dengan mengombinasikan Postman (sebagai API Client) dan OWASP ZAP (sebagai Intercepting Proxy dan Security Scanner).

---

## 1. Konsep Arsitektur dan Alur Kerja

Dalam pengujian backend, Postman digunakan untuk menyusun request terautentikasi (JWT Bearer token, session cookie, JSON payload), sementara ZAP menangkap, merekam, memodifikasi, dan memindai seluruh lalu lintas HTTP/HTTPS tersebut.

```
[Postman Client] 
       │
       ▼ (HTTP/HTTPS Request)
[OWASP ZAP Proxy : 127.0.0.1:8080]  <── Intersep, Modifikasi, Passive/Active Scan
       │
       ▼
[Backend API Target (In-Scope)]
```

Dengan konfigurasi ini:
1. ZAP memetakan seluruh rute API backend secara otomatis di **Sites Tree**.
2. Anda dapat melakukan pengujian manual terarah (*tampering*, IDOR, bypass otorisasi) langsung melalui Postman atau editor intersep ZAP.
3. Scanner aktif ZAP dapat dijalankan hanya pada parameter spesifik tanpa merusak sesi autentikasi.

---

## 2. Langkah Konfigurasi Awal

### A. Konfigurasi OWASP ZAP Proxy
1. Buka OWASP ZAP GUI.
2. Buka menu **Tools** -> **Options** -> **Network** -> **Local Servers/Proxies** (atau **Local Proxies** pada ZAP versi lama).
3. Pastikan konfigurasi proxy lokal:
   - **Address:** `localhost` atau `127.0.0.1`
   - **Port:** `8080`
4. Ekspor Sertifikat Root CA ZAP (untuk lalu lintas HTTPS):
   - Masuk ke **Tools** -> **Options** -> **Network** -> **Server Certificates** (atau **Dynamic SSL Certificates**).
   - Klik tombol **Save** untuk menyimpan file `owasp_zap_root_ca.cer` ke komputer Anda.

### B. Konfigurasi Postman
1. Buka Postman -> Buka **Settings** (ikon gerigi di kanan atas).
2. Tab **Proxy**:
   - Aktifkan toggle **Use custom proxy configuration**.
   - Pilih **HTTP** dan **HTTPS**.
   - **Proxy Server:** `127.0.0.1` : `8080`
3. Tab **Certificates** (Pilih salah satu metode):
   - **Metode 1 (Disarankan untuk testing lokal/staging):** Di tab **General**, matikan toggle **SSL certificate verification**.
   - **Metode 2:** Di tab **Certificates**, aktifkan **CA Certificates** lalu upload file `owasp_zap_root_ca.cer` yang diekspor dari ZAP.

### C. Menentukan Scope Target di ZAP
Untuk mencegah ZAP memindai domain di luar izin:
1. Di ZAP, buat Context baru: Klik kanan pada **Sites** -> **New Context**.
2. Masukkan URL target (contoh: `http://target.local` atau `http://127.0.0.1:8000`).
3. Tambahkan regex domain ke **Include in Context**: `\Qhttp://target.local\E.*`
4. Aktifkan tombol **Set target in scope** (ikon target merah di toolbar).

---

## 3. Langkah Pengujian Manual Langkah demi Langkah

### Langkah 1: Pemetaan Endpoint Backend (Reconnaissance)
1. Buka Postman Collection yang berisi rute-rute API backend Anda.
2. Pastikan environment Postman sudah memuat token autentikasi yang valid.
3. Kirim request secara berurutan atau jalankan **Postman Collection Runner**:
   - Contoh rute:
     - `POST /api/auth/login`
     - `GET /api/users/profile`
     - `GET /api/orders/101`
     - `POST /api/orders`
4. Periksa ZAP: Seluruh rute, metode HTTP, header, dan parameter JSON kini terekam rapi di tab **Sites Tree** dan **History**.

---

### Langkah 2: Evaluasi Passive Scan (Penyaringan Awal)
ZAP secara otomatis mengaudit respons HTTP yang lewat tanpa mengirim paket berbahaya tambahan.

1. Buka tab **Alerts** di ZAP.
2. Terapkan filter **7-Question Gate** (hindari menghabiskan waktu pada temuan dangkal):
   - Abaikan: Missing CSP header, Missing X-Content-Type-Options, Server version banner (noise scanner).
   - Selidiki: Sensitif token/API key di parameter URL, kebocoran stack trace error DB, response JSON yang memuat field PII berlebih (*Excessive Data Exposure*).

---

### Langkah 3: Pengujian Manual Kerentanan Kritis (Tampering)

#### A. Pengujian IDOR (Insecure Direct Object Reference / BOLA)
1. Siapkan dua akun pengguna di Postman:
   - **User A** (Korban): Memiliki order ID `101`.
   - **User B** (Penyerang): Memiliki order ID `202`.
2. Kirim request di Postman menggunakan token **User B**, tetapi ubah path/parameter menuju resource milik **User A**:
   ```http
   GET /api/orders/101 HTTP/1.1
   Host: target.local
   Authorization: Bearer <TOKEN_USER_B>
   ```
3. Amati respons di ZAP:
   - Jika status `403 Forbidden` atau `404 Not Found`: Aman (kontrol akses berjalan).
   - Jika status `200 OK` dan data User A tampil: **IDOR terkonfirmasi (VRT P2/P3)**.

#### B. Pengujian Broken Object Level Authentication (BFLA)
1. Kirim request endpoint administratif menggunakan token pengguna biasa:
   ```http
   GET /api/admin/users HTTP/1.1
   Host: target.local
   Authorization: Bearer <TOKEN_USER_REGULAR>
   ```
2. Coba juga dengan menghapus header `Authorization` seluruhnya.
3. Jika backend tetap merespons dengan data sensitif: **Auth Bypass / Broken Function Level Authorization**.

#### C. Pengujian Injeksi Parameter (SQLi / NoSQLi)
1. Di Postman, pilih endpoint pencarian atau filter:
   `GET /api/products?search=test`
2. Modifikasi payload parameter secara bertahap:
   - SQLi string break: `test'` atau `test' OR '1'='1`
   - NoSQLi JSON operator: Ubah body menjadi `{"username": {"$ne": null}, "password": {"$ne": null}}`
3. Amati perbedaan respons di ZAP: bandingkan status code, ukuran response body, dan pesan kesalahan database.

---

### Langkah 4: Targeted Active Scan pada Endpoint Tertentu
Jangan menjalankan Active Scan ke seluruh aplikasi agar tidak memicu rate-limit atau merusak database. Jalankan hanya pada endpoint yang dicurigai.

1. Di ZAP **Sites Tree**, klik kanan pada endpoint spesifik yang ingin diuji (contoh: `POST:orders(items,address)`).
2. Pilih **Attack** -> **Active Scan...**
3. Pada dialog Active Scan:
   - Pastikan **Recurse** tidak dicentang.
   - Pilih tab **Policy**: Fokuskan hanya pada kategori *Injection*, *Path Traversal*, atau *Server Side Code Injection*.
4. Klik **Start Scan**.
5. Amati tab **Active Scan** untuk melihat mutasi payload yang dikirimkan ZAP.

---

### Langkah 5: Kontrol Soft-404 Wajib (Anti False-Positive)
Jika ZAP menemukan file sensitif seperti `.env`, `.git`, atau `/actuator`:
1. Kirim request ke file tersebut:
   `curl -s -i http://target.local/.env`
2. Kirim request kontrol ke path sampah acak:
   `curl -s -i http://target.local/zzz-nonsense-random-1234`
3. Bandingkan panjang byte dan status code:
   - Jika kedua response identik (misal sama-sama 200 dengan konten HTML default SPA): **False Positive (Soft-404 catch-all)**. Jangan dilaporkan.
   - Jika response `.env` berbeda dan memuat teks konfigurasi nyata: **Temuan valid**.

---

## 4. Memanfaatkan MCP Tools zaplang untuk Akselerasi

Jika proyek `zaplang` dijalankan sebagai asisten keamanan berbasis AI (MCP Server), Anda dapat mengotomatisasi analisis manual di atas menggunakan tool berikut:

| Tool MCP | Fungsi dalam Pengujian Manual |
|---|---|
| `zap_triage_alerts` | Menyaring alert ZAP secara otomatis dengan filter 7-Question Gate dan memetakan ke prioritas Bugcrowd VRT (P1-P4). |
| `zap_recon_scope_triage` | Memisahkan domain dan subdomain target dari tabrakan nama (*namespace collision*) sebelum Postman dijalankan. |
| `zap_osint_fingerprint` | Memeriksa banner server, reverse proxy, dan WAF/CDN secara pasif sebelum menentukan payload injection. |
| `zap_generate_poc` | Mengonversi alert ZAP menjadi perintah `curl` minimal siap uji yang dapat langsung ditempel ke terminal. |
| `zap_rag_lookup` | Mengambil referensi teknik bypass atau pola payload dari database pengetahuan pgvector. |

---

## 5. Template Dokumentasi Laporan Temuan

Jika menemukan kerentanan valid dari pengujian manual, gunakan format laporan standar industri:

```markdown
# [Jenis Celah] pada [Endpoint] menyebabkan [Dampak Bisnis Konkret]

## Ringkasan Eksekutif
Deskripsi singkat mengenai temuan dan bagaimana celah dapat dieksploitasi.

## Klasifikasi Bugcrowd VRT
- Kategori: Server-Side Injection / Broken Authorization / IDOR
- Severity: P1 (Critical) / P2 (High) / P3 (Medium) / P4 (Low)

## Endpoint & Parameter Terpapar
- Method: POST
- URL: http://target.local/api/orders
- Parameter: order_id

## Langkah Reproduksi (PoC)
1. Buka terminal atau Postman.
2. Kirim request dengan perintah curl berikut:
   ```bash
   curl -i -s -k -X GET "http://target.local/api/orders/101" \
     -H "Authorization: Bearer <TOKEN_USER_B>"
   ```
3. Perhatikan bahwa response memuat data milik User A.

## Bukti Respons (Evidence)
<untrusted_data>
HTTP/1.1 200 OK
Content-Type: application/json

{
  "order_id": 101,
  "owner_email": "korban@target.local",
  "credit_card_last4": "1234"
}
</untrusted_data>

## Dampak Bisnis Nyata
Penyerang dapat mengunduh seluruh data transaksi dan informasi sensitif pelanggan lain tanpa hak akses.

## Rekomendasi Remediasi
Terapkan pengecekan otorisasi tingkat objek (*Object-Level Authorization*) pada layer repository/service sebelum data dikembalikan ke client.
```

