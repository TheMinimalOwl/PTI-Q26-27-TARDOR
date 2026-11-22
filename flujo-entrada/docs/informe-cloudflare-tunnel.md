# Informe: Cloudflare Tunnel en la VM

Estado revisado en la VM `krabby` (10.4.41.114), clúster minikube `ingesta`, el 22/11/2026.

## Resumen

La API (FastAPI del equipo de API/BD) se publica en internet en
**`https://api.superahorro.app`** con un **Cloudflare Tunnel con nombre** de la cuenta del
equipo. Corre como un Deployment `cloudflared` dentro del propio clúster. Abre conexiones
**salientes** desde la VM hacia la red de Cloudflare, así que funciona aunque a la VM solo se
llegue por la VPN de la FIB y no tenga ningún puerto de entrada abierto.

- URL fija: `https://api.superahorro.app` (`/health` → 200 en ~0,13 s desde la VM; la
  respuesta sale por el edge `MAD`).
- Sustituye, desde el 22/11/2026, al *quick tunnel* que había desde el 18/11
  (`https://<aleatorio>.trycloudflare.com`, URL que cambiaba en cada reinicio del pod).

## Arquitectura

```
Cliente (internet)
   │ HTTPS
   ▼
Cloudflare edge (mad01/05/06/07) ── https://api.superahorro.app
   ▲
   │ 4 conexiones QUIC (UDP 7844) por réplica, iniciadas DESDE la VM, de salida
   │
┌──┴──────────────── VM krabby · minikube "ingesta" · namespace api ───────────┐
│  Deployment cloudflared (2 réplicas, `tunnel run`)                           │
│     └─ http://api.api.svc.cluster.local:80   (ruta definida en el panel)     │
│            └─ Service api (ClusterIP 80 → 8000)                              │
│                   └─ Deployment api (2 réplicas, pti/api:dev) → postgres     │
└──────────────────────────────────────────────────────────────────────────────┘
```

Cloudflare termina el TLS en su edge y manda las peticiones por el túnel a cualquiera de las
dos réplicas. `cloudflared` las reenvía en HTTP plano al Service `api` del clúster, que las
reparte entre las dos réplicas de la API.

## Piezas en el repositorio

