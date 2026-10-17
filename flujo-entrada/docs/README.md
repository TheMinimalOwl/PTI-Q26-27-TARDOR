# Diseño de la ingesta — parte de Samuel

Documentación de diseño del **flujo de entrada** del comparador de precios: scrapers,
cluster Kubernetes, mensajería NATS JetStream y normalización con Fission.

> Estado: `scrapping` @ `ed5aa47` (15/10/2026). Los esquemas describen lo que hay
> **implementado** en el repo, no lo que se desearía tener.

## Alcance

**Cubre** la cadena completa desde la web del supermercado hasta la frontera con el
equipo de API/BD:

```
web del súper  →  scraper (CronJob)  →  NATS raw  →  normalizer  →  NATS clean  →  [ API/BD ]
```

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
        subgraph N3["default"]
            D["⚙️ Fission"]
        end
        B --> C
        C --> D
    end

    A --> B

    classDef cInternet fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px,color:#0d47a1,font-weight:bold
    classDef cScraper fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#1b5e20,font-weight:bold
    classDef cNats fill:#fff8e1,stroke:#fb8c00,stroke-width:2px,color:#e65100,font-weight:bold
    classDef cFission fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px,color:#4a148c,font-weight:bold

    class A cInternet
    class B cScraper
    class C cNats
    class D cFission

    style EXT fill:#fafafa,stroke:#b0bec5,stroke-dasharray:5 5,color:#546e7a
    style K8S fill:#eef2f7,stroke:#5c6bc0,stroke-width:2px,color:#283593
    style N1 fill:#ffffff,stroke:#43a047
    style N2 fill:#ffffff,stroke:#fb8c00
    style N3 fill:#ffffff,stroke:#8e24aa
    linkStyle default stroke:#90a4ae,stroke-width:2px
```

## Índice

| Documento | Contenido |
|---|---|
| [`01-arquitectura.md`](01-arquitectura.md) | Componentes, despliegue en K8s, decisiones de diseño y variables de entorno |
| [`02-flujo-datos.md`](02-flujo-datos.md) | Secuencia end-to-end, ciclo de vida de un producto y cadencia temporal |
| [`03-contratos-datos.md`](03-contratos-datos.md) | Subjects, envelopes, formato de línea limpia con precio unitario canónico y mapeo de Mercadona |
| [`04-estados-y-errores.md`](04-estados-y-errores.md) | Estados, tipos de fallo, reintentos y escenarios límite |
| [`05-pendientes.md`](05-pendientes.md) | Huecos detectados y siguiente trabajo previsto en el plan |

## Relación con el plan de tareas

Referencia: hoja **Samuel** de `Plan_tareas_PTI.xlsx` (15 tareas).

| Tarea del plan | Estado real | Dónde |
|---|---|---|
| 1. Clúster K8s local, repo y Dockerfile base + scraper Mercadona | Hecha | [`01`](01-arquitectura.md), [`02`](02-flujo-datos.md) |
| 2. Scraper publicando + router Fission + esqueleto del normalizador | Hecha (con cambio de diseño: NATS en vez de HTTP POST) | [`01`](01-arquitectura.md), [`03`](03-contratos-datos.md) |
| 3. Normalizador con Pydantic + cálculo €/L·€/kg + escritura en BD + CronJob | Parcial (cálculo €/L·€/kg, contrato Pydantic y despliegue en la VM **hechos**; falta conectar la BD) | [`03`](03-contratos-datos.md), [`05`](05-pendientes.md) |
| 4–15. Presentación de progreso, Alcampo/Ahorramás, calidad de datos, ingesta, demos, memoria | No iniciadas | [`05`](05-pendientes.md) |

## Convenciones

- **Namespaces**: `scrappers` (recolectores), `messaging` (NATS), `fission` (instalación
  de Fission), `default` (función `normalizer`, trigger y consumer).
- **Nombres de subject**: `<recurso>.<cadena>.<estado>` → `scraper.mercadona.raw`,
  `scraper.mercadona.clean`.
- **`wh`**: etiqueta de almacén/tienda que viaja en el envelope. Hoy siempre `default`;
  es el gancho para multi-tienda (datos de supermercados cercanos).
