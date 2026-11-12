# scrapper_carrefour — BLOQUEADO

No pasa challenge JS de Cloudflare.

- `GET /` y `GET /supermercado/` -> `403 + Cf-Mitigated: challenge + Server: cloudflare` (15/10/2026).
- Probado con `requests` y `curl.exe` simple: solo devuelve página de challenge (~5KB), 0 productos.
- Con navegador real (Playwright, Chromium sin interfaz) tampoco: `403 Attention Required` de
  Cloudflare en todas las páginas (11/11/2026). Pasarlo exigiría técnicas para ocultar el bot;
  descartado (ver `docs/05-pendientes.md`). No se despliega. Ver `out/carrefour_*.txt`.
