# 01 · Decision de modelos: embeddings y LLM

Este documento es la respuesta a la primera parte de la tarea: **que modelo de
embeddings y que LLM**. No es una comparativa de marketing: los candidatos se
puntuan con los criterios del proyecto y, cuando se puede, se miden sobre el
dataset propio (ver [`03-evaluacion.md`](03-evaluacion.md)).

## 1. Restricciones reales del proyecto

Estas condiciones son las que descartan candidatos. Sin ellas, la decision
seria distinta.

| Restriccion | Valor concreto | Por manda |
|---|---|---|
| **Idioma y dominio** | Texto de supermercado **espanol**; nombres con marca propia (`Aceite de oliva virgen extra Hacendado`), abreviaturas (`Cafe molido natural`), formatos (`100 g`, `dc`, `lavado`) | Un modelo entrenado solo en ingles se queda corto con nombres de tienda |
| **Maquina** | VM del cluster (Minikube), **sin GPU**, RAM limitada | Descarta cualquier modelo que exija GPU para ser util |
| **Coste** | Presupuesto 0 EUR; la API de Gemini entra por la **cuenta de la universidad** (mas cuota que el tier gratuito) | Los embeddings van en local: se paga una vez (descarga) y no por token |
| **Corpus** | ~4.6k productos por pasada del scraper de Mercadona (4591 el 15/10/2026); 3 cadenas en el prototipo | Pocos miles de vectores: no hace falta un indice distribuido |
| **Reproducibilidad** | La demo tiene que funcionar delante del profesor, en la VM, sin depender de la red | El camino por defecto no puede depender de una API |
| **Integracion** | El dato llega como **texto plano** desde NATS (`scraper.<cadena>.clean`) | El embedding se calcula en el servicio de IA, no en el normalizador (el normalizador no debe cargar 2 GB de modelo) |

## 2. Criterios

### Embeddings

| # | Criterio | Peso | Como se comprueba |
|---|---|---|---|
| C1 | Calidad en **espanol** y en nombres de producto | Alto | `recall@k` y `MRR` sobre el dataset propio |
| C2 | Funciona **sin GPU y sin red** (una vez descargado) | Alto | El indice se regenera en la VM sin claves |
| C3 | Coste por token = 0 | Alto | Open weights |
| C4 | RAM y velocidad en CPU | Alto | Medir el tiempo de indexado en la VM |
| C5 | Licencia que permita reutilizarlo | Medio | MIT / Apache-2.0 frente a CC-BY-NC |
| C6 | Dim del vector (tamaño del indice) | Medio | 384 frente a 1024 |
| C7 | Prefijos asimetricos (query/passage) | Medio | Si los exige, hay que aplicarlos bien o el recall se hunde |

### LLM

| # | Criterio | Peso |
|---|---|---|
| L1 | Calidad en espanol y al comparar productos/precios | Alto |
| L2 | Coste (0 EUR en local, cuota de la uni en la API) | Alto |
| L3 | Latencia y recursos en una VM sin GPU | Medio-alto |
| L4 | Que la demo no dependa de la red | Medio |
| L5 | Licencia | Medio |

## 3. Embeddings: candidatos

### 3.1 Open weights (los que se evaluan en local)

| Modelo | Dim | Params | Descarga | Idiomas | Licencia | Contexto | Notas |
|---|---|---|---|---|---|---|---|
| **`BAAI/bge-m3`** | 1024 | 568M | 2.3 GB | 100+ | MIT | 8192 | Denso + disperso + multi-vector. **Sin prefijos**: se consulta igual que se indexa |
| `intfloat/multilingual-e5-small` | 384 | 118M | 0.47 GB | 100 | MIT | 512 | Muy ligero. **Exige** prefijos (`query: ` / `passage: `) |
| `intfloat/multilingual-e5-large` | 1024 | 560M | 2.3 GB | 100 | MIT | 512 | Mismo peso que bge-m3, peor en multilingue reciente |
| `Qwen/Qwen3-Embedding-0.6B` | 1024 | 595M | 2.4 GB | 119 | Apache-2.0 | 32768 | Lider multilingue de 2026, sin prefijos |
| `nomic-ai/nomic-embed-text-v1.5` | 768 | 137M | 0.55 GB | ~100 | Apache-2.0 | 8192 | Pensado para documentos largos (aqui sobraria) |
| `jina-ai/jina-embeddings-v3` | 1024 | 570M | 2.3 GB | 89 | **CC-BY-NC-4.0** | 8192 | Muy bueno, pero licencia **no comercial** |

