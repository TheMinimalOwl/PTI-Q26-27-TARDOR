# 02 · Flujo de datos

## Secuencia end-to-end

```mermaid
sequenceDiagram
  autonumber
  participant CJ as CronJob scraper-mercadona
  participant MD as API Mercadona
  participant FS as out/*.txt (PVC scraper-out)
  participant NATS as NATS JetStream
  participant CONS as normalizer-consumer
  participant RT as Router Fission
  participant FN as Function normalizer
  participant WR as writer de API/BD
  participant PG as PostgreSQL

  Note over CJ,NATS: kube crea el Pod a las 02:00 (schedule 0 2 * * *)

  CJ->>MD: GET /api/categories/
  MD-->>CJ: { results: [ familias → subcategorías ] }

  loop por cada subcategoría (sleep 0.3 s entre llamadas)
    CJ->>MD: GET /api/categories/{id}/
    MD-->>CJ: { categories: [ { products: [ ...crudos... ] } ] }
  end

  CJ->>CJ: collect_raw() → items[] (+ errors[] de subcategorías)
  CJ->>FS: dump(mercadona_<wh>_<ts>.txt)
  loop 1 mensaje por producto con "id"
    CJ->>NATS: publish scraper.mercadona.raw (envelope)
  end

  Note over NATS,CONS: cola push deliver.normalizer (filtro scraper.*.raw)

  NATS-->>CONS: entrega de mensajes
  Note over CONS: búfer: vuelca al llegar a 50 o cada 5 s
  CONS->>RT: POST /normalize { items: [ ...crudos... ] }
  RT->>FN: invoca normalizer.main
  FN-->>RT: "pid | nombre | precio | ... " (text/plain)
  RT-->>CONS: 200 text/plain

  CONS->>NATS: publish scraper.mercadona.clean { batch, clean }
  CONS->>NATS: ack de todo el lote

  Note over NATS,WR: durable api-writer (pull, filtro scraper.*.clean)
  WR->>NATS: fetch(10)
  NATS-->>WR: lotes clean
  WR->>PG: upsert cadena, tienda (wh), productos y precio del día
  WR->>NATS: ack tras el commit
```

## Ciclo de vida de un producto

```mermaid
stateDiagram-v2
  [*] --> Crudo
  Crudo --> Extraido: collect_raw() en el scraper
  Extraido --> Volcado: dump_txt() · respaldo de depuración
  Extraido --> Publicado: tiene "id" → publish()
  Extraido --> Descartado: sin "id" o pseudo-item _errors
  Descartado --> [*]

  Publicado --> EnBuffer: deliver.normalizer
  EnBuffer --> EnBuffer: publish falla → sin ack → reentrega (AckWait)
  EnBuffer --> Normalizado: POST /normalize (lote de hasta 50)
  Normalizado --> Limpio: publish scraper.mercadona.clean
  Limpio --> EnBD: durable api-writer → upsert (equipo de API/BD)
  EnBD --> [*]
```

Estados y su significado:

| Estado | Dónde vive | Forma del dato |
|---|---|---|
| Crudo | Memoria del pod | dict tal cual lo da la API de Mercadona |
| Extraído | Memoria del pod | lista `items[]` aplanada |
| Volcado | `out/mercadona_<wh>_<ts>.txt` en el PVC `scraper-out` (se borra a los 7 días) | texto `raw: {...}` por línea |
| Publicado | NATS `scraper.mercadona.raw` | envelope con `product` crudo |
| En búfer | Memoria del consumer | lista de envelopes |
| Normalizado | Respuesta HTTP de Fission | texto plano (`to_clean_txt`) con precio unitario canónico |
| Limpio | NATS `scraper.mercadona.clean` | un mensaje por **lote** con `clean` |
| En BD | PostgreSQL (namespace `api`) | filas en `products` y `prices`: un precio por producto, tienda y día |

## Cadencia temporal

```mermaid
gantt
  title Ciclo diario (esquema, no ejecución real)
  dateFormat HH:mm
  axisFormat %H:%M
  section Mercadona
  Job del scraper        :02:00, 2m
  section Consum
  Job del scraper        :02:00, 10m
  section Caprabo
  Job del scraper        :02:00, 60m
  section Condis
  Job del scraper        :02:00, 2m
  section bonÀrea
  Job del scraper        :02:00, 18m
  section Consumer y writer
  Escucha continua       :00:00, 24h
```

- **Mercadona**, **Consum**, **Caprabo**, **Condis** y **bonÀrea**: una ejecución diaria a
  las 02:00 **hora de Madrid** (`timeZone: Europe/Madrid`), cada uno en serie consigo mismo
  (`Forbid`). Corren a la vez: el consumer agrupa los lotes por cadena. Caprabo es el más
  lento (~1 h, una página por categoría con 3 s de pausa); Condis, el más rápido (~20
  peticiones).
- **Histórico:** la BD guarda un precio por producto, tienda y día
  (`prices(product_id, store_id, observed_on)`), así que cada noche añade un día al
  histórico. Si un scraper se relanza el mismo día, se actualiza ese día, no se duplica.
- El flujo de cada producto es el mismo para todas las cadenas; arriba se usa Mercadona como
  ejemplo.
- **normalizer-consumer** y **writer**: Deployments siempre arriba; no dependen de los
  CronJobs, solo consumen lo que llegue a NATS.
