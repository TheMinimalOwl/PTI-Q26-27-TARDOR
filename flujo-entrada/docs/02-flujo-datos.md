# 02 · Flujo de datos

## Secuencia end-to-end

```mermaid
sequenceDiagram
  autonumber
  participant CJ as CronJob scraper-mercadona
  participant MD as API Mercadona
  participant FS as out/*.txt (dentro del pod)
  participant NATS as NATS JetStream
  participant CONS as normalizer-consumer
  participant RT as Router Fission
  participant FN as Function normalizer

  Note over CJ,NATS: kube crea el Pod a las 02:00 (schedule 0 2 * * *)

  CJ->>MD: GET /api/categories/
  MD-->>CJ: { results: [ familias → subcategorías ] }

  loop por cada subcategoría (sleep 0.3 s entre llamadas)
    CJ->>MD: GET /api/categories/{id}/
    MD-->>CJ: { categories: [ { products: [ ...crudos... ] } ] }
  end

  CJ->>CJ: collect_raw() → items[] + errores[]
  CJ->>FS: dump(mercadona_<ts>.txt)
  loop 1 mensaje por producto con "id"
    CJ->>NATS: publish scraper.mercadona.raw (envelope)
  end

  Note over NATS,CONS: cola push deliver.normalizer (filtro scraper.mercadona.raw)

  NATS-->>CONS: entrega de mensajes
  Note over CONS: búfer: vuelca al llegar a 50 o cada 5 s
  CONS->>RT: POST /normalize { items: [ ...crudos... ] }
  RT->>FN: invoca normalizer.main
  FN-->>RT: "pid | nombre | precio | ... " (text/plain)
  RT-->>CONS: 200 text/plain

  CONS->>NATS: publish scraper.mercadona.clean { batch, clean }
  CONS->>NATS: ack de todo el lote
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
  EnBuffer --> EnBuffer: flush-error → sin ack → reentrega (AckWait)
  EnBuffer --> Normalizado: POST /normalize (lote de hasta 50)
  Normalizado --> Limpio: publish scraper.mercadona.clean
  Limpio --> [*]: lo consume API/BD (frontera con otro equipo)
```

Estados y su significado:

| Estado | Dónde vive | Forma del dato |
|---|---|---|
| Crudo | Memoria del pod | dict tal cual lo da la API de Mercadona |
| Extraído | Memoria del pod | lista `items[]` aplanada |
| Volcado | `out/mercadona_<ts>.txt` (efímero) | texto `raw: {...}` por línea |
| Publicado | NATS `scraper.mercadona.raw` | envelope con `product` crudo |
| En búfer | Memoria del consumer | lista de envelopes |
| Normalizado | Respuesta HTTP de Fission | texto plano (`to_clean_txt`) con precio unitario canónico |
| Limpio | NATS `scraper.mercadona.clean` | un mensaje por **lote** con `clean` |

## Cadencia temporal

```mermaid
gantt
  title Ciclo diario (esquema, no ejecución real)
  dateFormat HH:mm
  axisFormat %H:%M
  section Mercadona
  Job del scraper        :02:00, 15m
  section Consumer
  Escucha continua       :00:00, 24h
```

- **Mercadona**: una ejecución diaria a las 02:00, en serie (`Forbid`).
- **normalizer-consumer**: Deployment siempre arriba; no depende del CronJob, solo consume
  lo que llegue a NATS.

## Flujo mínimo de punta a punta

El plan (tarea 4) define como hito: **1 cadena → BD → API → app**. Hoy está cubierto hasta
la parte intermedia:

```
✅ 1 cadena (Mercadona) → ✅ NATS → ✅ normalizer → ✅ NATS clean
❌ BD        (otro equipo, no existe todavía)
❌ API       (otro equipo)
❌ app       (otro equipo)
```

Comprobado en el clúster el **17/10/2026** con el normalizer ya con el contrato Pydantic: un
disparo manual publicó **4592 productos** y el consumer los normalizó en **92 lotes**
(4592 sin perder ninguno). Detalle y mensaje `clean` de ejemplo:
[`04-estados-y-errores.md`](04-estados-y-errores.md#verificación-end-to-end-17102026).

El flujo actual es **byte-in / texto-out**: entra JSON crudo y sale texto formateado con el
**precio unitario ya normalizado** a una unidad base (`€/kg`, `€/l`, `€/ud`, `€/m`,
`€/lavado`). Mercadona ya trae el precio de referencia, así que se respeta el de la fuente;
cuando no lo traiga, el normalizador lo calcula (ver
[`03-contratos-datos.md`](03-contratos-datos.md#precio-unitario-canónico-€kg--€l--€ud--€m--€lavado)).
