# 03 · Evaluacion

Como se mide el prototipo y que se ha medido. Todas las cifras de este
documento son **reproducibles** con los comandos que se indican: no hay
numeros de marketing ni de otro dataset.

## Tareas y metricas

| Tarea | Pregunta | Metrica | Como se mide |
|---|---|---|---|
| **Catalogo** | ¿la busqueda devuelve el producto pedido? | `recall@k`, `MRR` | ¿el pid esperado esta en el top-k? |
| **Equivalencia** | ¿el equivalente de otra cadena esta entre los candidatos? | `recall@k` | ¿el pid equivalente esta en el top-k? |
| **Equivalencia + LLM** | ¿el LLM elige el equivalente correcto? | `precision@1` | ¿el pid que devuelve el LLM es el del ground truth? |
| **Trampas** | ¿el LLM descarta los casi-iguales? | `trampas_ok` | ¿el LLM avoids el pid de formato distinto? |
| **QA** | ¿la respuesta es correcta y no inventa? | `contenido_ok`, `citas_ok`, `cubre_esperados` | ¿el dato esperado esta en la respuesta? ¿los ids citados estaban en el contexto? |

`recall@k` de equivalencia se mide **con filtro por cadena destino**: el
recuperado tiene que estar en la cadena correcta, no solo ser parecido.

## Resultados medidos

### Retrieval (embeddings `intfloat/multilingual-e5-small`, 257 productos, 3 cadenas)

```bash
python -m rag.cli eval --llm none
```

| Tarea | n | recall@1 | recall@3 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|---|
| Catalogo | 166 consultas | 0.837 | 0.994 | 0.994 | 1.000 | 0.908 |
| Equivalencia | 498 pares | 0.996 | 1.000 | 1.000 | 1.000 | — |

**Como se leen estos numeros.**

- *Catalogo*: el 99% de las consultas traen el producto esperado en el top-3 y
  el 100% en el top-10. El `recall@1` de 0.837 es **correcto para este
  dataset**, y conviene explicarlo: la mitad de las consultas son "el mismo
  producto en las tres cadenas", asi que hay **tres** respuestas validas (una
  por cadena) y acertar una sola no basta para que el primer resultado sea "el"
  correcto. Por eso la metrica que hay que mirar es `recall_full@k` (fraccion
  de los tres esperados presentes en el top-k): **0.504 en top-1, 0.994 en
  top-3, 0.994 en top-5, 1.000 en top-10**. O sea: en la mayoria de consultas
  aparecen **las tres** cadenas del producto entre los tres primeros
  resultados.
- *Equivalencia*: recall@1 = 0.996 (497 de 498 pares). El embedding denso con
  el nombre, la marca, la categoria y el formato basta para encontrar el
  equivalente en la otra cadena **casi siempre**. Esto es lo que sostiene la
  tarea 6 del plan ("equivalencia de productos"): la recuperacion ya
  funciona; lo que queda por delante es el LLM decidiendo entre candidatos y
  el ground truth etiquetado sobre datos reales.

### Comparativa de modelos de embeddings

Mismo dataset, mismos filtros, mismas consultas, mismo codigo:

```bash
python -m rag.cli compare
```

| Modelo | Dim | recall@1 | recall@3 | recall@5 | MRR | Equiv. recall@1 | Peso en disco | Indexado (s) |
|---|---|---|---|---|---|---|---|---|
| **`intfloat/multilingual-e5-small`** | 384 | **0.837** | **0.994** | 0.994 | **0.908** | 0.996 | **471 MB** | **27-62** |
| `BAAI/bge-m3` | 1024 | 0.584 | 0.970 | 0.994 | 0.778 | **1.000** | 2.3 GB | 74-99 |
| `Qwen/Qwen3-Embedding-0.6B` | 1024 | - | - | - | - | - | 1.2 GB | no medido (OOM en la maquina de desarrollo) |

Conclusion: **el modelo pequeno gana**. En catalogo es 25 puntos mejor en
recall@1 y 0.13 mejor en MRR; en equivalencia pierde un caso de 498. Y pesa
cinco veces menos, lo que en una VM con RAM limitada es lo que decide (ver
[`01-decision-modelos.md`](01-decision-modelos.md)).

### Con LLM (VM `gastly`, `qwen3:8b` local, muestra de 25 casos)

```bash
# En la VM: 4 cores, 15 GB, sin GPU
python -m rag.cli eval --llm ollama --max-casos 25 --json docs/resultados-qa-ollama.json
```

| Metrica | Valor | Lectura |
|---|---|---|
| Equivalencia · `precision@1` **con LLM** | **1.000** | El LLM elige el equivalente correcto en los 25 casos |
| Equivalencia · `precision@1` solo retrieval (top-1) | 0.920 | El primer candidato recuperado falla en 2 de 25 |
| Equivalencia · casos trampa descartados | **1.000** (8/8) | No confunde un pack de 2 ud con 1 ud |
| QA · contenido correcto | **0.880** (22/25) | La respuesta trae el dato esperado |
| QA · citas sin inventar | **1.000** (25/25) | Ninguna respuesta cita un producto que no estaba en el contexto |
| QA · cubre el producto esperado | 0.920 | 23 de 25 citas el producto correcto |
| QA · latencia media | 9-16 s | Por respuesta, con el modelo ya cargado en RAM |

