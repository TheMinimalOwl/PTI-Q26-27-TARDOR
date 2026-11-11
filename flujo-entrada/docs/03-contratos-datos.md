# 03 · Contratos de datos

Contratos de la frontera de ingesta. Cualquier cambio aquí afecta al equipo de API/BD.

## Mapa de subjects

```mermaid
flowchart LR
  P["scrapper_mercadona<br/>publish.py"] -->|"1 msg = 1 producto"| RAW["scraper.mercadona.raw"]
  P2["scrapper_consum<br/>publish.py"] -->|"1 msg = 1 producto"| RAW2["scraper.consum.raw"]
  RAW --> C["normalizer-consumer"]
  RAW2 --> C
  C -->|"1 msg = 1 lote"| CLEAN["scraper.mercadona.clean"]
  C -->|"1 msg = 1 lote"| CLEAN2["scraper.consum.clean"]
  CLEAN2 --> API
  CLEAN -->|"durable api-writer (pull)"| API["writer de API/BD<br/>→ PostgreSQL"]
  RAW -.->|stream| S[("SCRAPERS<br/>subjects scraper.&gt;")]
  CLEAN -.->|stream| S
```

| Subject | Productor | Consumidor | Granularidad |
|---|---|---|---|
| `scraper.mercadona.raw` | scraper de Mercadona | `normalizer-consumer` (durable `normalizer`) | 1 mensaje por producto |
| `scraper.consum.raw` | scraper de Consum | `normalizer-consumer` (durable `normalizer`) | 1 mensaje por producto |
| `scraper.mercadona.clean` | `normalizer-consumer` | writer de API/BD (durable `api-writer`) | 1 mensaje por lote |
| `scraper.consum.clean` | `normalizer-consumer` | writer de API/BD (durable `api-writer`) | 1 mensaje por lote |

El consumer agrupa los lotes **por cadena** (nunca mezcla dos cadenas en un lote) y publica
cada uno en el `clean` de la cadena de la que vino: `scraper.<cadena>.raw` →
`scraper.<cadena>.clean`.

Ambos viven en el **mismo** stream `SCRAPERS` (subjects `scraper.>`): no hay un stream
aparte para la salida. Lo crea Terraform con NACK (`infra/terraform/nats.tf`) o
`setup-vm.sh` en el montaje a mano; `publish.py` además lo crea de forma defensiva si falta
(`js.add_stream`). Retiene los mensajes **7 días** (`Maximum Age: 7d`, `Discard Old`) con
`Duplicate Window: 2m`, así que la salida aguanta 7 días aunque nadie la lea.

## Cola de salida (frontera con API/BD)

La salida de la ingesta es el subject `scraper.<cadena>.clean` dentro de `SCRAPERS`. Cada
lado es dueño de una parte:

| Pieza | Dueño | Dónde se define |
|---|---|---|
| Stream `SCRAPERS` (nombre, subjects `scraper.>`, retención 7 d) | Ingesta | `infra/terraform/nats.tf` (`kubectl_manifest.stream`) |
| Publicar `scraper.<cadena>.clean` con el formato de [Mensaje de salida](#mensaje-de-salida-clean) | Ingesta | `fission/normalizer/consumer.py` (`NATS_SUBJECT_OUT`) |
| Consumidor durable `api-writer` sobre `scraper.*.clean` | API/BD | Lo crea el propio writer al arrancar (`api/app/writer.py`) |
| Escribir en PostgreSQL | API/BD | `api/app/ingest.py` (`upsert_batch`) |

Consumidores durables del stream:

| Durable | Tipo | Filtro | Quién lo crea | Ack |
|---|---|---|---|---|
| `normalizer` | push → `deliver.normalizer` | `scraper.*.raw` | Ingesta (NACK, `nats.tf`) | Explícito, `AckWait 30s`, `MaxAckPending 1000` |
| `api-writer` | pull (`fetch(10)`) | `scraper.*.clean` | API/BD (`js.pull_subscribe`) | Tras el commit en BD; `nak(delay=10)` si falla la BD; `term()` si el mensaje está mal formado |

Garantías que da la frontera:

- **No se pierde nada si el writer arranca tarde o cae.** El durable guarda su posición en
  NATS y el stream conserva los lotes 7 días. Por eso el orden de despliegue entre ingesta y
  API no importa, siempre que el stream exista.
- **Entrega at-least-once.** Un lote puede llegar dos veces (reentrega del normalizador o
  del writer). La carga en BD es idempotente: el precio tiene clave única
  `(product_id, store_id, observed_on)` y se hace *upsert*, así que una reentrega el mismo
  día no duplica filas.
- **La cadena sale del subject**, no del cuerpo: `scraper.mercadona.clean` → `mercadona`.
  Una cadena nueva solo tiene que publicar en `scraper.<cadena>.clean`; el filtro
  `scraper.*.clean` del writer ya la recoge.
- **Punto de conexión:** `nats://nats.messaging.svc.cluster.local:4222` (dentro del clúster,
  `api/k8s/configmap.yaml`).

Qué rompería el contrato y hay que avisar antes al equipo de API/BD: renombrar el stream,
cambiar el patrón de subjects, quitar `clean` o `items` del mensaje, cambiar el orden de los
campos de la línea limpia o bajar la retención por debajo del tiempo que el writer pueda
estar parado.

Para mirar la cola de salida a mano:

```bash
kubectl -n messaging exec deploy/nats-box -- nats -s nats://nats:4222 stream subjects SCRAPERS
kubectl -n messaging exec deploy/nats-box -- nats -s nats://nats:4222 consumer info SCRAPERS api-writer
```

## Código postal y tienda

Las dos cadenas deciden **qué productos** se venden según el código postal del cliente: cada
código postal lo sirve una tienda o almacén con su propio surtido. En las pruebas
(11/11/2026) el precio de un mismo producto **no** cambiaba entre zonas, pero el catálogo sí
(Consum: 8.611 productos en Barcelona, 9.581 en Valencia).

Por eso los scrapers no recorren "el catálogo", sino **el catálogo de la tienda que sirve
cada código postal**:

| Cadena | Código postal → tienda | Cómo se pide el catálogo de esa tienda | Ejemplo con 08016 |
|---|---|---|---|
| Mercadona | `PUT /api/postal-codes/actions/change-pc/` `{"new_postal_code": "08016"}` → cabecera `x-customer-wh` | `?lang=es&wh=bcn1` en cada petición | `wh=bcn1` |
| Consum | `GET /api/rest/V1.0/shipping/area?zipCode=08016` → zona de reparto a domicilio | Cabeceras `X-TOL-ZONE: 378` y `X-TOL-SHIPPING-ZONE: 378D` | `wh=378` (tienda "Centro 378", Barcelona) |

- Varios códigos postales que caen en la misma tienda se recorren **una sola vez**.
- Si una cadena no da servicio en un código postal (Consum no reparte en Madrid ni Sevilla),
  ese código se salta con un aviso en el log; no es un error.
- `wh` es el código de tienda **de cada cadena**: en la BD de la API es `stores.code`, único
  por cadena (`bcn1` de Mercadona y `378` de Consum son dos tiendas distintas).

**De dónde salen los códigos postales.** La idea es que los dé la app: el usuario indica su
código postal y la API lo guarda. Mientras eso no existe, se usa **08016** de ejemplo:

- Con Terraform: variable `postal_codes` (lista, por defecto `["08016"]`), que se copia a la
  variable de entorno `SCRAPER_POSTAL_CODES` de los dos CronJobs.
- Sin Terraform: `SCRAPER_POSTAL_CODES` en cada `cronjob.yaml` (separados por comas).

Propuesta de contrato para cuando la API lo implemente (a acordar con el equipo de API/BD):
un endpoint interno, p. ej. `GET /internal/postal-codes` → `["08016", "46001"]`, con los
códigos postales distintos de los usuarios. Los scrapers lo leerían al empezar cada pasada
en lugar de la variable de entorno. Cada código postal nuevo que aparezca significa, como
mucho, una tienda más por cadena y por noche.

## Envelope de entrada (raw)

Publicado por `publish.build_envelope()`:

```json
{
  "source": "mercadona",
  "wh": "bcn1",
  "postal_code": "08016",
  "ts": "2026-10-15T19:20:07+00:00",
  "product_id": "12345",
  "product": { "...": "objeto tal cual lo devuelve la API de Mercadona" }
}
```

| Campo | Tipo | Origen | Notas |
|---|---|---|---|
| `source` | string | constante | Cadena de origen |
| `wh` | string | resuelto desde el código postal | Tienda o almacén de la cadena que sirve ese código postal: `bcn1` (Mercadona), `378` (Consum). Ver [Código postal y tienda](#código-postal-y-tienda) |
| `postal_code` | string | `SCRAPER_POSTAL_CODES` | Código postal del que salió `wh` |
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
  "wh": "bcn1",
  "postal_code": "08016",
  "ts": "2026-10-15T19:22:31+00:00",
  "batch": 50,
  "clean": "Items: 50\nUnitarios: 50 (fuente 48, calculado 2) | Incompletos: 0\n---\n12345 | Aceite de oliva 0,5 l | 4.10EUR total | 8.20EUR/l | 0.5l | Aceite | https://... | ref=8.200EUR/L src=fuente\n..."
}
```

| Campo | Tipo | Notas |
|---|---|---|
| `source` | string | Siempre `normalizer` |
| `wh` | string | Tienda/almacén del lote. El consumer agrupa por cadena **y** `wh`, así que un lote nunca mezcla tiendas |
| `postal_code` | string | Código postal del que salió `wh` (trazabilidad; el writer de API/BD puede ignorarlo) |
| `ts` | string | UTC, mismo formato que el envelope |
| `batch` | number | Nº de productos crudos del lote |
| `clean` | string | Texto plano completo del lote (cabecera + una línea por producto) |

**Decisión relevante:** `clean` viaja como **texto plano**, no como JSON estructurado. Es lo
más rápido de producir y de leer, pero obliga al consumidor a parsear por ` | `. La variante
estructurada existe ya como **opt-in** (`POST /normalize?format=json` → `CleanBatch` con
`NormalizedProduct[]`).

El writer de API/BD (`api/app/ingest.py`, `parse_message`) **ya acepta las dos formas**: si
el mensaje trae `items` lo usa directamente (la preferida), y si trae `clean` lo parsea línea
a línea por ` | `. Así que pasar la salida a `CleanBatch` no rompe al writer, pero sí cambia
el contrato: se acuerda antes con API/BD (ver
[`05-pendientes.md`](05-pendientes.md#prioridad-3--contrato-con-apibd)). Si se hace, conviene
publicar los dos campos (`clean` e `items`) durante una transición.

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
`ERROR id=...` por item). Contrato: [Contrato Pydantic](#contrato-pydantic).

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

## Mapeo de campos de Consum

Consum no tiene la forma de Mercadona. En vez de cambiar el resto del normalizador, una
función `from_consum()` traduce el crudo a la forma común (la de Mercadona) y todo lo demás
(precio unitario canónico, línea limpia, contrato Pydantic) es igual. La cadena se detecta
por la forma del objeto (`productData` + `priceData`), así que el scraper publica el crudo
tal cual.

| Forma común | Consum | Ejemplo |
|---|---|---|
| `id` | `code` (id público, el de la URL; `id` es interno) | `"1669"` |
| `display_name` | `productData.name` | `Rabanito Bolsa` |
| `price_instructions.unit_price` | `centAmount` del precio vigente: `OFFER_PRICE` si hay oferta, si no `PRICE` (en euros, pese al nombre) | `1.3` |
| `price_instructions.reference_price` | `centUnitAmount` del mismo precio | `5.2` |
| `price_instructions.reference_format` | `unitPriceUnitType` sin el `1 ` inicial | `1 Kg` → `Kg` |
| `price_instructions.unit_size` / `size_format` | Final de `productData.description`; `N x tamaño` en packs; si no hay, se omite (`-`) | `250 Gr` → `250` / `Gr` |
| `share_url` | `productData.url` | `https://tienda.consum.es/es/p/rabanito-bolsa/1669` |
| `categories[0].name` | `categories[0].name` | `Zanahorias y otras raíces` |

Formatos de `unitPriceUnitType` vistos (11/11/2026, 9.354 productos) y su unidad base:
`1 Kg` (4.758) → kg, `1 L` (1.695) → l, `1 U` (1.614) → ud, `100 ml` (942) → l,
`100 Gr` (204) → kg, `1 Lv` (111) → lavado, `1 Dc` (14) → ud (docena), `1 M` (8) → m y
`1 Do` (8, dosis: pastillas de lavavajillas, bolsitas) → ud.

Todos traen precio por unidad, así que **el 100 % sale con `src=fuente`** y ninguno queda
incompleto. Ejemplo de línea limpia:

```
1669 | Rabanito Bolsa | 1.30EUR total | 5.20EUR/kg | 250Gr | Zanahorias y otras raíces | https://tienda.consum.es/es/p/rabanito-bolsa/1669 | ref=5.2EUR/Kg src=fuente
```

`ean` viaja en el crudo pero **no** en la línea limpia: añadirlo cambia el contrato con
API/BD (ver [`05-pendientes.md`](05-pendientes.md)).

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

## Contrato Pydantic

El plan (tarea 3) pide Pydantic explícitamente. El contrato vive en
`fission/normalizer/normalizer.py`, en el mismo fichero que la función (Fission se sube como
una única fuente con `fission fn create|update --code normalizer.py`, y el consumer reutiliza
el módulo). Los modelos **envuelven** `normalize_record()` con tipos y validación, **sin
rehacer la lógica**: separan la entrada (crudo de la cadena, tolerante) de la salida (línea
ya normalizada, estricta).

```mermaid
classDiagram
  class RawProduct {
    +str id
    +str display_name
    +PriceInstructions price_instructions
    +str share_url
    +list~Category~ categories
  }
  class PriceInstructions {
    +Decimal unit_price
    +Decimal reference_price
    +str reference_format
    +Decimal unit_size
    +str size_format
    +Decimal drained_weight
  }
  class Category {
    +str name
  }
  class NormalizedProduct {
    +str id
    +str name
    +Decimal total
    +Decimal unit_price
    +str unit
    +str unit_src
    +str unit_reason
    +Any ref
    +str ref_format
    +Any size
    +str size_format
    +str category
    +str url
  }
  class CleanBatch {
    +str source
    +str wh
    +str ts
    +int batch
    +list~NormalizedProduct~ items
  }
  RawProduct --> PriceInstructions
  RawProduct --> Category
  NormalizedProduct ..> RawProduct : normalize_record()
  CleanBatch --> NormalizedProduct
```

### Entrada (cruda, tolerante)

Mercadona manda muchos más campos de los que se usan. El modelo declara **solo** los que
consume el normalizador y **ignora el resto** (`extra="ignore"`): un campo nuevo en la
fuente no rompe la ingesta.

```python
from decimal import Decimal
from typing import Annotated, Any, Literal
from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator,
)

# Reutiliza _dec() de normalizer.py: admite coma decimal y rechaza NaN/Inf/''.
Dec = Annotated[Decimal, BeforeValidator(_dec)]
# Mercadona manda `id` como numero: se coacciona a str (mismo criterio que str(...)).
Id = Annotated[str, BeforeValidator(lambda v: v if isinstance(v, str) else str(v))]


class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""


class PriceInstructions(BaseModel):
    """Solo los campos que usa unit_price(); el resto (bulk_price, pack_size,
    approx_size, total_units...) se ignora a proposito."""
    model_config = ConfigDict(extra="ignore")

    unit_price: Dec | None = None        # precio del envase (total)
    reference_price: Dec | None = None   # base de la fuente, si la trae
    reference_format: str = ""
    unit_size: Dec | None = None
    size_format: str = ""
    drained_weight: Dec | None = None    # peso escurrido (pesables)


class RawProduct(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Id
    display_name: str = ""
    price_instructions: PriceInstructions = Field(default_factory=PriceInstructions)
    share_url: str = ""
    categories: list[Category] = Field(default_factory=list)
```

### Salida (normalizada, estricta)

Refleja **exactamente** los campos que devuelve `normalize_record()` con tipos y validación:

```python
UnitBase = Literal["kg", "l", "ud", "m", "lavado"]  # debe seguir a UNITS en normalizer.py
UnitSrc = Literal["fuente", "calculado", "-"]


class NormalizedProduct(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Id
    name: str
    total: Dec | None
    unit_price: Dec | None
    unit: UnitBase | None
    unit_src: UnitSrc
    unit_reason: str = ""            # "", sin_precio, sin_tamano, formato_no_comparable:<fmt>
    ref: Any = None                  # crudo de la fuente ("-", numero o texto) -> trazabilidad
    ref_format: str = ""
    size: Any = None                 # crudo de la fuente
    size_format: str = ""
    category: str = ""
    url: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def _collapse(cls, v: Any) -> str:
        return " ".join(str(v or "").split())

    @model_validator(mode="after")
    def _coherente(self) -> "NormalizedProduct":
        if self.unit_price is None:
            if not self.unit_reason:
                raise ValueError("sin unit_price hace falta unit_reason")
            if self.unit is not None or self.unit_src != "-":
                raise ValueError("linea incompleta no puede traer unidad ni origen")
        else:
            if self.unit is None or self.unit_src == "-":
                raise ValueError("con unit_price la unidad y el origen son obligatorios")
            if self.unit_reason:
                raise ValueError("unit_reason debe estar vacio cuando hay unit_price")
        return self
```

`unit_reason` conserva la cadena dinámica `formato_no_comparable:<fmt>`, así que se tipa
como `str` con valores documentados en vez de un `Literal` cerrado. `ref` y `size` se
dejan **sin tipar a propósito**: son el dato crudo de la fuente (número, texto o `-`) y se
conservan solo para trazabilidad; la comparación usa siempre `unit_price` + `unit`.

### Lote limpio (variante estructurada de `clean`)

Si el destino deja de ser texto plano y pasa a JSON (decisión abierta con API/BD, Prioridad 3
de [`05-pendientes.md`](05-pendientes.md#prioridad-3--contrato-con-apibd)), el mensaje de
`scraper.mercadona.clean` sería:

```python
class CleanBatch(BaseModel):
    source: Literal["normalizer"] = "normalizer"
    wh: str = "default"
    ts: str                                  # ISO-8601 UTC, igual que el envelope
    batch: int                               # nº de productos crudos del lote
    items: list[NormalizedProduct]
```

Hoy equivale al campo `clean` en texto plano; `items` es su versión tipada, sin parseo por
` | ` (ver [Mensaje de salida (clean)](#mensaje-de-salida-clean)).

### Reglas de validación

1. **Nada se inventa.** Sin precio, sin tamaño o con formato no comparable, la línea queda
   incompleta: `unit_price = None`, `unit = None`, `unit_src = "-"` y `unit_reason` con el
   motivo. El validador de coherencia **exige** esa combinación (`_coherente`).
2. **La fuente manda.** Con `reference_price` convertible → `unit_src = "fuente"`; si no,
   `"calculado"`. Nunca `"fuente"` con un valor del respaldo.
3. **Tolerancia en la frontera, rigor en la salida.** La entrada ignora campos nuevos
   (`extra="ignore"`); la salida los prohíbe (`extra="forbid"`) para que el contrato no
   derive en silencio.
4. **Error por item, no `-` silencioso.** Un `ValidationError` se emite como
   `ERROR id=...` y el lote continúa (como en `to_clean_txt`), pero **deja rastro** en
   vez de degradar el campo a `-`.
5. **Decimal para dinero.** Los importes son `Decimal` (nunca `float`), con la cuantización
   a 4 decimales (`_q`) que ya aplica `unit_price()`.

### Implementación

Lo que se añadió sobre `normalize_record()`:

| Pieza | Qué hace |
|---|---|
| `RawProduct` / `PriceInstructions` / `Category` | Validan la entrada en el camino estructurado |
| `NormalizedProduct` | Valida cada línea normalizada (`normalize_model`) |
| `CleanBatch` | Lote limpio serializable (`to_clean_json`) |
| `POST /normalize?format=json` | Devuelve un `CleanBatch`; `422` si un crudo no valida (**opt-in**) |
| `to_clean_txt` | Sigue igual, pero valida cada item: `ERROR id=...: validacion: ...` en una línea |

`_dec`, `_unit`, `UNITS`, `unit_price()` y `format_record()` se mantienen tal cual: el modelo
es un **envoltorio** sobre `normalize_record()`, que sigue siendo la única fuente de la
lógica. La línea limpia de texto (contrato actual de `clean`) no se altera.

Requiere **Pydantic v2** (`ConfigDict`, `field_validator`, `model_validator`).
