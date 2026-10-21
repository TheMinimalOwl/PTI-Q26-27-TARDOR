# flujo-ia · Prototipo de RAG (parte de IA del proyecto)

Parte de IA de **TARDOR** (comparador de precios de supermercado): elige el
modelo de embeddings y el de LLM, y monta el prototipo de RAG sobre las lineas
limpias que produce el normalizador del equipo de ingesta.

Los datos de entrada son los mismos que salen del subject
`scraper.<cadena>.clean`: texto plano, una linea por producto. Si el equipo de
ingesta comparte un `mercadona_<ts>.txt`, se copia en `data/raw/` y este
prototipo lo consume sin tocar una linea.

## Documentacion

| Documento | Contenido |
|---|---|
| [`docs/01-decision-modelos.md`](docs/01-decision-modelos.md) | **Que modelo de embeddings y que LLM, y por que** |
| [`docs/02-prototipo-rag.md`](docs/02-prototipo-rag.md) | Como funciona: chunking, que se embebe, prompts, degradacion |
| [`docs/03-evaluacion.md`](docs/03-evaluacion.md) | Metricas, resultados medidos y como reproducirlos |

## Arranque rapido

```bash
cd flujo-ia
bash setup.sh            # venv + dependencias + dataset + indice
bash setup.sh --verify   # estado del montage
```

`setup.sh` es idempotente y se puede volver a ejecutar. Si la maquina no
tiene `python3-venv` (Debian/Ubuntu), el script lo detecta y arranca pip a
mano.

## Uso

```bash
# 1. Indexar (o reindexar) los datos de data/raw/
python -m rag.cli index

# 2. Catalogo: buscar un producto por descripcion
python -m rag.cli search "aceite de oliva virgen extra"

# 3. Equivalencia entre cadenas: este de Mercadona, cual es en Carrefour
python -m rag.cli equiv --id 10001 --chain carrefour --llm ollama

# 4. QA: pregunta en lenguaje natural
python -m rag.cli ask "¿cual es el aceite de oliva mas barato por litro?" --llm ollama

# 5. Evaluacion (metricas de retrieval, sin gastar API)
python -m rag.cli eval --llm none

# 6. Comparar modelos de embeddings
python -m rag.cli compare
```

## Configuracion

Todo se cambia por variable de entorno, sin tocar codigo:

| Variable | Por defecto | Para que sirve |
|---|---|---|
| `RAG_EMBED_MODEL` | `e5-small` | Modelo de embeddings (`e5-small`, `bge-m3`, `qwen3-embed-0.6b` o un id de HF) |
| `RAG_LLM` | `ollama` | Backend de LLM: `ollama`, `gemini` o `none` |
| `RAG_OLLAMA_MODEL` | `qwen3:4b` | Modelo local de Ollama |
| `RAG_OLLAMA_THINK` | `false` | Si el modelo razona antes de responder. En CPU la diferencia es de **15 s a 0,7 s** por respuesta |
| `RAG_OLLAMA_HOST` | `http://localhost:11434` | Endpoint de Ollama |
| `RAG_GEMINI_MODEL` | `gemini-2.5-flash` | Modelo de la API de Gemini |
| `GEMINI_API_KEY` | — | Clave de AI Studio (la cuenta de la uni da mas cuota) |
| `RAG_TOP_K` | `5` | Productos recuperados por consulta |
| `RAG_CACHE_DIR` | `./.cache` | Donde van el indice y los modelos |

## El LLM es opcional

`--llm none` deja el pipeline en modo **solo-recuperacion**: es la linea base
para medir la calidad del retrieval (que es lo que decide el modelo de
embeddings) y funciona sin GPU, sin claves y sin red. El LLM solo hace falta
para redactar la respuesta, para elegir el equivalente entre candidatos y para
responder preguntas.

## Servicio HTTP

El servicio (`python -m rag.serve`) expone lo que consume el equipo de API y
la app:

| Endpoint | Que hace |
|---|---|
| `GET /health` | Estado: modelo de embeddings, LLM, nº de productos |
| `POST /search` | Busqueda de catalogo (texto y metadatos) |
| `POST /ask` | Pregunta en lenguaje natural. Devuelve **JSON validado contra un JSON Schema**, con guardrails (citas validas, cifras del contexto, abstension) |
| `POST /ask/stream` | Lo mismo en **streaming por SSE** (`fuentes`, `token`, `fin`) |
| `POST /equiv` | Equivalencia entre cadenas: el equivalente de un producto en otra cadena |

```bash
curl -s localhost:8080/ask -H 'Content-Type: application/json' \
  -d '{"question":"¿cual es el aceite de oliva mas barato por litro?"}' | python3 -m json.tool
```

## Estructura

```
flujo-ia/
├── README.md
├── setup.sh                  # montaje idempotente
├── requirements.txt
├── rag/                      # el pipeline (ver docs/02-prototipo-rag.md)
│   ├── config.py             # modelos, rutas, parametros
│   ├── ingest.py             # parser de la linea limpia (unica frontera con ingesta)
│   ├── embeddings.py         # sentence-transformers
│   ├── store.py              # indice vectorial
│   ├── indexer.py            # orquestacion de indexado
│   ├── retriever.py          # busqueda con filtros
│   ├── llm.py                # Ollama | Gemini | ninguno (con streaming)
│   ├── chain.py              # cadenas RAG con LangChain (LCEL)
│   ├── guardrails.py         # controles de la respuesta + JSON Schema
│   ├── schemas/              # JSON Schema de la respuesta
│   ├── pipelines.py          # catalogo, equivalencia, QA (adaptador sobre chain.py)
│   ├── evaluate.py           # metricas
│   ├── serve.py              # servicio HTTP (Flask)
│   └── cli.py                # CLI
├── data/
│   ├── generate_dataset.py   # genera el dataset de prueba y el ground truth
│   ├── raw/                  # lineas limpias (una por cadena)
│   └── gold/                 # ground truth: equivalencias, catalogo, QA
├── tests/                    # 35 tests, sin GPU ni API
└── docs/                     # 01 modelos · 02 prototipo · 03 evaluacion
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

No necesitan el modelo de embeddings ni el LLM: el LLM se sustituye por un
doble en `tests/test_pipelines.py`. Son la red de seguridad para cuando el
formato de la linea limpia cambie en el equipo de ingesta.

## Estado

- [x] Decision de modelo de embeddings (medida sobre el dataset, no de opinion): `e5-small` por defecto, `bge-m3` como alternativa
- [x] Prototipo de RAG con los tres pipelines
- [x] Cadena RAG con **LangChain** (LCEL sobre `langchain-core`)
- [x] Dataset de prueba con ground truth exacto
- [x] Evaluacion de retrieval reproducible
- [x] Evaluacion con LLM en la VM (`qwen3:8b` local): precision@1 de equivalencia 1.000,
      trampas 8/8, QA 0.880 de contenido y 1.000 de citas sin inventar
- [x] Guardrails (citas, cifras, abstension) y salida con **JSON Schema**
- [x] **Streaming SSE** en `/ask/stream`
- [ ] Integracion con el subject `scraper.<cadena>.clean` (pendiente de que ingesta lo exponga)
