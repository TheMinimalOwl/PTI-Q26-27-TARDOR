# subjects

- stream: `SCRAPERS` (existe en cluster, subjects `scraper.>`)
- subject: `scraper.mercadona.raw` (1 mensaje = 1 producto)
- envelope: `{"source":"mercadona","wh":"...","ts":"...","product_id":"...","product":{...}}`
- env scraper: `NATS_URL` (def `nats://nats.messaging.svc.cluster.local:4222`), `SCRAPER_WH` (def `default`)
- consumer KEDA: `normalizer` (pull, durable, filter `scraper.mercadona.raw`)
