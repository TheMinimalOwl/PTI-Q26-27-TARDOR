# scrappers

Recolectores crudos. Sin normalización.

- Cada scraper solo extrae datos tal cual de la web y los vuelca a `txt`.
- Normaliza Fission, no el scraper.
- Activos: **Mercadona** (`scraper.mercadona.raw`) y **Consum** (`scraper.consum.raw`). Los
  dos publican en NATS además del `txt` y se ejecutan a las 02:00 (hora de Madrid).
- El scraper de Carrefour existe pero está bloqueado por Cloudflare (ver su README).
- Para añadir una cadena: scraper que publique el crudo en `scraper.<cadena>.raw` + una
  función `from_<cadena>()` en `fission/normalizer/normalizer.py` + su CronJob en
  `infra/terraform/scraper.tf`. El consumer y el writer de API/BD ya la recogen solos.

## Qué supermercados tienen API (investigación del 11/11/2026)

| Súper | Acceso | Estado |
|---|---|---|
| Mercadona | API JSON pública (`tienda.mercadona.es/api`) | ✅ Activo |
| Consum | API JSON pública (`tienda.consum.es/api/rest/V1.0`) | ✅ Activo |
| Ahorramás | Sin JSON; HTML paginado de Salesforce Commerce Cloud (`Search-UpdateGrid`, 96 por página) | 🟡 Viable |
| Eroski | HTML renderizado en servidor, sin antibot | 🟡 Viable, falta ver el precio por unidad |
| Alcampo | API JSON de Ocado, pero AWS WAF pide desafío JS tras unas pocas peticiones | ❌ Necesita navegador |
| Dia | API interna, Akamai responde 403 | ❌ |
| Carrefour | Cloudflare responde 403 con desafío | ❌ |
| El Corte Inglés | Akamai responde 403 | ❌ |
| Aldi, Lidl | Sin catálogo de alimentación online | ❌ |