### 3.2 API (descartados como opcion principal)

| Modelo | Dim | Coste | Motivo del descarte |
|---|---|---|---|
| `text-embedding-3-small` (OpenAI) | 1536 | 0.02 $/1M tokens | Requiere clave y red para **reconstruir el indice**; la calidad no compensa |
| `gemini-embedding-001` (Google) | 3072 | Gratis hasta cierto volumen | Igual: ataria el prototipo a una clave y a la red |
| `text-embedding-3-large` / `jina-v3` API | 3072/1024 | 0.13 $/1M | Coste y latencia de red sin ganancia medible en este corpus |

La API no se descarta por calidad: se descarta porque **el indice tiene que
poder regenerarse en la VM sin depender de nadie** (si el modelo de embeddings
cambia, hay que reindexar los ~4.6k productos; con la API eso es un script
dependiente de una clave, sin ella el prototipo no arranca).

### 3.3 Decision

> **Embeddings por defecto: `intfloat/multilingual-e5-small` (384 dim, MIT).**
>
> `BAAI/bge-m3` queda como **alternativa ya configurada** (y como el modelo
> que se prueba con los datos reales). Se cambia con
> `RAG_EMBED_MODEL=bge-m3`, sin tocar codigo.

El motivo no es la reputacion del modelo, es la medicion: en el dataset
propio, `e5-small` **iguala o supera** a `bge-m3` y pesa cinco veces menos.

| | `e5-small` | `bge-m3` |
|---|---|---|
| recall@1 catalogo | **0.837** | 0.584 |
| recall@3 catalogo | **0.994** | 0.970 |
| recall@5 catalogo | 0.994 | 0.994 |
| MRR catalogo | **0.908** | 0.778 |
| recall@1 equivalencia | 0.996 | **1.000** |
| recall@3 equivalencia | 1.000 | 1.000 |
| Dim (indice) | **384** (484 KB) | 1024 (1.2 MB) |
| Peso en disco | **471 MB** | 2.3 GB (4.5 GB con los dos formatos) |
| Tiempo de indexado | **27-62 s** | 74-99 s |

Por que gana `e5-small`:

1. **C1 - calidad medida, y gana.** En catalogo es claramente mejor
   (recall@1 +25 puntos, MRR +0.13). En equivalencia pierde por **un caso de
   498** (0.996 vs 1.000): en la practica, empate.
2. **C4 - recursos.** 471 MB frente a 2.3 GB, y 384 dim frente a 1024. En
   una VM sin GPU esto no es un detalle: el servicio de RAG carga el modelo en
   RAM y convive con el LLM. Con `e5-small` el LLM local puede ser de 14B en
   la misma maquina; con `bge-m3` no caben los dos.
3. **C6 - indice.** 484 KB en vez de 1.2 MB. Irrelevante a esta escala, pero
   gratis.
4. **C7 - prefijos.** Es la contra: la familia E5 **exige** `query: ` y
   `passage: `. `embeddings.py` los aplica siempre (y hay un test que lo
   comprueba), pero es la trampa que hace que este modelo funcione peor si
   alguien lo usa a mano sin los prefijos.

**Cuando se cambiaria a `bge-m3`:**

- Si con el `.txt` real de Mercadona el modelo pequeno se queda corto (nombres
  reales con atributos raros, descripciones mas largas). El comando
  `rag.cli compare` lo responde en un minuto.
