# 02 · Prototipo de RAG

Como funciona el prototipo: que entra, como se indexa, como se recupera y
que se le pide al LLM. El "que" esta en
[`01-decision-modelos.md`](01-decision-modelos.md); aqui esta el "como".

## Flujo general

```mermaid
flowchart LR
  A["web del súper<br/>(Mercadona, Carrefour…)"] --> B["scraper<br/>(equipo de ingesta)"]
  B --> C["normalizer<br/>(equipo de ingesta)"]
  C -->|"linea limpia<br/>(texto plano)"| D["flujo-ia<br/>ingest.py"]
  D --> E["embeddings<br/>(HF, local)"]
  E --> F[("indice vectorial<br/>.cache/index/")]
  F --> G["retrieval<br/>(denso + filtros)"]
  G --> H["LLM<br/>(Ollama o Gemini)"]
  H --> I["respuesta con citas [id]"]

  style D fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px,color:#4a148c
  style E fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#1b5e20
  style F fill:#fff8e1,stroke:#fb8c00,stroke-width:2px,color:#e65100
  style G fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px,color:#0d47a1
  style H fill:#fce4ec,stroke:#d81b60,stroke-width:2px,color:#880e4f
```

La frontera con el equipo de ingesta es **un fichero de texto con lineas
limpias**. Es el mismo formato que viaja por el subject `scraper.<cadena>.clean`
(ver `flujo-entrada/docs/03-contratos-datos.md` de la rama `scrapping`), asi
que el prototipo consume el dato real sin adaptadores: se copia el `.txt` a
`data/raw/<cadena>_clean.txt` y se indexa.

## Estructura del codigo

| Fichero | Responsabilidad |
|---|---|
| `rag/config.py` | Modelos, rutas y parametros. Todo se cambia por entorno |
| `rag/ingest.py` | **Unico** punto que conoce el formato de la linea limpia |
| `rag/embeddings.py` | Envoltorio de `sentence-transformers` (prefijos, normalizacion) |
| `rag/store.py` | Indice vectorial (coseno con numpy) + persistencia |
| `rag/indexer.py` | Orquestacion de indexado: lineas -> vectores -> indice |
| `rag/retriever.py` | Busqueda con filtros de metadatos |
| `rag/llm.py` | Clientes Ollama / Gemini / sin-LLM con la misma interfaz |
| `rag/pipelines.py` | Los tres pipelines: catalogo, equivalencia, QA |
| `rag/evaluate.py` | Las tres evaluaciones y el informe |
| `rag/cli.py` | Interfaz de linea de comandos |
| `data/generate_dataset.py` | Genera el dataset de prueba y el ground truth |

## Decisiones del pipeline

### 1. El chunk es un producto

Cada producto normalizado es **un chunk**. No hay troceado de texto: un
producto de supermercado ya es una unidad semantica atomica (nombre, marca,
formato, precio). Trocearlo mas pequena solo destruye la informacion que
hace falta para comparar (el formato y la unidad de precio van juntos).

Consecuencia practica: el indice tiene exactamente un vector por producto
(257 en el dataset de prueba), y el `id` del producto es la clave de citacion.

### 2. Que se embebe (y que no)

```
Aceite de oliva virgen extra Hacendado | categoria Aceites, especias y salsas | tamano 1 l
```

Se embeben el **nombre** (que ya lleva marca y, en el dato real, el formato),
la **categoria** y el **tamano**. **No** se embeben el precio, la URL ni el
precio unitario:

- El precio no sirve para decir "esto es lo mismo que aquello" (solo para
  ordenar), y metido en el vector diluye la senal de identidad del producto.
- La URL es un identificador tecnico: aporta ruido y ningun parecido semantico.
- El precio unitario si es informativo, pero va en los **metadatos**, que se
  filtran con reglas exactas (precio < 2 EUR) y no con similitud. Mezclar
  reglas exactas dentro de un vector difumina el criterio.

Regla: **el vector decide que productos son parecidos; los metadatos decide
cuales entran en la respuesta** (cadena, categoria, rango de precio).

### 3. Recuperacion: densa + filtros, sin reranking

El retrieval es coseno sobre vectores normalizados, con **filtros de
metadatos aplicados antes** del top-k. Sin reranking con LLM en el camino
critico: el LLM entra *despues* de recuperar, para redactar o para decidir
entre candidatos que ya estan en el top-k.

Motivo: el reranking multiplica el coste por consulta (una llamada al LLM por
candidato) y en una VM sin GPU eso se nota. Con un corpus de miles de
productos, el top-8 denso ya trae la respuesta correcta (ver
[`03-evaluacion.md`](03-evaluacion.md)).

### 4. Por que numpy y no FAISS

Con 257 productos (y ~4.6k en una ejecucion real del scraper) la similitud
coseno sobre una matriz normalizada es milisegundos. FAISS o pgvector tienen
sentido a partir de ~10^5-10^6 vectores. La API de `VectorStore`
(`add` / `search` / `save` / `load`) esta pensada para que cambiar de
backend sea cambiar la implementacion, no el pipeline. Cuando el equipo de
API/BD tenga el esquema de BD, el sitio natural es `pgvector` (el vector
viaja en la misma tabla que el producto).

