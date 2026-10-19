# scrappers

Recolectores crudos. Sin normalización.

- Cada scraper solo extrae datos tal cual de la web y los vuelca a `txt`.
- Normaliza Fission, no el scraper.
- Hoy solo **Mercadona** está activo: publica en NATS (`scraper.mercadona.raw`) además del
  `txt`. El scraper de Carrefour existe pero está bloqueado por Cloudflare (ver su README).