- Si el corpus crece hasta millones de productos y se quiere un modelo con
  mayor cobertura multilingue (bge-m3 cubre 100+ idiomas).
- Si el LLM va a ser una API (Gemini) y la RAM no aprieta: entonces el
  embedding puede ser el mas grande sin coste.

> [!IMPORTANT]
> La comparativa se hizo con el **dataset sintetico**. Con datos reales el
> orden puede cambiar: es exactamente lo que habria que re-medir cuando el
> equipo de ingesta comparta el `mercadona_<ts>.txt`. Lo que si es solido es
> la conclusion operativa: **un modelo de 471 MB rinde igual que uno de
> 2.3 GB en este dominio**, y en una VM con RAM limitada eso decide.

### 3.4 Candidatos no evaluados

| Modelo | Por que no se midio aqui |
|---|---|
| `Qwen/Qwen3-Embedding-0.6B` | Descargar e indexar con el mataba el proceso por falta de RAM en la maquina de desarrollo (6 GB). Es el candidato a medir **en la VM**: es el lider multilingue de 2026 y pesa 1.2 GB |
| `intfloat/multilingual-e5-large` | Mismo tamano que bge-m3 (2.3 GB) y peor en multilingue reciente |
| `nomic-ai/nomic-embed-text-v1.5` | Pensado para documentos largos; aqui los chunks son de una linea |
| `jina-ai/jina-embeddings-v3` | Licencia CC-BY-NC (no comercial) |

### 3.5 Como comparar (y volver a comparar)

```bash
python -m rag.cli compare
```

Reindexa y evalua los candidatos con el mismo dataset, los mismos filtros y
las mismas consultas, y deja la tabla en `docs/resultados-embeddings.json`.
Cuando llegue el dato real, se copia a `data/raw/` y se vuelve a ejecutar: es
la forma de tener la decision **actualizada por evidencia** y no por costumbre.

## 4. LLM: candidatos

### 4.1 Local con Ollama (sin GPU)

| Modelo | Descarga (Q4) | RAM aprox | Espanol | Para que |
|---|---|---|---|---|
| `qwen3:4b` | 2.5 GB | ~4 GB | Bueno | **Por defecto**: cabe en una VM modesta y responde en segundos |
| `qwen3:8b` | 5.2 GB | ~7 GB | Bueno | Si la VM tiene 8 GB de RAM sobrantes |
| `qwen3:14b` | 9 GB | ~11 GB | Muy bueno | Si la VM es potente |
| `qwen3:30b-a3b` | 18 GB | ~20 GB | Muy bueno | MoE: 30B de parametros pero solo 3B activos -> velocidad de 3B con calidad de 30B |
| `llama3.1:8b` | 4.9 GB | ~7 GB | Correcto | Alternativa; tokeniza peor el espanol que qwen |
| `gemma3:12b` | 8.1 GB | ~10 GB | Bueno | Alternativa |
| `llama3.2:1b` | 1.3 GB | ~2 GB | Regular | Solo para maquinas muy justas; insuficiente para el prompt de equivalencia |

La familia **Qwen3** es la escolha por defecto del lado local: es la que mejor
resuelve espanol con licencia permisiva (Apache-2.0) y es la que mas juego da
en el rango de 4-8 GB de RAM.

### 4.2 API (Gemini)

| Modelo | Estabilidad | Cuando |
|---|---|---|
| `gemini-2.5-flash` | Estable, en todos los tiers | **Por defecto en la API**: rapido, barato y con cuota en la cuenta de la uni |
| `gemini-3-flash-preview` | Preview | Si la cuenta tiene acceso: mas capaz, pero la preview puede cambiar o desaparecer |
| `gemini-3-pro` / `gemini-3.1-pro-preview` | Preview, caro y lento | Para el informe final, no para el pipeline |

Se usa la API de **AI Studio** (`https://aistudio.google.com/apikey`), que es
distinta de la clave de Vertex AI. La clave va en `GEMINI_API_KEY` y **no**
se versiona.

