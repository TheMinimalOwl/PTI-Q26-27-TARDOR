# subjects

- stream: `SCRAPER`
- subject: `mercadona.raw` (1 mensaje = 1 producto)
- envelope: `{"source":"mercadona","wh":"...","ts":"...","product_id":"...","product":{...}}`
- env scraper: `NATS_URL` (def `nats://nats.messaging.svc.cluster.local:4222`), `SCRAPER_WH` (def `default`)
