"""Test skeleton untuk zaplang.

TODO:
- tests/test_scope.py  - uji enforce_scope(): host luar scope, file://, subdomain palsu, redirect.
- tests/test_zap_client.py - uji ZapClient dengan httpx mock; pastikan ScopeViolation dilempar.
- tests/test_health.py - uji GET /health.
- tests/test_untrusted_output.py - uji bahwa evidence dengan injeksi prompt tetap terbungkus.

Semua test harus lulus sebelum tool baru di-merge (scope-guardrails rule #5 & validasi).
"""