### 4.3 Decision

> **LLM hibrido: `ollama` por defecto, `gemini` con la clave de la
> universidad como alternativa. Los dos se cambian con una variable de
> entorno, sin tocar codigo.**

```bash
RAG_LLM=ollama python -m rag.cli ask "..."     # local, 0 EUR, funciona sin red
RAG_LLM=gemini python -m rag.cli ask "..."     # API, mejor calidad, usa la cuota de la uni
```

Por que hibrido y no uno solo:

1. **L4 - la demo no puede depender de la red ni de una cuota.** La VM del
   proyecto es el sitio donde se ensaya delante del profesor. Con Ollama
   como camino por defecto, la demo funciona aunque falle internet o se
   agote la cuota de la API.
2. **L2 - el coste escala con el uso.** Con la cuota de la uni, 100
   preguntas de demo entran de sobra; pero el proyecto no debe depender de
   una clave que caduca o de un limite por cuenta.
3. **L1 - para comparar.** Con la misma interfaz, el mismo dataset y la misma
   evaluacion, se puede medir cuanto mejora Gemini frente al local. Esa
   comparacion es la que decide el modelo final del producto.
4. **El contexto ya viene filtrado y estructurado**, asi que el local de 4B
   llega: no tiene que razonar sobre 4.6k productos, solo sobre 5-8 que ya
   son los relevantes.

Por que `qwen3:4b` y no uno mas grande por defecto: el coste de RAM y de
latencia en una VM sin GPU es real, y el prompt esta disenado para eso
(contexto corto, formato de salida declarado, instruccion de no inventar). Si
la VM tiene RAM de sobra, `RAG_OLLAMA_MODEL=qwen3:8b` (o `30b-a3b`) lo sube
sin tocar codigo.

## 5. Lo que se descarto, resumido

| Descartado | Motivo |
|---|---|
| Embeddings por API | El indice tiene que poder regenerarse sin claves ni red |
| `jina-embeddings-v3` | Licencia CC-BY-NC (no comercial) |
| `nomic-embed-text-v1.5` | Pensado para documentos largos; aqui los chunks son de una linea |
| Un unico LLM (solo API o solo local) | La demo no puede depender de la red; el coste no puede depender de una cuota |
| Reranking con LLM en el camino critico | Multiplica el coste por consulta; en CPU se nota y el recall del top-8 ya es suficiente |
| Calcular embeddings en el normalizador (Fission) | Meteria 2 GB de modelo en la imagen de la funcion; el embedding va en el servicio de IA |

## 6. Como cambiar la decision

```bash
# Embeddings (cada modelo tiene su propio indice)
RAG_EMBED_MODEL=bge-m3 python -m rag.cli index
RAG_EMBED_MODEL=bge-m3 python -m rag.cli search "aceite"   # indice separado por modelo

# LLM
RAG_LLM=gemini GEMINI_API_KEY=... python -m rag.cli ask "..."
RAG_OLLAMA_MODEL=qwen3:8b python -m rag.cli ask "..."
```

Cada modelo de embeddings tiene **su propio indice** en `.cache/index/<modelo>/`,
de modo que se pueden comparar sin pisarse.

## 7. Licencias

| Componente | Licencia | Nota |
|---|---|---|
| `intfloat/multilingual-e5-small` | MIT | Uso libre (modelo por defecto) |
| `Qwen/Qwen3-Embedding-0.6B` | Apache-2.0 | Uso libre |
| `BAAI/bge-m3` | MIT | Uso libre (alternativa) |
| `qwen3:4b` (Ollama) | Apache-2.0 | Uso libre |
| `llama3.1`, `gemma3` | Llama Community / Gemma | Requisitos de uso de Meta y Google |
| Gemini API | Google's terms | Solo si se usa `--llm gemini` |

Ninguno de los componentes de software del prototipo tiene licencia
copyleft: el repositorio del proyecto puede seguir siendo el que es.
