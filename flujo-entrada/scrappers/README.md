# scrappers

Recolectores crudos. Sin normalización.

- Cada scraper solo extrae datos tal cual de la web y los vuelca a `txt`.
- Normaliza Fission, no el scraper.
- Activos: **Mercadona** (`scraper.mercadona.raw`), **Consum** (`scraper.consum.raw`) y
  **Caprabo** (`scraper.caprabo.raw`) y **Condis** (`scraper.condis.raw`). Todos publican en NATS además del `txt` y se ejecutan a las 02:00
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
| bonÀrea | Los productos se cargan aparte del HTML; sin API a la vista | 🟡 Requiere más investigación |
| Ametller Origen | Salesforce Commerce (PWA Kit); no expone su clave de acceso | 🟡 Difícil |
| Bonpreu/Esclat | API JSON de Ocado; `robots.txt` prohíbe `/api/` | ❌ AWS WAF tras ~6 peticiones (comprobado el 11/11) |
| Alcampo | API JSON de Ocado, pero AWS WAF pide desafío JS tras unas pocas peticiones | ❌ Necesita navegador |
| Dia | API interna, Akamai responde 403 | ❌ |
| Carrefour | Cloudflare responde 403 con desafío | ❌ |
| El Corte Inglés | Akamai responde 403 | ❌ |
| Aldi, Lidl | Sin catálogo de alimentación online | ❌ |
