# Diseño de la ingesta — parte de Samuel

Documentación de diseño del **flujo de entrada** del comparador de precios: scrapers,
cluster Kubernetes, mensajería NATS JetStream y normalización con Fission.

> Estado: rama `develop` (actualizado el 12/11/2026). Los esquemas describen lo que hay
> **implementado** en el repo, no lo que se desearía tener.

## Alcance

**Cubre** la cadena completa desde la web del supermercado hasta la cola de salida, que
lee el writer del equipo de API/BD:

```
web del súper  →  scraper (CronJob)  →  NATS raw  →  normalizer  →  NATS clean  →  writer API/BD  →  PostgreSQL
                  └──────────────────────── ingesta (esta parte) ────────────────┘  └──── equipo de API/BD ────┘
```

La parte de API/BD se despliega en el mismo clúster con `infra/api-up.sh` (sin tocar su
código), así que la cadena funciona entera en una sola VM.

**No cubre** (es de otros compañeros): esquema de BD, API REST, Redis, app móvil,
modelo RAG/embeddings y LLM.

## Mapa en 30 segundos

```mermaid
flowchart LR
    subgraph EXT["Fuera del clúster"]
        A["🌐 Internet"]
    end

    subgraph K8S["☸️ Kubernetes · Minikube"]
        direction LR
        subgraph N1["scrappers"]
            B["🕷️ Scraper"]
        end
        subgraph N2["messaging"]
            C["📨 NATS<br/>raw · clean"]
        end
        subgraph N3["fission · ingesta"]
            D["⚙️ Fission"]
        end
        subgraph N4["api · equipo de API/BD"]
            E[("🐘 PostgreSQL<br/>writer + API")]
        end
        B -->|raw| C
        C <-->|"raw · clean"| D
        C -->|clean| E
    end

    A --> B

    classDef cInternet fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px,color:#0d47a1,font-weight:bold
    classDef cScraper fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#1b5e20,font-weight:bold
    classDef cNats fill:#fff8e1,stroke:#fb8c00,stroke-width:2px,color:#e65100,font-weight:bold
    classDef cFission fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px,color:#4a148c,font-weight:bold
    classDef cApi fill:#e0f2f1,stroke:#00897b,stroke-width:2px,color:#004d40,font-weight:bold

    class A cInternet
    class B cScraper
    class C cNats
    class D cFission
    class E cApi

    style EXT fill:#fafafa,stroke:#b0bec5,stroke-dasharray:5 5,color:#546e7a
    style K8S fill:#eef2f7,stroke:#5c6bc0,stroke-width:2px,color:#283593
    style N1 fill:#ffffff,stroke:#43a047
    style N2 fill:#ffffff,stroke:#fb8c00
    style N3 fill:#ffffff,stroke:#8e24aa
    style N4 fill:#ffffff,stroke:#00897b
    linkStyle default stroke:#90a4ae,stroke-width:2px
```

## Índice

| Documento | Contenido |
|---|---|
| [`01-arquitectura.md`](01-arquitectura.md) | Componentes, despliegue en K8s, decisiones de diseño y variables de entorno |
| [`02-flujo-datos.md`](02-flujo-datos.md) | Secuencia end-to-end, ciclo de vida de un producto y cadencia temporal |
| [`03-contratos-datos.md`](03-contratos-datos.md) | Subjects, envelopes, formato de línea limpia con precio unitario canónico, mapeo de Mercadona y contrato Pydantic |
| [`04-estados-y-errores.md`](04-estados-y-errores.md) | Estados, tipos de fallo, reintentos y escenarios límite |
| [`05-pendientes.md`](05-pendientes.md) | Huecos detectados, lo que queda para el equipo de API/BD y siguiente trabajo previsto |
| [`../infra/README.md`](../infra/README.md) | Despliegue con un comando (`up.sh` + Terraform), API/BD en la misma VM (`api-up.sh`), versiones fijadas y problemas conocidos |
| [`../scrappers/README.md`](../scrappers/README.md) | Qué supermercados tienen API y cuáles bloquean |

## Relación con el plan de tareas

Referencia: hoja **Samuel** de `Plan_tareas_PTI.xlsx` (15 tareas).

| Tarea del plan | Estado real | Dónde |
|---|---|---|
| 1. Clúster K8s local, repo y Dockerfile base + scraper Mercadona | Hecha | [`01`](01-arquitectura.md), [`02`](02-flujo-datos.md) |
| 2. Scraper publicando + router Fission + esqueleto del normalizador | Hecha (con cambio de diseño: NATS en vez de HTTP POST) | [`01`](01-arquitectura.md), [`03`](03-contratos-datos.md) |
| 3. Normalizador con Pydantic + cálculo €/L·€/kg + escritura en BD + CronJob | Hecha: la salida `scraper.*.clean` la carga en PostgreSQL el writer de API/BD, probado en la misma VM con `api-up.sh` (queda abierto texto vs JSON) | [`03`](03-contratos-datos.md), [`05`](05-pendientes.md) |
| Despliegue reproducible (Terraform) | Hecho: `infra/up.sh` monta la ingesta desde una VM vacía | [`infra/README.md`](../infra/README.md) |
| 5–6. Más cadenas | **Consum** (API JSON), **Caprabo** (HTML), **Condis** (API JSON del buscador) y **bonÀrea** (JSON interno) activos desde el 11/11: cinco cadenas en total. Carrefour, Alcampo, Dia y Bonpreu bloqueados por antibots, también con Playwright; Veritas viable (ver [`scrappers/README.md`](../scrappers/README.md)) | [`03`](03-contratos-datos.md#mapeo-de-campos-de-consum) |
| 4, 7–15. Presentación de progreso, calidad de datos, ingesta, demos, memoria | No iniciadas | [`05`](05-pendientes.md) |

## Convenciones

- **Namespaces**: `scrappers` (recolectores), `messaging` (NATS), `fission` (instalación
  de Fission), `ingesta` (función `normalizer`, entorno, trigger, pods del pool y consumer)
  y `api` (PostgreSQL, Redis, API y writer, del equipo de API/BD). Con el montaje a mano
  (`setup-vm.sh`) lo de `ingesta` sigue en `default`.
- **Nombres de subject**: `scraper.<cadena>.<estado>`, con `<cadena>` ∈ `mercadona`,
  `consum`, `caprabo`, `condis`, `bonarea` y `<estado>` ∈ `raw` (crudo, 1 mensaje por
  producto), `clean` (normalizado, 1 mensaje por lote).
- **`wh`**: tienda o almacén de la cadena que sirve un código postal (para 08016: `bcn1` en
  Mercadona, `378` en Consum, `8284` en Caprabo, `718` en Condis y `online` en bonÀrea). Viaja en el envelope y en el lote limpio junto a
  `postal_code`. Los códigos postales los dará la app; de momento, 08016 de ejemplo.
