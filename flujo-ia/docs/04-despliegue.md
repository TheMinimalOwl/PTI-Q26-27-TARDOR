# 04 · Despliegue

Como llevar el prototipo a la VM y (opcionalmente) al clúster. Hay dos caminos:
**systemd en la VM** (simple, el de la demo) y **Deployment en Kubernetes**
(cuando el servicio se una al resto del sistema).

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

Disco: **8 GB** como minimo (modelo de embeddings 2.2 GB + modelo de Ollama
2.5-18 GB + indice). Si el sistema de la VM tiene la particion raiz llena,
`ollama pull` falla con *no space left on device*: hay que mover `OLLAMA_MODELS`
a una particion con espacio (ver mas abajo).

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

## 7. Checklist antes de la demo

- [ ] `bash setup.sh --verify` dice que el indice existe
- [ ] `python -m rag.cli eval --llm none` da las metricas esperadas
- [ ] `python -m rag.cli ask "..." --llm ollama` responde con citas
- [ ] `curl localhost:8080/health` devuelve `"ok": true`
- [ ] La clave de Gemini **no** esta en el repo ni en un fichero con permisos
      abiertos
- [ ] Hay espacio en disco para el modelo (`df -h`)
