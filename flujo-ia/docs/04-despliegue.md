# 04 · Despliegue

Como llevar el prototipo a la VM y (opcionalmente) al clúster. Hay dos caminos:
**systemd en la VM** (simple, el de la demo) y **Deployment en Kubernetes**
(cuando el servicio se una al resto del sistema).

## 0. Estado del despliegue verificado

Desplegado y probado en la VM `gastly` (Ubuntu 24.04.4, 4 cores, 15 GB RAM,
29 GB disco, **sin GPU**):

| Paso | Comando | Resultado |
|---|---|---|
| Clonar | `git clone -b ai <repo>` | 40 ficheros, 2 commits de la parte de IA |
| Montar | `bash setup.sh` | venv (Python 3.12) + torch CPU + sentence-transformers + dataset + indice (19 s) |
| LLM | `ollama pull qwen3:8b` (instalacion por usuario) | 5.2 GB, 25 s de descarga |
| Probar | `python -m rag.cli ask "..." --llm ollama` | respuesta correcta con cita `[id]` |
| Servicio | `python -m rag.serve` | `/health`, `/search`, `/ask`, `/equiv` respondiendo |
| Evaluar | `python -m rag.cli eval --llm ollama --max-casos 25` | 13 min (66 llamadas al LLM) |

Notas del entorno real:

- La VM **no tiene sudo sin contraseña**, asi que Ollama va instalado por
  usuario (`~/ollama/`) con unidad systemd de usuario. El servicio de RAG
  tambien (`~/.config/systemd/user/flujo-ia.service`).
- `python3 -m venv` falla (`ensurepip` no esta): `setup.sh` lo detecta y
  arranca pip con `get-pip.py`.
- El repo es **privado**: la VM necesita credenciales para `git pull`. Se
  dejaron en `~/.git-credentials` (permisos 600) usando el credential store.

### Acceso y operacion de la VM (datos reales)

| Dato | Valor |
|---|---|
| VM | `gastly`, IP `10.4.41.108` (se alcanza con la VPN FIB / FortiClient activa) |
| Usuario SSH | **`alumne`** (no `joel`) |
| Repo clonado | **`~/TARDOR-test`** (el nombre no es `PTI-Q26-27-TARDOR`) |
| Consola | VNC de OpenNebula Sunstone (`virtech.fib.upc.edu`) |
| Servicio | unidad de usuario `flujo-ia` (`Linger=yes`: se reinicia por SSH sin sesion) |

Despliegue completo desde el portatil en un solo comando:

```bash
ssh alumne@10.4.41.108 'cd ~/TARDOR-test && git pull origin ai && systemctl --user restart flujo-ia'
```

Comprobarlo despues: `curl -s http://10.4.41.108:8080/health` y
`bash scripts/demo-check.sh --url http://10.4.41.108:8080`.

## 1. Requisitos de la VM

El prototipo no necesita GPU. Lo que decide es el **LLM**:

| LLM | RAM para el servicio | RAM total recomendada | Latencia aprox. por respuesta |
|---|---|---|---|
| Sin LLM (`RAG_LLM=none`) | 1.5 GB (embeddings) | 4 GB | instantanea (solo retrieval) |
| `qwen3:4b` | 2.5 GB (modelo) + 2 GB (embeddings) | 8 GB | 5-15 s |
| `qwen3:8b` | 5.2 GB + 2 GB | 12 GB | 8-25 s |
| `qwen3:14b` | 9 GB + 2 GB | 16 GB | 15-45 s |
| `qwen3:30b-a3b` | 18 GB + 2 GB | 24 GB | 20-60 s (3B activos) |
| Gemini (API) | 2 GB | 4 GB | 2-6 s (depende de la red) |

Disco: **8 GB** como minimo (modelo de embeddings 0,5 GB con `e5-small` + modelo
de Ollama 2.5-18 GB + indice). Si el sistema de la VM tiene la particion raiz
llena, `ollama pull` falla con *no space left on device*: hay que mover
`OLLAMA_MODELS` a una particion con espacio (ver mas abajo).

