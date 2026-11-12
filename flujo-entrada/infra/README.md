# Infraestructura de la ingesta (Terraform)

Levanta todo el flujo de entrada en un clúster de minikube propio con **un solo comando**:

```bash
bash flujo-entrada/infra/up.sh
```

Y para quitarlo:

```bash
bash flujo-entrada/infra/down.sh          # borra el perfil de minikube
bash flujo-entrada/infra/down.sh --keep   # terraform destroy, deja el clúster
```

Terraform cubre la ingesta (scraper → NATS → normalizador → `scraper.<cadena>.clean`). La
API, la BD y el RAG son de otros equipos y su código no se toca. La frontera con ellos es la
cola de salida: el stream `SCRAPERS` y el subject `scraper.<cadena>.clean`, que el writer de
API/BD lee con su durable `api-writer` (ver [`docs/03-contratos-datos.md`](../docs/03-contratos-datos.md#cola-de-salida-frontera-con-apibd)).
Para tener la cadena entera en la VM, `api-up.sh` despliega su parte tal cual en el mismo
clúster (ver [API y BD en la misma VM](#api-y-bd-en-la-misma-vm-api-upsh)).

## En una VM recién instalada

El único requisito es **Ubuntu o Debian con un usuario con sudo**. No hay que instalar nada
antes:

```bash
git clone <repo> && cd PTI-Q26-27-TARDOR
bash flujo-entrada/infra/up.sh
```

`up.sh` llama primero a [`bootstrap.sh`](bootstrap.sh), que se puede ejecutar por separado y
es idempotente:

| Qué | Cómo | sudo |
|---|---|---|
| `curl`, `python3`, `unzip`, `ca-certificates` | `apt-get` | sí |
| Docker Engine + buildx | Repo oficial de Docker (`download.docker.com`); servicio con `systemctl enable --now` | sí |
| Usuario en el grupo `docker` | `usermod -aG docker`. En la misma sesión, `up.sh` se relanza con `sg docker` para no tener que cerrar sesión | sí |
| `fs.inotify.max_user_instances=512` | `/etc/sysctl.d/99-ingesta-inotify.conf` | sí |
| `kubectl` v1.37.1, `minikube` v1.39.0, `helm` v3.16.3, `terraform` 1.17.1 | Binarios oficiales en `~/.local/bin`, comprobados con sha256 | no |

Si alguna herramienta ya está instalada con otra versión, se respeta y solo se avisa.
`helm` no lo usa `up.sh` (Terraform habla directamente con el clúster), pero queda instalado
para depurar. El CLI `fission` no hace falta.

### Versiones fijadas

Para que dos VMs den el mismo resultado está todo fijado:

- Las herramientas de la tabla anterior y Kubernetes `v1.37.0` (`K8S_VERSION`).
- Los providers de Terraform, en `terraform/.terraform.lock.hcl`, que **hay que commitear**.
- Los charts: NATS 2.15.1, NACK 0.35.0 y fission-all 1.27.0, más los CRDs de Fission de esa
  misma versión.
- Las imágenes: `nats:2.10.29-alpine`, `python:3.13.18-slim` y la base de Fission
  `python-env` fijada por digest.
- Los `requirements.txt` de los scrapers y del normalizador, con `==`, y `nats-py==2.16.0`
  en la imagen del consumer.

No se fijan los paquetes de apt (Docker Engine y los básicos), que instalan la versión estable
del día, ni las imágenes de la parte de API/BD (`python:3.12-slim`, `pgvector/pgvector:pg16`,
`redis:7.4-alpine`): son del equipo de API/BD (ver `docs/05-pendientes.md`).

## Qué hace `up.sh`

1. `bootstrap.sh` (ver arriba).
2. Arranca el perfil de minikube `ingesta` (2 CPU, 4 GB) si no está en marcha y deja
   `kubectl` apuntando a él. El perfil `minikube` de siempre no se toca.
3. `terraform plan` + `apply` (ver abajo). En pantalla solo sale el resumen de qué se crea o
   cambia; el plan completo queda en `terraform/last-plan.txt` (los CRDs de Fission ocupan
   unas 40.000 líneas). Si falla por la red, lo reintenta hasta 3 veces.
4. Prueba de humo: el estado del stream y del consumidor, y `deploy.sh smoke` contra el router
   de Fission.
5. Con `API=1`, [`api-up.sh`](api-up.sh): la API y la BD en el namespace `api` (ver abajo).
6. Con `E2E=1`, [`e2e.sh`](e2e.sh): una pasada real de los scrapers (ver abajo).

Desde cero y comprobando que los datos llegan a la BD:

```bash
bash flujo-entrada/infra/down.sh && API=1 E2E=1 bash flujo-entrada/infra/up.sh
```

Es idempotente: si se vuelve a ejecutar, solo se reconstruye lo que haya cambiado.

## Qué crea Terraform

| Fichero | Recursos | Antes lo hacía |
|---|---|---|
| `images.tf` | `scrapper-mercadona`, `scrapper-consum`, `scrapper-caprabo`, `scrapper-condis`, `scrapper-bonarea`, `normalizer-env` y `normalizer-consumer`: `docker build` + `minikube image load`, y comprueba con `minikube image ls` que han llegado al nodo | Lo mismo, a mano |
| `namespaces.tf` | `scrappers`, `messaging` y `fission` (a partir de `cluster/namespace.yaml`) | `kubectl apply -k cluster/` |
| `nats.tf` | Chart de NATS (con `messaging/nats-values.yaml`), **NACK**, y los CRD `Stream SCRAPERS` y `Consumer normalizer` | `helm install` + `kubectl exec nats-box -- nats request $JS.API...` |
| `fission.tf` | Chart `fission-all` 1.27, `Environment python` con pydantic, `Package` + `Function normalizer`, `HTTPTrigger` (`fission.yaml`) y `normalizer-consumer` (`consumer.yaml`) | `helm install` + `fission env/fn create` + `deploy.sh` |
| `scraper.tf` | `scraper-secrets`, PVC `scraper-out`, CronJobs `scrapper-mercadona`, `scrapper-consum`, `scrapper-caprabo`, `scrapper-condis` y `scrapper-bonarea` (02:00, hora de Madrid) y `scraper-out-cleanup` (01:30, borra los volcados de más de 7 días) | `kubectl apply -k scrappers/...` |

Los YAML de siempre siguen siendo la fuente de verdad: Terraform los lee tal cual y solo
cambia la etiqueta de la imagen.

**Etiquetas por hash.** Cada imagen se etiqueta con el hash de los ficheros que contiene. Si
cambias `consumer.py`, se reconstruye solo esa imagen y el Deployment hace rollout. Con
`normalizer.py` pasa lo mismo: el paquete de Fission se llama `normalizer-<hash>` y la Function
pasa a usar el nuevo. Esto arregla el problema de antes, cuando con la etiqueta fija
(`:v1`/`:v2`) había que forzar un `rollout restart` a mano.

## Namespaces

Todo lo de la ingesta vive en namespaces propios y no toca `default`:

| Namespace | Qué hay |
|---|---|
| `scrappers` | CronJobs `scrapper-mercadona`, `scrapper-consum`, `scrapper-caprabo`, `scrapper-condis`, `scrapper-bonarea` y `scraper-out-cleanup`, `scraper-secrets`, PVC `scraper-out` |
| `messaging` | NATS (StatefulSet), `nats-box`, NACK, CRDs `Stream SCRAPERS` y `Consumer normalizer` |
| `fission` | Plano de control de Fission (router, executor…) |
| `ingesta` | `Environment python`, `Function` y `Package` `normalizer`, `HTTPTrigger`, pods del pool y `normalizer-consumer` |
| `api` | **Despliegue aparte** (`api-up.sh`, del equipo de API/BD): PostgreSQL + pgvector, Redis, API (2 réplicas) y `writer` |

Fission se instala con `defaultNamespace: ingesta`, así que solo vigila ese namespace.
La API/BD, desplegada en el mismo clúster en su namespace `api`, no se pisa con la ingesta;
la única conexión es NATS (`nats://nats.messaging.svc.cluster.local:4222`).

## API y BD en la misma VM (`api-up.sh`)

La API y la BD son del equipo de API/BD (carpeta `api/`), pero se despliegan en el **mismo
clúster** como un despliegue aparte, para que lo que publica la ingesta acabe en PostgreSQL:

```bash
bash flujo-entrada/infra/api-up.sh       # después de up.sh
API=1 bash flujo-entrada/infra/up.sh     # o todo de una vez
```

- No toca nada de `api/`: hace `docker build` de `api/`, `minikube image load` de
  `pti/api:dev` y `kubectl apply -k api/k8s/` (namespace `api`).
- El `writer` lee `scraper.*.clean` con el durable `api-writer` y hace *upsert* en
  PostgreSQL. Al arrancar carga lo que haya en el stream (7 días).
- Al final comprueba `/health` y cuenta productos y precios por cadena.
- Mismo clúster porque el writer llega a NATS por DNS interno
  (`nats.messaging.svc.cluster.local`).
- Quitarlo: `kubectl --context ingesta delete -k api/k8s/` (borra también el volumen de la BD).

Probado el 11/11/2026: 1.331 lotes `clean` cargados en ~4 minutos, 0 errores en el writer;
en la BD, Caprabo 13.068 productos, Condis 7.810, Consum 8.611 (tienda 378) y Mercadona
4.389 (`bcn1`), y `/products/search` compara las cadenas. bonÀrea, añadido después, cargó
6.245 productos (tienda `online`) con 0 errores.

Cada noche el writer añade un precio por producto, tienda y día: eso es el histórico. Para
no perderlo:

- La VM tiene que estar encendida a las 02:00. Si se reinicia, `autostart.sh` (ver abajo)
  vuelve a levantar el clúster, y los CronJobs lanzan la pasada perdida si el clúster vuelve
  antes de 6 h (`startingDeadlineSeconds`).
- El volumen de la BD se borra con `down.sh`, `minikube delete` o `kubectl delete -k api/k8s/`.
  No hay copia: es el único dato que no se puede recuperar (NATS solo guarda 7 días). Un
  `pg_dump` nocturno es decisión del equipo de API/BD (ver `docs/05-pendientes.md`).

## Si la VM se reinicia (`autostart.sh`)

El contenedor de minikube tiene política de reinicio `no`: tras un reinicio de la VM no hay
scrapers, NATS, API ni writer hasta que alguien lance `minikube start -p ingesta`. Para que
vuelva solo:

```bash
bash flujo-entrada/infra/autostart.sh            # una vez; idempotente
bash flujo-entrada/infra/autostart.sh --remove   # quitarlo
```

Con sudo instala una unidad systemd (`minikube-ingesta.service`, después de Docker); sin sudo,
una línea `@reboot` en el crontab del usuario. Al arrancar espera a Docker y hace
`minikube start -p ingesta`; los datos (BD, stream, volcados e imágenes) están en el volumen de
minikube y sobreviven. Log en `~/.minikube-ingesta-autostart.log`. Hay que lanzarlo a mano una
vez: `up.sh` no lo hace porque cambia la configuración del sistema.

Probado el 12/11/2026 con un `sudo reboot` real en la VM: cron lo lanzó ~2 min después de
arrancar y en ~3 min todo estaba en `Running`, con la BD (histórico de dos días), el stream de
NATS y los durables intactos. Algunos pods se reinician una o dos veces al arrancar (la API, el
writer y el consumer arrancan antes que NATS o PostgreSQL): es normal.

## Variables

Se cambian con `-var` o con un `terraform/terraform.tfvars` (está en `.gitignore`). Las
principales son: `minikube_profile`, `postal_codes` (códigos postales que recorren los
scrapers; por defecto `["08016"]`), `fission_namespace_functions` (`ingesta`), las versiones de los charts (`nats_chart_version`,
`nack_chart_version` y `fission_chart_version`), las de JetStream (`stream_name`,
`stream_max_age` y `normalizer_*`) y las de Fission (`fission_env_poolsize` y
`fission_python_base`). Están todas en `terraform/variables.tf`.

`up.sh` además acepta `MINIKUBE_PROFILE`, `MINIKUBE_CPUS`, `MINIKUBE_MEMORY`,
`MINIKUBE_DRIVER`, `K8S_VERSION`, `SKIP_SMOKE=1`, `API=1` y `E2E=1`, además de las versiones de las
herramientas de `bootstrap.sh` (`KUBECTL_VERSION`, `MINIKUBE_VERSION`, `HELM_VERSION`,
`TF_VERSION`).

## Probar una pasada completa

Automática:

```bash
bash flujo-entrada/infra/e2e.sh
```

Lanza un Job desde cada CronJob, espera a que acaben (máximo 90 min), comprueba en el log que el
scraper ha publicado más de 0 productos (detecta el fallo silencioso) y espera a que el
consumidor `normalizer` quede a 0 pendientes y aparezcan lotes nuevos en
`scraper.<cadena>.clean` (máximo 15 min). Después busca errores: en el log del consumer desde
que empezó (`flush-error`, `parse-error`…) y dentro de los lotes `clean` de esta pasada
(líneas `ERROR id=...`, con [`clean_check.py`](clean_check.py)); cualquiera hace fallar la
prueba (`MAX_CLEAN_ERRORS` para tolerar alguno). Lo hace para todas las cadenas a la vez
(`SCRAPERS="mercadona consum caprabo condis bonarea"`, los CronJobs; `SCRAPERS=consum` para uno solo).
Con Caprabo la pasada dura unos 60 minutos. Sale con 0 solo si se cumple
todo.

A mano:

```bash
kubectl --context ingesta -n scrappers create job --from=cronjob/scrapper-mercadona prueba-manual
kubectl --context ingesta -n ingesta logs deploy/normalizer-consumer -f
#   esperado: ~4592 productos -> 92 lotes (91x50 + 42) y 0 errores
kubectl --context ingesta -n scrappers delete job prueba-manual

# la salida se queda en el stream hasta que la lea el writer de API/BD (7 días)
kubectl --context ingesta -n messaging exec deploy/nats-box -- nats -s nats://nats:4222 stream subjects SCRAPERS
```

Sin `api-up.sh` no hay writer, así que los lotes `clean` se acumulan en el stream (7 días).
Cuando se despliega la parte de API/BD, su durable `api-writer` empieza desde el principio y
los carga todos.

## Problemas conocidos (y cómo están resueltos)

| Síntoma | Causa | Solución |
|---|---|---|
| El nodo se queda `NotReady` y `kube-proxy` cae en CrashLoop con "too many open files" | Hay dos clústeres de minikube a la vez y el límite de inotify es de 128 instancias | `bootstrap.sh` lo sube a 512 de forma persistente. Si no se ha podido, `up.sh` lo detecta y se para antes de crear el clúster |
| Router y executor de Fission en CrashLoop con "timeout waiting for function CRD access" | Desde la 1.18, el chart `fission-all` no instala los CRDs | `fission.tf` los descarga del repo de Fission (misma versión) y los aplica antes del chart |
| `helm_release.fission` se queda esperando hasta el timeout | El Service `router` es de tipo LoadBalancer y en minikube nunca recibe IP | `routerServiceType: NodePort` |
| "Error locating chart … 500" | GitHub falla a ratos | `up.sh` reintenta el apply hasta 3 veces. Las releases son `atomic`, así que un intento fallido no deja nada a medias |
| En un contenedor (sin systemd) `bootstrap.sh` instala Docker pero dice "el demonio de docker no esta en marcha" | No hay systemd que arranque `dockerd` | Solo pasa en contenedores, no en una VM. Arranca `dockerd` a mano y repite `up.sh` |
| Un Job de scraper acaba `Failed` con "0 productos", "subcategorías fallidas" o "pasada a medias" | Fallo de red puntual o la web bloquea | Desde el 11/11 el scraper falla en vez de acabar "bien" sin datos, y desde el 12/11 también si se queda a medias (más del 5 % de categorías fallidas; en Consum, más de un 3 % por debajo del total de la API). Kubernetes lo reintenta (2 veces; Caprabo 1); si no, relanza el Job a mano |
| El consumer sigue `Running` pero no procesa | NATS estuvo caído y la conexión se cerró | Desde el 12/11 reintenta sin fin y tiene `livenessProbe`: si lleva más de 2 min sin conexión, Kubernetes lo reinicia |
| Tras reiniciar la VM no hay nada en marcha | El contenedor de minikube no se reinicia solo | `autostart.sh` (ver arriba) |

## Cómo se ha probado

- **VM limpia simulada:** contenedor `ubuntu:24.04` privilegiado con un usuario con sudo y
  nada instalado. `up.sh` instaló Docker, kubectl, minikube, helm y terraform, se relanzó con
  `sg docker`, creó el clúster y aplicó 29 recursos; `E2E=1` pasó (4639 productos → 94 lotes
  en `scraper.mercadona.clean`, 0 errores).
- **Desde cero en la máquina de desarrollo:** `down.sh && E2E=1 up.sh`, RC=0 (4656 productos
  → 94 lotes).
- **Idempotencia:** un segundo `up.sh` da `No changes` en unos 20 s.
- **Con Consum (11/11/2026):** `E2E=1 up.sh` sobre el clúster existente añadió la imagen y el
  CronJob de Consum y cambió el filtro a `scraper.*.raw`; las dos cadenas a la vez:
  Mercadona 4659 productos → 94 lotes, Consum 9338 → 187 lotes, 0 errores, RC=0.
- **Con código postal y Caprabo (11/11/2026):** `E2E=1 up.sh`, los tres scrapers a la vez
  con 08016: Mercadona `bcn1` 4652 → 94 lotes, Consum `378` 8611 → 173, Caprabo `8284` 13068
  → 263 (59 min), 0 errores, RC=0.
- **Con bonÀrea y la API (11/11/2026):** `up.sh` añadió la imagen y el CronJob, y
  `SCRAPERS=bonarea e2e.sh` dio 6245 productos → 125 lotes (17 min), 0 errores; el writer los
  cargó en PostgreSQL (tienda `online`).

## Relación con `setup-vm.sh`

`setup-vm.sh` y `fission/normalizer/deploy.sh` son el montaje a mano de octubre (perfil
`minikube`) y se conservan solo como referencia: montan **solo Mercadona**, con el durable
filtrando `scraper.mercadona.raw`, en el namespace `default`, con imágenes `:v1`/`:v2` y sin
API/BD. Para desplegar, `infra/`. No conviene mezclar los dos en el mismo
clúster: las releases de Helm creadas a mano no están en el estado de Terraform.
