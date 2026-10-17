# 04 · Estados, errores y reintentos

## Taxonomía de fallos

```mermaid
flowchart TB
  START(["Ejecución del scraper"]) --> NET{"¿Falla la red<br/>o timeout?"}
  NET -->|"sí (RequestException)"| F1["status = None<br/>→ 0 items"]
  NET -->|"no"| HTTP{"¿status != 200?"}
  HTTP -->|"sí (403/404/500)"| F2["se acumula en errors[]<br/>→ 0 items de esa subcategoría"]
  HTTP -->|"200"| OK["items[] extraídos"]
  OK --> DUMP["dump txt"]
  DUMP --> PUB{"¿NATS disponible?"}
  PUB -->|"no"| F3["publish = 0<br/>job termina OK ← fallo silencioso"]
  PUB -->|"sí"| F4["publicado en scraper.mercadona.raw"]
  F1 --> DUMP
  F2 --> DUMP
```

## Comportamiento por capa

| Capa | Fallo | Reacción | ¿Pierde datos? |
|---|---|---|---|
| `client.fetch_json` | Timeout / error de red | Devuelve `(None, {})`; se cuenta como error | Sí, esa subcategoría |
| `client.fetch_json` | HTTP != 200 | Devuelve `(status, {})` | Sí, esa subcategoría |
| `main` | Alguna subcategoría falla | Acumula en `errors[]` y añade un pseudo-item `{"_errors": [...]}` | Solo lo fallado |
| `main` | Todas fallan | `status != 200`, se vuelca `ERROR status=...` | Todo |
| `dump_txt` | — | Escribe siempre; es el respaldo | No |
| `publish` | NATS caído | `try/except` → devuelve `0` y log `ERROR NATS (...), txt intacto` | **Sí, silenciosamente** |
| `normalizer` | Campo ausente | `.get()` con defecto `-` | Degrada la línea, no rompe |
| `normalizer` | Precio unitario no calculable (sin precio, sin tamaño o formato no comparable) | Línea con `- (motivo)` y contador `Incompletos` en la cabecera | Degrada la línea, no rompe |
| `normalizer` | Sin `reference_price` en la fuente | Calcula el precio unitario desde `unit_price`/tamaño (`src=calculado`) | No (respaldo aproximado) |
| `normalizer` | Item corrupto | `try/except` → línea `ERROR id=...` | Solo ese item |
| `consumer` | JSON ilegible | Log `parse-error`, **ack** y descarta | Sí, ese mensaje |
| `consumer` | Router Fission caído | Log `flush-error`, **sin ack** → reentrega por `AckWait` | No (pero duplica) |

## Semántica de reintentos

```mermaid
stateDiagram-v2
  [*] --> Publicado
  Publicado --> SinAck: el consumer falla al publicar el lote
  SinAck --> Reentregado: AckWait expira
  Reentregado --> Publicado: nueva entrega (posible duplicado)
  Publicado --> Confirmado: publish OK → ack de todo el lote
  Confirmado --> [*]

  state SinAck {
    note right of SinAck: El búfer NO se vacía en el fallo<br/>rebota entero en el siguiente flush
  }
```

| Mecanismo | Configuración | Efecto |
|---|---|---|
| NATS JetStream | `AckWait` por defecto | Redelivery de lotes no confirmados |
| `consumer` | `CONSUMER_BATCH=50`, flush cada 5 s | Cotas del búfer en condiciones normales |
| `consumer` | `ack` tras publicar | Entrega **at-least-once** → posibles duplicados |
| CronJob | `concurrencyPolicy: Forbid` | Sin solape de ejecuciones |
| CronJob | `backoffLimit: 2` | 2 reintentos del Pod antes de marcar Job fallido |
| CronJob | `restartPolicy: OnFailure` | Reinicio del contenedor dentro del Pod |

## Riesgos detectados en el diseño actual

1. **Fallo silencioso del scraper.** `main.py` nunca devuelve código de salida distinto de
   0. Si NATS está caído, el Job se marca como **exitoso** y los datos solo quedan en un
   `.txt` dentro de un Pod que se destruye. No hay alarma ni reingesta.
2. **Búfer sin cota.** En `flush()`, `buf.clear()` va después del `publish`; si este falla,
   el búfer conserva todo y sigue creciendo con cada reentrega. Un fallo prolongado de
   Fission puede agotar la memoria del consumer.
3. **Sin idempotencia.** Nada deduplica por `product_id`. Una reentrega del mismo mensaje
   produce líneas repetidas en `scraper.mercadona.clean`.
4. **`wh` a nivel de lote.** `consumer.flush()` toma el `wh` del **primer** producto del
   lote y lo aplica a todo. Hoy todos los productos son `default`, pero al introducir
   multi-tienda el etiquetado sería incorrecto.
5. **Sin `Service` para los scrapers.** El `Ingress` del repo apunta a Services
   inexistentes. Además, los scrapers son CronJobs (batch), no exponen puertos: el Ingress
   parece un resto de una idea anterior.
6. **Sin observabilidad.** No hay métricas ni logs estructurados; solo `print()` en el
   consumer y en el scraper. Los fallos del punto 1 son invisibles.

## Escenarios límite

| Escenario | Comportamiento esperado hoy |
|---|---|
| Mercadona cambia su JSON | Líneas con `-` en los campos que falten; el lote sigue |
| Mercadona añade un `size_format`/`reference_format` nuevo | Ese producto queda con precio unitario incompleto (`- (formato_no_comparable:...)`); el resto sigue |
| Mercadona bloquea temporalmente | `status` != 200 → 0 items → Job "exitoso" sin datos |
| NATS caído durante el CronJob | Datos solo en el `.txt` efímero → se pierden con el Pod |
| Fission caído un rato | Reentrega por `AckWait`; búfer creciendo; duplicados al recuperar |
| Llegan productos de dos tiendas | El lote entero se etiqueta con el `wh` del primero |
| Un producto sin `id` | Se descarta en `publish` (no se publica); sí aparece en el `.txt` |