> Los pesos de los embeddings van a `~/.cache/huggingface` (la ubicacion
> estandar de HuggingFace), **no** dentro del repo: asi el clon del proyecto
> no arrastra medio gigabyte y la cache se comparte entre clones.

## 2. Instalacion en la VM

```bash
git clone <repo> && cd PTI-Q26-27-TARDOR/flujo-ia
bash setup.sh --with-ollama      # venv + deps + dataset + indice + modelo
bash setup.sh --verify           # comprueba el estado
```

`setup.sh` es idempotente. Si el sistema no tiene `python3-venv` (habitual en
Debian/Ubuntu), lo detecta y arranca `pip` a mano; si `/tmp` esta en la
particion del sistema, mueve el temporal a la cache del proyecto.

### Donde van los modelos

Ollama guarda los modelos en `/usr/share/ollama/.ollama/models` cuando corre
como servicio del sistema, y esa particion suele ser la pequena. Para moverlos:

```bash
sudo systemctl edit ollama      # o: sudo systemctl edit --full ollama
```

```ini
[Service]
Environment="OLLAMA_MODELS=/home/joelfurca/.ollama/models"
```

```bash
sudo systemctl restart ollama
```

Igual con HuggingFace: `HF_HOME` (lo usa `setup.sh` y el servicio systemd).

## 2bis. Ollama sin sudo (instalacion por usuario)

El `install.sh` de Ollama necesita sudo (instala el servicio del sistema). Si
no hay sudo en la maquina, la instalacion por usuario funciona igual y es la
que se ha probado en la VM:

```bash
VER=v0.40.7
curl -fL https://github.com/ollama/ollama/releases/download/$VER/ollama-linux-amd64.tar.zst -o ollama.tar.zst
zstd -d -c ollama.tar.zst | tar -x -C ollama        # necesita el paquete zstd
export OLLAMA_MODELS=$HOME/.ollama/models
setsid nohup env OLLAMA_MODELS=$OLLAMA_MODELS OLLAMA_HOST=127.0.0.1:11434 \
  $HOME/ollama/bin/ollama serve > $HOME/ollama.log 2>&1 < /dev/null &
$HOME/ollama/bin/ollama pull qwen3:8b
```

> [!IMPORTANT]
> **No se puede borrar la carpeta `lib/`.** El binario `ollama` busca al
> servidor de inferencia en `<dir del binario>/../lib/ollama/llama-server`.
> Si se copia solo `bin/ollama`, el modelo se descarga pero toda inferencia
> falla con `llama-server binary not found`.

### Como servicio (usuario), para que sobreviva a un reinicio

Las dos unidades estan en el repo: `deploy/ollama.service` y
`deploy/flujo-ia.service` (son unidades **de usuario**, con `%h`):

```bash
mkdir -p ~/.config/systemd/user
cp deploy/ollama.service deploy/flujo-ia.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ollama flujo-ia
```

Para que arranque sin sesion abierta (por ejemplo, tras un reinicio por SSH):

```bash
sudo loginctl enable-linger $USER
```

### Y el servicio de RAG

Igual, en `~/.config/systemd/user/flujo-ia.service` (plantilla en
`deploy/flujo-ia.service`): `After=... ollama.service`, `RAG_LLM=ollama` y
`OLLAMA_HOST=http://127.0.0.1:11434`.

## 3. Camino A · systemd en la VM (el de la demo)

```bash
sudo cp deploy/flujo-ia.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now flujo-ia
systemctl status flujo-ia
curl -s localhost:8080/health | python3 -m json.tool
```

Editar `deploy/flujo-ia.service` antes de copiarlo: `User`, `WorkingDirectory`
y las rutas tienen que ser las de la maquina.

Si el LLM es local, Ollama tambien tiene que estar como servicio (lo instala
`setup.sh --with-ollama`). Con Gemini en vez de local, basta con
`RAG_LLM=gemini` y la clave en `Environment=GEMINI_API_KEY=...` (mejor en un
fichero aparte con permisos 600, no en la unit a pelo).