| Fichero | Qué hace |
|---|---|
| [`infra/tunnel/cloudflared.yaml`](../infra/tunnel/cloudflared.yaml) | Manifiesto del Deployment `cloudflared` (hostname; el token lo lee del Secret) |
| [`infra/tunnel-up.sh`](../infra/tunnel-up.sh) | Despliega y comprueba, da la URL o quita el túnel |
| [`infra/README.md`](../infra/README.md#api-pública-tunnel-upsh) | Documentación de uso |

El quick tunnel se añadió en el commit `86680ec`. El paso a túnel con nombre no toca nada del
código de `api/`.

### El Deployment (`tunnel/cloudflared.yaml`)

- Imagen `cloudflare/cloudflared:2026.10.7`, fijada a una versión (no `latest`).
- Argumentos: `tunnel --no-autoupdate --metrics 0.0.0.0:2000 run`, con el token en la variable
  de entorno `TUNNEL_TOKEN`, leída del Secret `api/cloudflared-token` (`secretKeyRef`). El
  token no está en el repositorio, que es público.
  - `run` + token es lo que hace que sea un túnel con nombre: el túnel, su hostname público y
    el servicio de destino (`http://api.api.svc.cluster.local:80`) se configuran en el panel
    de Cloudflare (Zero Trust > Networks > Tunnels), no en el manifiesto.
  - `--no-autoupdate`: en un contenedor la versión la decide la imagen, no el binario.
  - `--metrics`: expone `/ready` y `/metrics` (Prometheus) en el puerto 2000.
- Anotación `superahorro/hostname: "api.superahorro.app"`: solo la lee `tunnel-up.sh` para dar
  la URL y probar `/health`.
- `replicas: 2` con `RollingUpdate` (`maxUnavailable: 0`, `maxSurge: 1`): las dos réplicas se
  registran en el mismo túnel, así que un rollout no corta el servicio.
- Sondas readiness y liveness sobre `GET /ready` del puerto de métricas. `/ready` devuelve 200
  solo si hay al menos una conexión registrada con el edge. Si se pierde la conexión durante
  ~2,5 min (5 fallos × 30 s), Kubernetes reinicia el pod.
- Recursos: request de 10m de CPU y 32Mi de memoria; límite de 128Mi de memoria.

### El script (`tunnel-up.sh`)

```bash
TUNNEL_TOKEN=<token> bash flujo-entrada/infra/tunnel-up.sh   # la 1a vez: guarda el token
bash flujo-entrada/infra/tunnel-up.sh          # despliega (idempotente) y comprueba
bash flujo-entrada/infra/tunnel-up.sh --url    # la URL pública
bash flujo-entrada/infra/tunnel-up.sh --down   # borra el Deployment
```

1. Lee el hostname de la anotación `superahorro/hostname` y falla si aún tiene el valor de
   ejemplo (`PON_AQUI...`).
2. Comprueba que existe el Service `api` en el namespace `api` (antes hay que lanzar
   `api-up.sh`). Si se le pasa `TUNNEL_TOKEN`, crea o actualiza el Secret
   `cloudflared-token`; si no, exige que ya exista.
3. `kubectl apply` del manifiesto y espera al `rollout status`.
4. Cuenta las líneas `Registered tunnel connection` de los logs de los pods (hasta 30 intentos
   de 2 s).
5. Espera a que `GET https://<hostname>/health` dé 200 (hasta 10 intentos de 3 s). Si no, avisa
   de revisar la ruta del hostname en el panel.

Usa el contexto de kubectl `ingesta` (o el de `MINIKUBE_PROFILE`).

## Estado real en la VM

```
deployment.apps/cloudflared   2/2   cloudflare/cloudflared:2026.10.7
pod/cloudflared-6cbdcd8947-sgk79   Running   0 reinicios   desde 22/11 13:17 UTC
pod/cloudflared-6cbdcd8947-rh7qx   Running   0 reinicios   desde 22/11 13:17 UTC
```

- 8 conexiones registradas con el edge (4 por réplica) en varios centros de Madrid (`mad01`, `mad05`, `mad06`, `mad07`…). El token lo leen del Secret `cloudflared-token`.
- Desde internet, `/health` y `/docs` responden 200. El `openapi.json` incluye
  `/products/search-vector`, `/products/semantic-search` y `/shopping-list/optimize`, y
  `GET /products/semantic-search?q=aceite de oliva` devuelve productos.

### Incidencias vistas con el quick tunnel (18–22/11)

- **Cortes de conexión con el edge** el 18/11 a las 16:39 UTC (~2 min) y el 19/11 a las
  21:08 UTC (~1 min): `timeout: no recent network activity` por QUIC. Con una sola réplica y
  una conexión, la API no se veía desde fuera durante el corte. Con 2 réplicas y 8 conexiones,
  un corte así ya no debería dejarla inaccesible.
- **`Failed to refresh feature selector ... lookup cfd-features.argotunnel.com on
  10.96.0.10:53: server misbehaving`**, cada pocas horas. Falla la resolución DNS de CoreDNS
  para ese nombre concreto. No afecta al tráfico: es solo la consulta de *feature flags*.
- **`Your version 2026.10.7 is outdated`**: hay una 2026.11.1. Aviso diario sin impacto.
- **`failed to sufficiently increase receive buffer size`** (quic-go): el kernel limita el
  buffer UDP a 416 KiB, y quic-go pide 7 MiB. Con el uso actual no se nota.

## Limitaciones

1. **El token solo está en el clúster** (Secret `api/cloudflared-token`). Quien lo tenga puede
   conectar conectores al túnel y recibir el tráfico de `api.superahorro.app`; si se pierde la
   VM, hay que volver a sacarlo del panel.
2. **Sin autenticación ni límite de peticiones**: cualquiera puede leer la API y `/docs`, y
   la API ya tiene rutas `POST` (`/products/search-vector`, `/shopping-list/optimize`) que
   hacen trabajo en la BD y en la IA.
3. **Sin monitorización**: Prometheus/Grafana (`monitoring/`) no recoge las métricas del
   puerto 2000 de `cloudflared`, y no hay ninguna alerta si se cae el túnel.
4. **La ruta vive en el panel de Cloudflare**: el destino `http://api.api.svc.cluster.local:80`
   no está en el repositorio. Si alguien la cambia en el panel, `tunnel-up.sh` solo lo detecta
   porque `/health` deja de dar 200.

## Recomendaciones

| Prioridad | Acción |
|---|---|
| Media | Límite de peticiones (regla de *rate limiting* de Cloudflare sobre `api.superahorro.app`, o en la API), sobre todo para las rutas `POST`. |
| Media | Añadir `cloudflared` como target de Prometheus (puerto 2000) y una alerta con `cloudflared_tunnel_ha_connections == 0`. |
| Baja | Subir la imagen a `2026.11.1`. |
| Baja | Revisar por qué CoreDNS falla con `cfd-features.argotunnel.com` (probablemente el DNS de subida de la VM con registros TXT). |
