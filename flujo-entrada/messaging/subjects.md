# subjects

- stream: `SCRAPERS` (existe en cluster, subjects `scraper.>`)
- subject: `scraper.mercadona.raw` (1 mensaje = 1 producto)
- envelope: `{"source":"mercadona","wh":"...","ts":"...","product_id":"...","product":{...}}`
- env scraper: `NATS_URL` (def `nats://nats.messaging.svc.cluster.local:4222`), `SCRAPER_WH` (def `default`)
- consumidor durable `normalizer`: push, filtro `scraper.mercadona.raw`, deliver `deliver.normalizer` (lo crea `setup-vm.sh`; **no** es un `MessageQueueTrigger` de KEDA)
- subject salida: `scraper.mercadona.clean` (1 mensaje = 1 lote con `{"source":"normalizer","wh":"...","batch":N,"clean":"txt..."}`)
- NOTA 15/10: `MessageQueueTrigger` de Fission bloqueado (conector v0.12 vs auth JWT interna router 1.27 -> 401).
  Puente activo: `normalizer-consumer` (Deployment) NATS -> `POST router.fission/normalize` -> NATS.
