---
name: scope-guardrails
description: >-
  Gunakan skill ini ketika user meminta menambah atau mengubah validasi
  scope, allowlist target, rate limit, atau pemblokiran aksi berbahaya pada
  agen zaplang. Wajib dibaca sebelum menambah tool baru yang menyentuh target.
allowed-tools: Read Write Edit Glob Grep
---

# Scope Guardrails

## Prinsip
Guardrail ditegakkan di KODE pada lapisan tool, bukan di system prompt. Prompt bisa dibypass lewat prompt injection; kode tidak.

## Aturan wajib
1. Allowlist host eksplisit (`ALLOWED_HOSTS`), dimuat dari konfigurasi, bukan dari input LLM.
2. Hanya skema `http` dan `https`.
3. Bandingkan hostname hasil `urlparse` secara exact (case-insensitive). Dilarang pakai `startswith` atau `in` pada string URL.
4. Tolak target yang resolve ke alamat internal/metadata (loopback, link-local, `169.254.169.254`) kecuali memang target lab lokal yang diizinkan eksplisit.
5. Batasi: jumlah request per menit, durasi scan maksimum, kedalaman spider.
6. Aksi berisiko (active scan, payload yang menulis/menghapus data) butuh flag konfirmasi manusia (`human_approved=True`), tidak bisa diisi oleh LLM.
7. Pelanggaran memunculkan `ScopeViolation` dan dicatat di audit log (tool, argumen, waktu, hasil).

## Validasi
- Ada test untuk: host di luar scope, skema `file://`, redirect keluar scope, subdomain yang mirip (`target.example.com.evil.com`).
- Semua test harus lulus sebelum tool baru di-merge.