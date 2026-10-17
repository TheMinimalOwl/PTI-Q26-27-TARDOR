# normalizer

POST JSON crudo Mercadona -> txt limpio. Sin guardar nada.

- `POST /normalize` con dict, envelope `{"product": {...}}` o `{"items": [...]}`.
- Calcula el **precio unitario canónico** (`€/kg` · `€/l` · `€/ud` · `€/m` · `€/lavado`):
  usa el `reference_price` de la fuente si existe, y si no lo calcula desde
  `unit_price` y el tamaño. Contrato y tabla de conversión:
  `docs/03-contratos-datos.md`.
- **Contrato Pydantic** (`RawProduct`, `NormalizedProduct`, `CleanBatch`) implementado en
  `normalizer.py` a propósito: el consumer reutiliza el módulo y la función de Fission se
  sube como una única fuente (`fission fn create|update --code normalizer.py`, ver
  `deploy.sh`). Cada línea se valida; si no cuadra sale `ERROR id=...` y el lote continúa.
  Contrato: `docs/05-pendientes.md`.
- Variante estructurada **opt-in**: `POST /normalize?format=json` devuelve un `CleanBatch`
  (`{source, wh, ts, batch, items[]}`). Es estricta: valida también la entrada y responde
  `422` si un crudo no valida.

Pruebas locales (sin cluster):

- `python test_local.py` — normaliza el último `scrapper_mercadona/out/mercadona_*.txt`.
- `python test_unit_price.py` — casos del precio unitario + validación sobre datos reales.
- `python test_models.py` — contrato Pydantic, tolerancia por item y endpoint.

## Despliegue

Pydantic **no** está en la imagen `python` prebuilt de Fission, y la función lo necesita.
Hay un script idempotente que se ejecuta **en la VM del clúster** (necesita docker, minikube,
kubectl y el CLI `fission`):

```bash
bash deploy.sh            # entorno + función + trigger + consumer + prueba de humo
bash deploy.sh env        # solo el entorno Fission con pydantic
bash deploy.sh fn         # solo el código de la función (+ trigger HTTP)
bash deploy.sh consumer   # solo el consumer (imagen nueva + rollout)
bash deploy.sh smoke      # solo la prueba de humo contra el router
```

> `bash deploy.sh` funciona aunque git no marque el script como ejecutable (en Windows el
> bit `+x` no se aplica; si hace falta, `chmod +x deploy.sh`).

**Qué hace `env`:** construye `Dockerfile.env` heredando de la imagen que ya usa el entorno
`python` (la detecta del CRD), la carga en minikube, parchea `spec.runtime.image` (conserva
`version`/`builder`/`poolsize`), borra los pods del pool precalentado y **comprueba dentro
de un pod del pool que `import pydantic` funciona**. Si el build falla porque la base no
está en el docker local, prueba `docker pull` y, si no, sugiere `eval $(minikube docker-env)`
o `FISSION_PY_ENV=<imagen>`.

**Qué hace `fn`:** `fission fn update --code normalizer.py --entrypoint normalizer.main`
(reutiliza el paquete existente `normalizer-<uuid>`) y crea el `HTTPTrigger` de
`fission.yaml` **solo si no existe** (en este clúster lo creó el CLI, y aplicarlo encima
solo genera avisos de propiedad).

**Qué hace `smoke`:** `port-forward` al `svc/router`, un `POST /normalize` con un producto
de ejemplo y la comprobación de que la línea limpia y el JSON salen **exactamente** como
toca (`3.45EUR/l … src=fuente`).

El consumer ya instala pydantic desde `requirements.txt` (`Dockerfile.consumer`), así que
`clean_local` valida aunque `NORMALIZE_URL` esté vacío.

## Clúster desplegado (17/10/2026)

| Qué | Valor |
|---|---|
| Clúster | minikube 1.39.0, Kubernetes v1.37.0, un nodo |
| Fission | v1.27.0 (cliente y servidor) |
| Entorno | `python` en `default`, `runtime.image: ghcr.io/fission/python-env`, `version: 3`, `poolsize: 3` |
| Función | `normalizer` (env `python`, executor `poolmgr`) |
| Paquete | `normalizer-<uuid>`, `build_status: none` (subido con `--code`) |
| Trigger | `normalizer-http`, `[POST] /normalize`, ns `default` |
| Router | `svc/router` (LoadBalancer, puerto 80; `port-forward` para probar) |
| Consumer | `deployment/normalizer-consumer` en `default` (1/1) |

Por eso el despliegue del código va por CLI y no aplicando un YAML de `Function`: el CRD no
tiene `entrypoint` ni `functionSource` (el entrypoint vive en `spec.package.functionName`) y
el paquete lo nombra el CLI con un uuid.

### Gotchas del CRD (v1.27)

| Campo | Correcto | Error que da si no |
|---|---|---|
| `Function.spec.package.functionName` | entrypoint (`normalizer.main`) | no existe `spec.entrypoint` |
| `HTTPTrigger.spec.functionref.type` | `name` | `Unsupported value: "Function": supported values: "name", "function-weights"` |
| `HTTPTrigger.spec.methods` | lista (`[POST]`) | `spec.method` está deprecado |