### Probarlo

```bash
curl -s localhost:8080/health | python3 -m json.tool

curl -s localhost:8080/search -H 'Content-Type: application/json' \
  -d '{"query":"aceite de oliva virgen extra","k":5}' | python3 -m json.tool

curl -s localhost:8080/ask -H 'Content-Type: application/json' \
  -d '{"question":"¿cual es el aceite de oliva mas barato por litro?"}' | python3 -m json.tool

curl -s localhost:8080/equiv -H 'Content-Type: application/json' \
  -d '{"id":"10001","chain":"carrefour"}' | python3 -m json.tool
```

## 4. Camino B · Kubernetes

```bash
# Imagen (el Dockerfile hornea el modelo y el indice: el contenedor arranca
# sin red)
docker build -t flujo-ia:v1 .
minikube image load flujo-ia:v1

# Secret con la clave (si se usa Gemini)
kubectl create secret generic ia-secrets -n ia --from-literal=GEMINI_API_KEY="$GEMINI_API_KEY"

kubectl apply -k deploy/k8s/
kubectl -n ia get pods,svc
```

Notas:

- El `Deployment` deja `RAG_LLM=none` por defecto: el contenedor del clúster no
  ve el Ollama de la VM. Para hablar con el LLM hay dos opciones:
  1. **`host.docker.internal:11434`** (como esta en el manifiesto): el
     Minikube corre en la misma maquina, asi que el pod puede alcanzar el
     Ollama de la VM. Hay que permitirlo: en el nodo,
     `echo "host.docker.internal host-gateway" >> /etc/hosts`.
  2. **Gemini por API**: cambiar `RAG_LLM=gemini` y crear el secret. Es lo
     mas simple si la clave esta disponible.
- **Recursos**: el contenedor carga el modelo de embeddings (2 GB) al arrancar,
  asi que el limite de memoria (4 Gi) tiene que holgar.
- Si el indice cambia, la imagen hay que reconstruirla. La alternativa es
  montar la cache como volumen (`emptyDir` o PVC) y recalcular el indice en un
  `Job` que se lance cuando llega un lote nuevo.

## 5. Datos reales: del `clean` al indice

El prototipo consume lineas limpias. Para pasarle el dato real del equipo de
ingesta:

```bash
# El consumer de ingesta publica en el subject scraper.<cadena>.clean
# (texto plano). Se copia ese texto a data/raw/<cadena>_clean.txt
cp mercadona_20261021T190000Z.txt data/raw/mercadona_clean.txt

python -m rag.cli index       # reindexa (el indice anterior se conserva)
```

El parser acepta el formato tal cual (mismo separador ` | `, misma cabecera
`Items:` / `Unitarios:` / `---`), incluidas las lineas `ERROR id=...` y las
lineas incompletas `- (sin_precio)`, que se indexan igual (su `id` y su
nombre siguen sirviendo para buscar).

**Lo que hay que rehacer con datos reales** es el *ground truth* de
equivalencias: con el sintetico lo genera el propio generador; con el real hay
que etiquetar los pares a mano (es la tarea 6 del plan). El resto de la
evaluacion (catalogo y QA) se puede autogenerar del propio `.txt`.

## 6. Reindexado automatico (pendiente de decidir)

En produccion el indice tiene que seguir a los datos. Dos opciones, y la
decision es del equipo:

| Opcion | Quien reindexa | Ventaja | Inconveniente |
|---|---|---|---|
| A | El `normalizer-consumer` de ingesta, al publicar el lote `clean` | No hay que coordinationar nada | El consumer pasa a depender del servicio de IA |
| B | Un `CronJob` que lee el subject y reindexa | Desacoplado | Latencia: el indice va con retraso |

La opcion B es la que menos acopla: el prototipo puede leer el subject
`scraper.mercadona.clean` directamente con un consumidor NATS y reindexar. Es
un desarrollo pequeno (el cliente `nats-py` ya lo usa el consumer de ingesta).

