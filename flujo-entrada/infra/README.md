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

Solo cubre la ingesta (scraper → NATS → normalizador → `scraper.<cadena>.clean`). La API, la
BD y el RAG son de otros equipos y no se tocan. La frontera con ellos es la cola de salida:
el stream `SCRAPERS` y el subject `scraper.<cadena>.clean`, que el writer de API/BD lee con su
durable `api-writer` (ver [`docs/03-contratos-datos.md`](../docs/03-contratos-datos.md#cola-de-salida-frontera-con-apibd)).

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
- Los `requirements.txt` del scraper y del normalizador, con `==`.

Lo único que no se fija son los paquetes de apt (Docker Engine y los básicos): instala la
versión estable del día.

## Qué hace `up.sh`

1. `bootstrap.sh` (ver arriba).
2. Arranca el perfil de minikube `ingesta` (2 CPU, 4 GB) si no está en marcha y deja
   `kubectl` apuntando a él. El perfil `minikube` de siempre no se toca.
3. `terraform plan` + `apply` (ver abajo). En pantalla solo sale el resumen de qué se crea o
   cambia; el plan completo queda en `terraform/last-plan.txt` (los CRDs de Fission ocupan
   unas 40.000 líneas). Si falla por la red, lo reintenta hasta 3 veces.
4. Prueba de humo: el estado del stream y del consumidor, y `deploy.sh smoke` contra el router
   de Fission.
5. Con `E2E=1`, además, [`e2e.sh`](e2e.sh): una pasada real del scraper (ver abajo).

Desde cero y comprobando que los datos llegan a la cola de salida:

```bash
bash flujo-entrada/infra/down.sh && E2E=1 bash flujo-entrada/infra/up.sh
```

Es idempotente: si se vuelve a ejecutar, solo se reconstruye lo que haya cambiado.

## Qué crea Terraform

| Fichero | Recursos | Antes lo hacía |
|---|---|---|
| `images.tf` | `scrapper-mercadona`, `normalizer-env` y `normalizer-consumer`: `docker build` + `minikube image load`, y comprueba con `minikube image ls` que han llegado al nodo | Lo mismo, a mano |
| `namespaces.tf` | `scrappers`, `messaging` y `fission` (a partir de `cluster/namespace.yaml`) | `kubectl apply -k cluster/` |
| `nats.tf` | Chart de NATS (con `messaging/nats-values.yaml`), **NACK**, y los CRD `Stream SCRAPERS` y `Consumer normalizer` | `helm install` + `kubectl exec nats-box -- nats request $JS.API...` |
| `fission.tf` | Chart `fission-all` 1.27, `Environment python` con pydantic, `Package` + `Function normalizer`, `HTTPTrigger` (`fission.yaml`) y `normalizer-consumer` (`consumer.yaml`) | `helm install` + `fission env/fn create` + `deploy.sh` |
| `scraper.tf` | `scraper-secrets`, PVC `scraper-out` y CronJob `scrapper-mercadona` | `kubectl apply -k scrappers/...` |

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
| `scrappers` | CronJob `scrapper-mercadona`, `scraper-secrets`, PVC `scraper-out` |
| `messaging` | NATS (StatefulSet), `nats-box`, NACK, CRDs `Stream SCRAPERS` y `Consumer normalizer` |
| `fission` | Plano de control de Fission (router, executor…) |
| `ingesta` | `Environment python`, `Function` y `Package` `normalizer`, `HTTPTrigger`, pods del pool y `normalizer-consumer` |

Fission se instala con `defaultNamespace: ingesta`, así que solo vigila ese namespace.
Si otro equipo despliega en el mismo clúster (por ejemplo, la API en su namespace), no se
pisan; la única conexión es NATS (`nats://nats.messaging.svc.cluster.local:4222`).

## Variables

Se cambian con `-var` o con un `terraform/terraform.tfvars` (está en `.gitignore`). Las
principales son: `minikube_profile`, `fission_namespace_functions` (`ingesta`), las versiones de los charts (`nats_chart_version`,
`nack_chart_version` y `fission_chart_version`), las de JetStream (`stream_name`,
`stream_max_age` y `normalizer_*`) y las de Fission (`fission_env_poolsize` y
`fission_python_base`). Están todas en `terraform/variables.tf`.

`up.sh` además acepta `MINIKUBE_PROFILE`, `MINIKUBE_CPUS`, `MINIKUBE_MEMORY`,
`MINIKUBE_DRIVER`, `K8S_VERSION`, `SKIP_SMOKE=1` y `E2E=1`, además de las versiones de las
herramientas de `bootstrap.sh` (`KUBECTL_VERSION`, `MINIKUBE_VERSION`, `HELM_VERSION`,
`TF_VERSION`).

## Probar una pasada completa

Automática:

```bash
bash flujo-entrada/infra/e2e.sh
```

Lanza un Job desde el CronJob, espera a que acabe (máximo 15 min), comprueba en el log que el
scraper ha publicado más de 0 productos (detecta el fallo silencioso) y espera a que el
consumidor `normalizer` quede a 0 pendientes y aparezcan lotes nuevos en
`scraper.mercadona.clean` (máximo 10 min). Sale con 0 solo si se cumple todo.

A mano:

```bash
kubectl --context ingesta -n scrappers create job --from=cronjob/scrapper-mercadona prueba-manual
kubectl --context ingesta -n ingesta logs deploy/normalizer-consumer -f
#   esperado: ~4592 productos -> 92 lotes (91x50 + 42) y 0 errores
kubectl --context ingesta -n scrappers delete job prueba-manual

# la salida se queda en el stream hasta que la lea el writer de API/BD (7 días)
kubectl --context ingesta -n messaging exec deploy/nats-box -- nats -s nats://nats:4222 stream subjects SCRAPERS
```

En este perfil no hay writer, así que los lotes `clean` se acumulan en el stream. Cuando se
despliegue la parte de API/BD en el mismo clúster, su durable `api-writer` empezará desde el
principio y los cargará todos.

## Problemas conocidos (y cómo están resueltos)

| Síntoma | Causa | Solución |
|---|---|---|
| El nodo se queda `NotReady` y `kube-proxy` cae en CrashLoop con "too many open files" | Hay dos clústeres de minikube a la vez y el límite de inotify es de 128 instancias | `bootstrap.sh` lo sube a 512 de forma persistente. Si no se ha podido, `up.sh` lo detecta y se para antes de crear el clúster |
| Router y executor de Fission en CrashLoop con "timeout waiting for function CRD access" | Desde la 1.18, el chart `fission-all` no instala los CRDs | `fission.tf` los descarga del repo de Fission (misma versión) y los aplica antes del chart |
| `helm_release.fission` se queda esperando hasta el timeout | El Service `router` es de tipo LoadBalancer y en minikube nunca recibe IP | `routerServiceType: NodePort` |
| "Error locating chart … 500" | GitHub falla a ratos | `up.sh` reintenta el apply hasta 3 veces. Las releases son `atomic`, así que un intento fallido no deja nada a medias |
| En un contenedor (sin systemd) `bootstrap.sh` instala Docker pero dice "el demonio de docker no esta en marcha" | No hay systemd que arranque `dockerd` | Solo pasa en contenedores, no en una VM. Arranca `dockerd` a mano y repite `up.sh` |
| `scrapper-mercadona` termina con `None 0 items` y "dry-run (0 pendientes)" | Fallo de red puntual: el cliente se traga la excepción y el Job acaba con código 0 | Pendiente en el scraper (ver `docs/05-pendientes.md`, "fallo silencioso"). Se arregla relanzando el Job |

## Cómo se ha probado

- **VM limpia simulada:** contenedor `ubuntu:24.04` privilegiado con un usuario con sudo y
  nada instalado. `up.sh` instaló Docker, kubectl, minikube, helm y terraform, se relanzó con
  `sg docker`, creó el clúster y aplicó 29 recursos; `E2E=1` pasó (4639 productos → 94 lotes
  en `scraper.mercadona.clean`, 0 errores).
- **Desde cero en la máquina de desarrollo:** `down.sh && E2E=1 up.sh`, RC=0 (4656 productos
  → 94 lotes).
- **Idempotencia:** un segundo `up.sh` da `No changes` en unos 20 s.

## Relación con `setup-vm.sh`

`setup-vm.sh` y `fission/normalizer/deploy.sh` siguen funcionando contra el clúster montado a
mano (el perfil `minikube`). Lo nuevo es `infra/`. No conviene mezclar los dos en el mismo
clúster: las releases de Helm creadas a mano no están en el estado de Terraform.
