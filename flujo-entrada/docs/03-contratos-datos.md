# 03 · Contratos de datos

Contratos de la frontera de ingesta. Cualquier cambio aquí afecta al equipo de API/BD.

## Mapa de subjects

```mermaid
flowchart LR
  P["scrapper_mercadona<br/>publish.py"] -->|"1 msg = 1 producto"| RAW["scraper.mercadona.raw"]
  RAW --> C["normalizer-consumer"]
  C -->|"1 msg = 1 lote"| CLEAN["scraper.mercadona.clean"]
  CLEAN --> API["API/BD"]
  RAW -.->|stream| S[("SCRAPERS<br/>subjects scraper.&gt;")]
```

| Subject | Productor | Consumidor | Granularidad |
|---|---|---|---|
| `scraper.mercadona.raw` | scraper | normalizer-consumer | 1 mensaje por producto |
| `scraper.mercadona.clean` | normalizer-consumer | **nadie todavía** | 1 mensaje por lote |

Ambos viven en el stream `SCRAPERS` (subjects `scraper.>`), que se crea con
`js.add_stream` de forma defensiva y retiene los mensajes **7 días** (`Maximum Age: 7d`,
`Discard Old`): los `clean` de esa ventana se pueden reproducir para cargarlos en BD.

## Envelope de entrada (raw)

Publicado por `publish.build_envelope()`:

```json
{
  "source": "mercadona",
  "wh": "default",
  "ts": "2026-10-15T19:20:07+00:00",
  "product_id": "12345",
  "product": { "...": "objeto tal cual lo devuelve la API de Mercadona" }
}
```

| Campo | Tipo | Origen | Notas |
|---|---|---|---|
| `source` | string | constante | Cadena de origen |
| `wh` | string | `SCRAPER_WH` | Almacén/tienda; hoy siempre `default` |
| `ts` | string | UTC, `isoformat(timespec="seconds")` | Formato `...+00:00` |
| `product_id` | string | `str(product["id"])` | Duplicado del id para indexar sin abrir `product` |
| `product` | object | crudo de la fuente | **Sin tocar**: el normalizador decide qué hacer |

> No hay versión de esquema (`schema_version`). Es un hueco a cubrir si el envelope
> evoluciona (ver [`05-pendientes.md`](05-pendientes.md)).

## Mensaje de salida (clean)

Publicado por `consumer.flush()`:

```json
{
  "source": "normalizer",
  "wh": "default",
  "ts": "2026-10-15T19:22:31+00:00",
  "batch": 50,
  "clean": "Items: 50\nUnitarios: 50 (fuente 48, calculado 2) | Incompletos: 0\n---\n12345 | Aceite de oliva 0,5 l | 4.10EUR total | 8.20EUR/l | 0.5l | Aceite | https://... | ref=8.200EUR/L src=fuente\n..."
}
```

| Campo | Tipo | Notas |
|---|---|---|
| `source` | string | Siempre `normalizer` |
| `wh` | string | **Heredado** del primer producto del lote: un lote asume un único almacén |
| `ts` | string | UTC, mismo formato que el envelope |
| `batch` | number | Nº de productos crudos del lote |
| `clean` | string | Texto plano completo del lote (cabecera + una línea por producto) |