## 7. PostgreSQL + pgvector (integracion con los datos del equipo)

**Decision del equipo (18/11)**: los datos viven en PostgreSQL con pgvector
(creado por el equipo de BD) y el RAG los lee de ahi. La API y el contrato
no cambian: solo cambia por donde coge los productos el `Retriever`.

Como en la VM el servicio RAG y la BD corren en la misma maquina, la
conexion es local (`127.0.0.1:5432`) y **no hay que exponer el puerto 5432**
para que el servicio funcione.

### Como se integra (checklist)

```bash
# 1. Instalar psycopg en el venv del servicio (una vez)
ssh alumne@10.4.41.108 'cd TARDOR-test/flujo-ia && .venv/bin/pip install -r requirements.txt'

# 2. Variables de entorno en la unidad del servicio
#    ~/.config/systemd/user/flujo-ia.service  (apartado [Service])
#      Environment=RAG_STORE=pg
#      Environment=RAG_PG_DSN=postgresql://USUARIO:CLAVE@127.0.0.1:5432/BASE
#    Si el esquema del equipo tiene otros nombres de tabla/columna:
#      Environment=RAG_PG_TABLE=productos
#      Environment=RAG_PG_COL_VECTOR=embedding
#      Environment=RAG_PG_COL_NAME=nombre        (y asi con cada campo)
#    Luego: systemctl --user daemon-reload && systemctl --user restart flujo-ia

# 3. Diagnostico: conexion, esquema, dimension de los vectores y busqueda
cd TARDOR-test/flujo-ia
.venv/bin/python -m rag.cli pg-check

# 4. Si faltan embeddings en la tabla, se rellenan con nuestro modelo
.venv/bin/python -m rag.cli pg-sync

# 5. Verificar: /health tiene que decir "store": "pg"
curl -s localhost:8080/health
```

Si algo falla en cualquier punto, **el servicio no se cae**: `cargar_store`
vuelve al indice local y `/health` lo publica como `"store": "local"` con
el motivo en `store_error`. La demo funciona igual (plan B).

Notas de integracion:

- Los vectores de la BD tienen que ser del **mismo modelo y dimension**
  que los del servicio (`e5-small`, 384): `pg-check` lo comprueba antes de
  dejarte activar `RAG_STORE=pg`.
- El esquema no hace falta que coincida al 100%: al arrancar se mira
  `information_schema` y solo se usan las columnas que existen. Los filtros
  sobre una columna que falta dan un error claro (mejor que devolver
  resultados sin filtrar).
- `pg-check` y `pg-sync` aceptan `--dsn` para probar otra conexion sin
  tocar el entorno.

### Server MCP

`rag/mcp_server.py` expone el RAG por el protocolo MCP (transporte stdio):
lo lanza el cliente (Claude Code, otro agente) como subproceso y habla por
stdin/stdout. No carga modelos: consume la API que ya esta en marcha.

```bash
# arrancarlo a mano (en la VM)
cd TARDOR-test/flujo-ia && .venv/bin/python -m rag.mcp_server

# desde el portatil, como "command" de un cliente MCP:
ssh alumne@10.4.41.108 "cd TARDOR-test/flujo-ia && .venv/bin/python -m rag.mcp_server"
```

Tools: `estado`, `buscar`, `preguntar`, `equivalencia` (API `:8080`) y
`consulta_productos`, `productos_similares` (pgvector; sin `RAG_PG_DSN`
explican que falta configurarla en vez de fallar).

## 8. Checklist antes de la demo

- [ ] `bash setup.sh --verify` dice que el indice existe
- [ ] `python -m rag.cli eval --llm none` da las metricas esperadas
- [ ] `python -m rag.cli ask "..." --llm ollama` responde con citas
- [ ] `curl localhost:8080/health` devuelve `"ok": true`
- [ ] La clave de Gemini **no** esta en el repo ni en un fichero con permisos
      abiertos
- [ ] Hay espacio en disco para el modelo (`df -h`)
