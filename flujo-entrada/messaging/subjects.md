# subjects

Resumen rápido; el contrato completo está en `docs/03-contratos-datos.md`.

- stream: `SCRAPERS`, subjects `scraper.>`, retención 7 días (con Terraform lo crea NACK en `infra/terraform/nats.tf`).
- entrada: `scraper.<cadena>.raw`, 1 mensaje = 1 producto, con `<cadena>` ∈ `mercadona`, `consum`, `caprabo`, `condis`, `bonarea`.
  - envelope: `{"source":"<cadena>","wh":"...","postal_code":"...","ts":"...","product_id":"...","product":{...}}`
  - env scraper: `NATS_URL` (def `nats://nats.messaging.svc.cluster.local:4222`), `SCRAPER_POSTAL_CODES` (def `08016`).
- consumidor durable `normalizer`: push, filtro `scraper.*.raw`, deliver `deliver.normalizer` (no es un `MessageQueueTrigger` de KEDA).
- salida: `scraper.<cadena>.clean`, 1 mensaje = 1 lote: `{"source":"normalizer","wh":"...","postal_code":"...","ts":"...","batch":N,"clean":"txt..."}`.
- consumidor durable `api-writer` (equipo de API/BD): pull, filtro `scraper.*.clean`, escribe en PostgreSQL.
- NOTA 15/10: `MessageQueueTrigger` de Fission bloqueado (conector v0.12 vs auth JWT interna router 1.27 -> 401).
  Puente activo: `normalizer-consumer` (Deployment) NATS -> `POST router.fission/normalize` -> NATS.
