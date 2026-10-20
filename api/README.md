# API · BD · Caché

Flujo de consulta del comparador: **app → FastAPI → Redis (L1) → PostgreSQL + pgvector (L2)**,
y el **writer** que carga en la BD lo que publica la ingesta en `scraper.<cadena>.clean`.

Decisiones y contrato con el resto del equipo: [`docs/CONTRATO.md`](docs/CONTRATO.md).

## Arrancar en local

Requisitos: Docker.

```bash
cd api
docker compose up -d --build                # BD + Redis + API
docker compose exec api python -m app.seed  # datos de demo
```

- Documentación interactiva: http://localhost:8000/docs
- Prueba rápida: http://localhost:8000/products/search?q=aceite

Writer conectado a NATS (por defecto `nats://host.docker.internal:4222`):

```bash
NATS_URL=nats://<host>:4222 docker compose --profile ingesta up -d writer
```

## Desarrollo sin Docker para la API

```bash
cd api
python -m venv .venv && .venv/Scripts/activate   # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d db redis
uvicorn app.main:app --reload
```

## Tests

```bash
docker compose up -d db redis
pytest
```

`tests/test_ingest.py` no necesita BD; `tests/test_api.py` se salta si PostgreSQL no está levantado.

**CI:** `.github/workflows/api.yml` pasa los tests con PostgreSQL y Redis reales, comprueba que
`openapi.json` está al día y construye la imagen en cada push o PR que toque `api/`.

## Despliegue en el clúster

Manifiestos en [`k8s/`](k8s/) (namespace `api`): PostgreSQL + pgvector (StatefulSet con
volumen), Redis, la API con 2 réplicas detrás de un Service (balanceo de carga) y el writer
conectado al NATS de `messaging`.

```bash
minikube image build -t pti/api:dev api/        # imagen dentro de minikube
kubectl apply -k api/k8s/
kubectl -n api exec deploy/api -- python -m app.seed   # opcional: datos de demo
kubectl -n api port-forward svc/api 8000:80            # http://localhost:8000/docs
```

Antes de usarlo fuera de local, cambia la contraseña de `k8s/secret.yaml`.

## Contrato OpenAPI

`openapi.json` se genera desde el código. Tras cambiar un endpoint:

```bash
python scripts/export_openapi.py
```

## Estructura

| Fichero | Qué hace |
|---|---|
| `app/models.py` | Esquema de la BD (tablas `chains`, `stores`, `products`, `prices`) |
| `app/schemas.py` | Formato de las respuestas JSON |
| `app/repository.py` | Consultas SQL |
| `app/main.py` | Endpoints REST |
| `app/cache.py` | Caché Redis con invalidación por versión |
| `app/ingest.py` | Parseo de mensajes `clean` (JSON o texto) y upsert en BD |
| `app/writer.py` | Servicio NATS → BD |
| `app/seed.py` | Datos de demo |
| `app/config.py` | Configuración por variables de entorno |
