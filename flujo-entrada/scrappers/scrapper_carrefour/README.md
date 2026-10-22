# scrapper_carrefour — BLOQUEADO

No pasa challenge JS de Cloudflare.

- `GET /` y `GET /supermercado/` -> `403 + Cf-Mitigated: challenge + Server: cloudflare` (15/10/2026).
- Probado con `requests` y `curl.exe` simple: solo devuelve página de challenge (~5KB), 0 productos.
- En pausa hasta navegador real. Ver `out/carrefour_*.txt`.
