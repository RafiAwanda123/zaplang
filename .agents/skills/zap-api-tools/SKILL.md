---
name: zap-api-tools
description: >-
  Gunakan skill ini ketika user meminta menulis atau mengubah kode yang
  memanggil OWASP ZAP REST API di project zaplang, termasuk spider, passive
  scan, active scan, dan pengambilan alerts.
allowed-tools: Read Write Edit Glob Grep
---

# ZAP API Tools

## Prinsip
- Satu tool = satu fungsi bertipe (`spider_start`, `get_alerts`). Dilarang membuat tool generik seperti `zap_call(endpoint, params)`.
- Semua panggilan ZAP lewat satu kelas `ZapClient` (httpx async). LLM tidak pernah memanggil ZAP langsung.

## Langkah menambah method baru
1. Tentukan endpoint ZAP yang dipakai (lihat tabel di bawah).
2. Panggil `enforce_scope()` pada setiap parameter URL SEBELUM request.
3. Clamp semua parameter numerik (`maxChildren`, `count`) ke batas maksimum.
4. Pasang timeout; scan yang berjalan harus punya jalur stop.
5. Tambah test: kasus normal dan kasus `ScopeViolation`.

## Endpoint
| Fungsi | Endpoint |
|---|---|
| Versi | `/JSON/core/view/version/` |
| Spider start | `/JSON/spider/action/scan/` (`subtreeOnly=true`) |
| Spider status | `/JSON/spider/view/status/` |
| Spider stop | `/JSON/spider/action/stop/` |
| Passive scan antrean | `/JSON/pscan/view/recordsToScan/` |
| Alerts | `/JSON/alert/view/alerts/` (paginasi `start`, `count`) |

## Aturan keamanan
- API key hanya dari env `ZAP_API_KEY`, dikirim lewat header `X-ZAP-Api-Key`, bukan query string.
- ZAP hanya bind ke `127.0.0.1`.
- `follow_redirects=False` pada client.
- Jangan pernah hardcode key atau mencetaknya ke log.