> La muestra es de 25 casos (el gold completo son 173 preguntas de QA y 498
> pares de equivalencia). La evaluacion completa con LLM local son ~670
> llamadas a 10-20 s: unas 3 horas. Con `--max-casos` se acota.

**Los 3 fallos que quedan son fallos reales, no de la metrica:**

1. *Aguacates de 4 ud* · el modelo responde `0.875 EUR/ud` (la cifra correcta,
   el gold la tiene redondeada a 0.88) pero **no dice de que cadena es**: la
   metrica exige precio *y* cadena.
2. *Atun claro en aceite de 3 ud* · idem: `0.767 EUR/ud` correcto, sin
   nombrar la cadena.
3. *Alubias cocidas de 570 g* · **respuesta vacia**: Ollama devolvio un error
   transitorio (`unexpected EOF`). El pipeline lo capturo, lo conto como fallo
   y **siguio con el resto** (degradacion elegante, sin tumbar la evaluacion).

### Lo que la evaluacion con LLM cambio en el prototipo

Medir con LLM no solo dio numeros: destapo tres fallos reales del prototipo
que se corrigieron y subieron las metricas.

| Cambio | Por que | Efecto |
|---|---|---|
| Ground truth con **empates** | El precio unitario viene de la fuente y es el mismo en las tres cadenas: "el mas barato por unidad" es un empate de tres y el ground truth exigia una sola cadena | contenido 0.40 -> 0.60 |
| Metrica que compara **numeros como numeros** | Se comparaba por subcadena: el atun cuesta 0.767 y el gold lo guardaba a 0.87, asi que una respuesta correcta se marcaba como fallo | (parte del 0.60 -> 0.84) |
| Preguntas de QA **con el formato** y sin duplicados | "El aceite de oliva virgen extra mas barato" salia dos veces con gold distinto (1 l y 0,5 l) y puntuaba como fallo una respuesta correcta | 0.84 -> 0.88 |
| Prompt de QA que **exige las cifras** y que compare solo formatos equivalentes | El modelo respondia "el mas barato es el de X" sin decir cuanto cuesta, y comparaba 1 l contra 0,5 l como si fueran el mismo producto | (parte del 0.60 -> 0.84) |

## Por que no se mide con un "LLM judge"

Evaluar con el LLM ("dime de 1 a 5 si la respuesta es buena") es subjetivo y
caro: ademas del coste, el juez es otro modelo pequeno con sus sesgos, y
terminaria midiendo la capacidad del juez, no la del sistema. Aqui se
comprueba **contra el ground truth**:

- el dato esperado (un precio, una cadena) aparece en la respuesta;
- los ids citados por el LLM estaban **en el contexto** que se le dio (si no,
  los invento).

Eso es objetivo, reproducible y no depende de un juez. La subjetividad
("¿la respuesta suena bien?") se deja para la revision manual de una
muestra, que es lo que se hace en la demo.

## Limitaciones conocidas de la evaluacion

1. **El dataset es sintetico.** El vocabulario es mas limpio que el de la web
   real: no hay falta de ortografia, ni productos con atributos raros, ni
   descripciones larguisimas. El `recall@k` real sera **peor** que el de aqui.
   Cuando llegue el `.txt` real, estas cifras dan una cota superior, no una
   prediccion.
2. **El ground truth de equivalencias es del propio generador.** El generador
   sabe que "Aceite de oliva virgen extra 1 l" de Mercadona y el de Carrefour
   son el mismo producto porque el generador los creo a los dos. Con datos
   reales hay que etiquetar a mano (y de ahi sale la tarea de "equivalencia
   de productos" del plan).
3. **No hay metricas de latencia de la recuperacion con el LLM real** todavia
   (si las de indexado: 257 productos en 27-62 s con `e5-small` en CPU, casi
   todo el tiempo es cargar el modelo; el embedding de 257 textos es de menos
   de un segundo).
4. **El `recall@1` del catalogo no es comparable** entre modelos si cambia el
   dataset. La comparativa de `docs/01-decision-modelos.md` usa el mismo
   dataset, asi que si es comparable.

## Reproducir todo

```bash
cd flujo-ia
bash setup.sh
python data/generate_dataset.py    # regenera el dataset (semilla fija)
python -m rag.cli index
python -m rag.cli eval --llm none
python -m rag.cli compare
.venv/bin/python -m pytest tests/ -q
```

El generador tiene semilla fija (`SEMILLA = 20261021`): el dataset es
identico en cualquier maquina, asi que las cifras se comparan entre grupos.