**Decisión relevante:** `clean` viaja como **texto plano**, no como JSON estructurado. Es lo
más rápido de producir y de leer, pero obliga al consumidor a parsear por ` | `. La variante
estructurada existe ya como **opt-in** (`POST /normalize?format=json` → `CleanBatch` con
`NormalizedProduct[]`); cambiar el mensaje de `clean` a JSON es decisión del equipo de
API/BD (Prioridad 3 de [`05-pendientes.md`](05-pendientes.md#prioridad-2--modelo-pydantic)).

## Contrato de entrada de `POST /normalize`

`normalizer._unwrap()` acepta tres formas, para simplificar las pruebas:

| Cuerpo enviado | Se interpreta como |
|---|---|
| `{ "id": ..., "display_name": ... }` | un solo producto |
| `{ "product": {...} }` | un envelope; se extrae `product` |
| `{ "items": [ {...}, {...} ] }` | un lote (lo que manda el consumer) |

Los elementos ya pueden venir envueltos o pelados: `it.get("product", it)` normaliza ambos
casos. Si el cuerpo no es JSON válido → `400` con mensaje de texto.

Respuesta por defecto: `text/plain` con el resultado de `to_clean_txt()`.

Variante estructurada (**opt-in**): `POST /normalize?format=json` valida la entrada con
`RawProduct` y responde `application/json` con un `CleanBatch`
(`{source, wh, ts, batch, items[]}`; `wh`/`ts` se toman del cuerpo si vienen). Es estricta:
si un crudo no valida responde `422` (el formato de texto sigue siendo el tolerante, con
`ERROR id=...` por item). Contrato: [`05-pendientes.md`](05-pendientes.md#prioridad-2--modelo-pydantic).

## Formato de línea limpia

La línea limpia tiene exactamente este formato:

```
{pid} | {nombre} | {total}EUR total | {up}EUR/{unidad} | {size}{size_fmt} | {cat} | {url} | ref={ref}EUR/{ref_fmt} src={origen}
```

- `nombre`: `display_name` con espacios colapsados (`" ".join(...split())`).
- `{up}EUR/{unidad}`: **precio unitario canónico** (ver la sección siguiente). Si no
  se puede calcular, se emite `- (<motivo>)`.
- `ref` / `ref_fmt` / `src`: valor original de la fuente y su procedencia, para
  trazabilidad y depuración. Se dejan al final para no romper un parseo posicional.
- `cat`: **solo la primera categoría** (`categories[0].name`); el resto se pierde.
- Cabecera del lote (añadida por `to_clean_txt`): `Items: N` y
  `Unitarios: U (fuente F, calculado C) | Incompletos: I`, seguidas de `---`.
- Si un item falla: se emite `ERROR id=<id>: <mensaje>` y se sigue con el resto. Con el
  contrato Pydantic, un item que no valida deja `ERROR id=<id>: validacion: <motivos>` en
  **una sola línea**.

Ejemplo real:

```
4241 | Aceite de oliva 0,4º Hacendado | 17.25EUR total | 3.45EUR/l | 5.0l | Aceite, especias y salsas | https://tienda.mercadona.es/product/4241/... | ref=3.450EUR/L src=fuente
```

## Precio unitario canónico (€/kg · €/l · €/ud · €/m · €/lavado)

Para comparar precios entre cadenas, el precio unitario se lleva **siempre a una
unidad base**: masa → `kg`, volumen → `l`, recuento → `ud`, longitud → `m`, y la
unidad funcional `lavado` (detergentes). El formato de la fuente (`kg`, `100 g`,
`100 ml`, `dc`…) se convierte con un factor de familia.

```mermaid
flowchart TB
  A["reference_price + reference_format"] --> B{"formato conocido?"}
  B -->|"sí"| C["up = reference_price / factor<br/>src=fuente"]
  B -->|"no"| D{"¿unit_price + tamaño?"}
  D -->|"sí"| E["up = unit_price / (tamaño × factor)<br/>src=calculado"]
  D -->|"no"| F["up = None<br/>línea incompleta con motivo"]
  C --> G["línea: upEUR/base | ... | src=fuente"]
  E --> G
  F --> G
```

Reglas, en orden:

1. **La fuente manda.** Si hay `reference_price` y su `reference_format` es conocido,
   se convierte a la unidad base. `src=fuente`.
2. **Si no**, se calcula desde `unit_price` y el tamaño. `src=calculado`. En productos
   pesables con `drained_weight` (conservas, aceitunas…) se usa el **peso escurrido**
   como tamaño, porque es lo que compara la fuente.
3. **Nunca se inventa.** Si falta el precio, el tamaño o el formato no es conocido, la
   línea queda incompleta (`- (motivo)`) y se cuenta en la cabecera. `motivo` ∈
   `sin_precio`, `sin_tamano`, `formato_no_comparable:<fmt>`.

### Tabla de conversión (formatos reales de Mercadona, 15/10/2026 · 4591 productos)

| Formato (`size_format` / `reference_format`) | Familia | Unidad base | Factor (unidades base por 1 del formato) |
|---|---|---|---|
| `kg` | masa | `kg` | 1 |
| `g` | masa | `kg` | 0,001 |
| `100 g` | masa | `kg` | 0,1 |
| `l`, `L` | volumen | `l` | 1 |
| `ml` | volumen | `l` | 0,001 |
| `cl` | volumen | `l` | 0,01 |
| `100 ml` | volumen | `l` | 0,1 |
| `ud`, `u`, `ud.` | recuento | `ud` | 1 |
| `dc`, `dz` | recuento | `ud` | 12 (docena) |
| `m` | longitud | `m` | 1 |
| `lv` | funcional | `lavado` | 1 |
| cualquier otra | — | — | **no comparable → incompleto** |

> **Aviso: la base del `reference_price` no es derivable.** Mercadona calcula su
> precio de referencia sobre bases distintas según el producto: `unit_size`
> (bruto), `drained_weight` (escurrido), `total_units × pack_size` (packs) o una
> unidad funcional (`botes`, `lavados`), además de casos con `approx_size: true` y
> alguna incoherencia interna (su `bulk_price` no cuadra con `unit_price`/`unit_size`).
> Por eso el cálculo **no sustituye** a la fuente: solo actúa de respaldo cuando
> `reference_price` falta, y siempre se marca `src=calculado`. La validación
> (`test_unit_price.py`) comprueba que, en productos simples, el cálculo reproduce
> la fuente en el **99,1%** de los casos (las diferencias restantes son redondeo de
> la fuente o incoherencias propias).

## Mapeo de campos de Mercadona

```mermaid
flowchart LR
  subgraph src["API Mercadona"]
    a1["id"]
    a2["display_name"]
    a3["price_instructions.unit_price"]
    a4["price_instructions.reference_price"]
    a5["price_instructions.reference_format"]
    a6["price_instructions.unit_size"]
    a7["price_instructions.size_format"]
    a8["share_url"]
    a9["categories[0].name"]
  end
  subgraph dst["Línea limpia"]
    b1["pid"]
    b2["nombre"]
    b3["total (EUR total)"]
    b4["unit (EUR/kg·l·ud·m·lavado)"]
    b5["size + size_fmt"]
    b6["url"]
    b7["cat"]
    b8["ref + ref_fmt + src"]
  end
  a1 --> b1
  a2 --> b2
  a3 --> b3
  a4 --> b4
  a5 --> b4
  a6 --> b4
  a7 --> b4
  a6 --> b5
  a7 --> b5
  a8 --> b6
  a9 --> b7
  a4 --> b8
  a5 --> b8
```

| Campo destino | Origen | Ejemplo |
|---|---|---|
| `total` | `price_instructions.unit_price` | `4.10` (precio del envase) |
| `unit` | `reference_price ÷ factor(reference_format)`; si falta, `unit_price ÷ (tamaño × factor(size_format))` | `8.20` (EUR por unidad base) |
| `size` / `size_fmt` | `unit_size` / `size_format` | `0.5` / `l` |
| `ref` / `ref_fmt` / `src` | `reference_price` / `reference_format` / `fuente`·`calculado` | `8.200` / `L` / `fuente` |

### Estado del «cálculo de €/L o €/kg»

El plan (tarea 3) pide **"cálculo de €/L o €/kg con Pydantic"**. Hoy:

- **El cálculo está hecho** (`normalizer.unit_price`), y desde el 17/10 también el
  **contrato Pydantic** (`RawProduct`/`NormalizedProduct`/`CleanBatch` en `normalizer.py`).
  El precio unitario se **normaliza a unidad base**, no solo se copia.
- En Mercadona el respaldo rara vez se usa (la fuente siempre trae `reference_price`),
  pero es lo que cubrirá a las cadenas que **no** den ese campo (Alcampo, Ahorramás).
- Falta desplegar pydantic en el entorno de Fission (imagen con pydantic) → ver
  [`05-pendientes.md`](05-pendientes.md#prioridad-2--modelo-pydantic).
