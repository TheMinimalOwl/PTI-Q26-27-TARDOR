# scrappers

Recolectores crudos. Sin normalización.

- Cada scraper solo extrae datos tal cual de la web y los vuelca a `txt`.
- Normaliza Fission, no el scraper.
- Activos: **Mercadona** (`scraper.mercadona.raw`), **Consum** (`scraper.consum.raw`) y
  **Caprabo** (`scraper.caprabo.raw`) , **Condis** (`scraper.condis.raw`) y **bonÀrea** (`scraper.bonarea.raw`). Todos publican en NATS además del `txt` y se ejecutan a las 02:00
  (hora de Madrid).
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
| Caprabo | HTML renderizado en servidor, sin antibot | ✅ Activo (`scrapper_caprabo`) |
| Eroski, Familia | Misma web que Caprabo (País Vasco/Navarra, Asturias) | ⏸️ Fuera de esta tanda: no reparten en Cataluña |
| BM Supermercados | Misma API JSON que Consum (Aktios); País Vasco, Navarra, Madrid | 🟡 Viable, no reparte en Cataluña |
| Condis | API JSON pública del buscador Empathy.co (`api.empathy.co/search/v1/query/condis`), sin antibot | ✅ Activo (`scrapper_condis`) |
| Veritas | API GraphQL de Magento abierta (`/graphql`), ~5.000 productos; sin precio por unidad | 🟡 Viable |
| bonÀrea | JSON interno de la web (`POST /ca/shop/ShoppingBody`), encontrado con Playwright; sin antibot ni `robots.txt` | ✅ Activo (`scrapper_bonarea`) |
| Ametller Origen | Salesforce Commerce (PWA Kit); no expone su clave de acceso | 🟡 Difícil |
| Bonpreu/Esclat | API JSON de Ocado; `robots.txt` prohíbe `/api/` | ❌ AWS WAF tras ~6 peticiones; con Playwright, CloudFront 403 en las categorías (11/11) |
| Alcampo | API JSON de Ocado, pero AWS WAF pide desafío JS tras unas pocas peticiones | ❌ Bloquea también Playwright (CloudFront 403, 11/11) |
| Dia | API interna, Akamai responde 403 | ❌ Bloquea también Playwright (Akamai «Access Denied», 11/11) |
| Carrefour | Cloudflare responde 403 con desafío | ❌ Bloquea también Playwright (Cloudflare «Attention Required», 11/11) |
| El Corte Inglés | Akamai responde 403 | ❌ |
| Aldi, Lidl | Sin catálogo de alimentación online | ❌ |
