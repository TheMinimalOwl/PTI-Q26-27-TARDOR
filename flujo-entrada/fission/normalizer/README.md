# normalizer

POST JSON crudo Mercadona -> txt limpio. Sin guardar nada.

- `POST /normalize` con dict, envelope `{"product": {...}}` o `{"items": [...]}`.
- Calcula el **precio unitario canónico** (`€/kg` · `€/l` · `€/ud` · `€/m` · `€/lavado`):
  usa el `reference_price` de la fuente si existe, y si no lo calcula desde
  `unit_price` y el tamaño. Contrato y tabla de conversión:
  `docs/03-contratos-datos.md`.
- **Contrato Pydantic** (`RawProduct`, `NormalizedProduct`, `CleanBatch`) implementado en
  `normalizer.py` a propósito: la función de Fission se empaqueta como una única fuente
  inline (`fission.yaml`). Cada línea se valida; si no cuadra sale `ERROR id=...` y el lote
  continúa. Contrato: `docs/05-pendientes.md`.
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
bash deploy.sh         # entorno + función + trigger + consumer + prueba de humo
bash deploy.sh env     # solo el entorno Fission con pydantic
bash deploy.sh fn      # solo el código de la función (+ trigger HTTP)
bash deploy.sh consumer   # solo el consumer (imagen nueva + rollout)
bash deploy.sh smoke   # solo la prueba de humo contra el router
```

> `bash deploy.sh` funciona aunque git no marque el script como ejecutable (en Windows el
> bit `+x` no se aplica; si hace falta, `chmod +x deploy.sh`).

Qué hace `env`: construye `Dockerfile.env` heredando de la imagen que ya usa el entorno
`python`, la carga en minikube, parchea `spec.runtime.image` (conserva version/builder) y
borra los pods del pool precalentado para que no sirvan la imagen vieja.

Qué hace `fn`: `fission fn create|update --code normalizer.py --entrypoint normalizer.main`
y aplica el `HTTPTrigger` de `fission.yaml`.

El consumer ya instala pydantic desde `requirements.txt` (`Dockerfile.consumer`), así que
`clean_local` valida aunque `NORMALIZE_URL` esté vacío.