### 5. Los tres pipelines

| Pipeline | Pregunta que responde | Recuperacion | LLM |
|---|---|---|---|
| **Catalogo** | "encuentra el aceite de oliva virgen extra de 1 l" | top-k por descripcion | redacta la respuesta con los ids citados |
| **Equivalencia** | "este de Mercadona, cual es en Carrefour" | top-k en la cadena destino | elige el equivalente o dice `pid: null` |
| **QA** | "cual es el aceite mas barato por litro" | top-k por relevance | responde **solo** con el contexto y cita `[id]` |

Los tres comparten la misma recuperacion y el mismo esqueleto de prompt
(sistema + contexto con ids + peticion). Lo que cambia es la instruccion y el
formato de salida.

### 6. Prompts

El prompt es corto a proposito: el modelo local por defecto es un 4B, que
responde peor cuanto mas se le alarga. Reglas que se siguen:

- **El contexto lleva el `id` entre corchetes** (`[10001]`) para que el modelo
  cite y para que la evaluacion pueda comprobar que no inventa ids.
- **El formato de salida se declara explicitamente** (`RESPUESTA:` / `FUENTES:`,
  o JSON para equivalencia). Un 4B sin formato declarado responde en prosa y
  es mas dificil de parsear.
- **Se le dice que no invente**: "si no esta en el contexto, dilo". Sin esta
  frase, un modelo pequeno completa los huecos con precios plausibles, que es
  justo el fallo que da verguenza en una demo.
- **La equivalencia se evalua con criterio negativo explicito**: "Aceite de
  oliva virgen extra 1 l" y "Aceite de oliva 1 l" **no** son el mismo
  producto, y un formato distinto (pack de 2 ud frente a 1 ud) tampoco. Sin
  esta instruccion el modelo tiende a decir que si.

El prompt de equivalencia pide JSON
(`{"pid": ..., "confianza": ..., "motivo": ...}`) y la respuesta se parsea con
`extract_json()`, que tolera vallas de codigo, texto alrededor y JSON
delimitado en medio de una frase (los modelos pequeños cometen eso).

### 7. Degradacion elegante

Ningun fallo del LLM tumba el pipeline:

| Fallo | Comportamiento |
|---|---|
| LLM no configurado (`--llm none`) | El pipeline devuelve solo la recuperacion (baseline) |
| LLM caido / timeout | Se captura el error, la recuperacion se conserva y se avisa por stderr |
| LLM devuelve JSON invalido | `pid` queda a `None`; el pipeline no revienta |
| Producto sin precio unitario | Se indexa igual: el `id` y el nombre siguen sirviendo para buscar |

La ultima fila es importante: el normalizador deja lineas incompletas
(`- (sin_precio)`) cuando la fuente no trae precio, y esas lineas **no** se
descartan. Descartarlas perderia productos del catalogo.

## Datos de prueba

El dataset lo genera `data/generate_dataset.py` (determinista, semilla fija):

- **257 productos** en 3 cadenas (mercadona, carrefour, alcampo) sobre 85
  productos canonicos, en el **formato exacto** de la linea limpia.
- Casos que el pipeline tiene que handlear: lineas con `src=calculado` (sin
  precio de referencia), lineas incompletas (`- (sin_precio)`), marcas
  compartidas entre cadenas (el vector no puede apoyarse en la marca) y
  **variantes de formato** (pack de 2 ud frente a 1 ud) que **no** son
  equivalentes pero se parecen mucho.
- **Ground truth** exacto en `data/gold/`: equivalencias, no-equivalencias,
  consultas de catalogo y preguntas de QA con la respuesta esperada.

La ventaja del dato sintetico es que el ground truth es exacto; la
desventaja, que el vocabulario es mas limpio que el de la web real. Cuando el
equipo de ingesta comparta el `mercadona_<ts>.txt` real, se copia a
`data/raw/` y el ground truth de equivalencias habra que etiquetarlo a mano
(la parte de QA y catalogo se puede autogenerar del propio `.txt`).

## Lo que este prototipo NO cubre

- **Multi-tienda real** (`wh`): el dataset tiene una sola etiqueta `default`,
  igual que la ingesta actual. El `wh` viaja en los metadatos, pero no se usa
  para filtrar.
- **Reindexado automatico**: el indice se regenera a mano (`rag.cli index`).
  En produccion, el `consumer` de ingesta (o el servicio de API/BD) deberia
  disparar el indexado al recibir un lote `clean` nuevo.
- **Embeddings en la ingesta**: el embedding se calcula aqui, fuera del
  clúster. La decision de quien lo calcula (normalizador vs. este servicio) es
  una pregunta abierta del plan (ver `05-pendientes.md` del equipo de
  ingesta): lo natural es calcularlo **en el servicio de IA**, no en el
  normalizador, para no meter un modelo de 2 GB en la imagen de Fission.
