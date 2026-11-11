# Fission + entorno con pydantic + funcion `normalizer` + trigger HTTP + consumer.
# Sustituye a `fission env create`, `fission fn create` y deploy.sh: todo son manifiestos,
# asi que no hace falta el CLI `fission`.

# Desde Fission 1.18 el chart no trae los CRDs: hay que aplicarlos antes (en la VM se
# hizo a mano con `kubectl create -k github.com/fission/fission/crds/v1?ref=v1.27.0`).
locals {
  fission_crds = [
    "canaryconfigs", "environments", "fissiontenants", "functions", "httptriggers",
    "kuberneteswatchtriggers", "messagequeuetriggers", "packages", "timetriggers",
  ]
}

data "http" "fission_crd" {
  for_each = toset(local.fission_crds)
  url      = "https://raw.githubusercontent.com/fission/fission/v${var.fission_chart_version}/crds/v1/fission.io_${each.key}.yaml"

  lifecycle {
    postcondition {
      condition     = self.status_code == 200
      error_message = "No he podido descargar el CRD ${each.key} de Fission v${var.fission_chart_version}."
    }
  }
}

resource "kubectl_manifest" "fission_crd" {
  for_each = data.http.fission_crd
  # sensitive: solo para que el plan no imprima los ~40.000 lineas de los CRDs.
  yaml_body = sensitive(each.value.response_body)
  # Los CRDs son grandes: con client-side apply no caben en la anotacion last-applied.
  server_side_apply = true
  wait              = true
}

resource "helm_release" "fission" {
  name       = "fission"
  namespace  = "fission"
  repository = "https://fission.github.io/fission-charts/"
  chart      = "fission-all"
  version    = var.fission_chart_version
  wait       = true
  atomic     = true # si falla, desinstala: el siguiente up.sh empieza limpio
  timeout    = 600

  # Por defecto el router es LoadBalancer: en minikube nunca recibe IP externa y `wait`
  # se queda colgado hasta el timeout. El consumer llega por DNS interno (router.fission).
  # defaultNamespace: Fission vigila (y crea los pods de las funciones en) nuestro namespace
  # en vez de `default`.
  values = [yamlencode({
    routerServiceType = "NodePort"
    defaultNamespace  = var.fission_namespace_functions
  })]

  depends_on = [kubectl_manifest.namespace, kubectl_manifest.namespace_fn, kubectl_manifest.fission_crd]
}

locals {
  ns_fn = var.fission_namespace_functions

  normalizer_code = file("${local.ingesta}/fission/normalizer/normalizer.py")
  # El nombre del paquete lleva el hash del codigo: al cambiar normalizer.py cambia el
  # packageref de la Function y Fission especializa pods nuevos con el codigo nuevo.
  normalizer_pkg = "normalizer-${substr(sha1(local.normalizer_code), 0, 10)}"
}

resource "kubectl_manifest" "fission_env" {
  yaml_body = yamlencode({
    apiVersion = "fission.io/v1"
    kind       = "Environment"
    metadata   = { name = var.fission_env_name, namespace = local.ns_fn }
    spec = {
      version     = 3
      poolsize    = var.fission_env_poolsize
      keeparchive = false
      runtime     = { image = local.image.normalizer_env }
      builder     = {}
    }
  })

  depends_on = [helm_release.fission, terraform_data.image["normalizer_env"]]
}

# Paquete "literal": el mismo que genera `fission fn create --code normalizer.py`.
resource "kubectl_manifest" "normalizer_pkg" {
  yaml_body = yamlencode({
    apiVersion = "fission.io/v1"
    kind       = "Package"
    metadata   = { name = local.normalizer_pkg, namespace = local.ns_fn }
    spec = {
      environment = { name = var.fission_env_name, namespace = local.ns_fn }
      deployment  = { type = "literal", literal = base64encode(local.normalizer_code), checksum = {} }
      source      = { checksum = {} }
    }
  })

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [kubectl_manifest.fission_env]
}

resource "kubectl_manifest" "normalizer_fn" {
  yaml_body = yamlencode({
    apiVersion = "fission.io/v1"
    kind       = "Function"
    metadata   = { name = "normalizer", namespace = local.ns_fn }
    spec = {
      environment = { name = var.fission_env_name, namespace = local.ns_fn }
      package = {
        functionName = "normalizer.main"
        packageref   = { name = local.normalizer_pkg, namespace = local.ns_fn }
      }
      InvokeStrategy = {
        StrategyType = "execution"
        ExecutionStrategy = {
          ExecutorType          = "poolmgr"
          MinScale              = 0
          MaxScale              = 0
          SpecializationTimeout = 120
          TargetCPUPercent      = 0
        }
      }
      concurrency     = 500
      functionTimeout = 60
      idletimeout     = 120
      requestsPerPod  = 1
      resources       = {}
    }
  })

  depends_on = [kubectl_manifest.normalizer_pkg]
}

resource "kubectl_manifest" "normalizer_trigger" {
  yaml_body          = file("${local.ingesta}/fission/normalizer/fission.yaml")
  override_namespace = local.ns_fn

  depends_on = [kubectl_manifest.normalizer_fn]
}

# Puente NATS -> router de Fission (el MessageQueueTrigger da 401 en 1.27).
resource "kubectl_manifest" "normalizer_consumer" {
  yaml_body = replace(
    file("${local.ingesta}/fission/normalizer/consumer.yaml"),
    "/image: normalizer-consumer:\\S+/",
    "image: ${local.image.consumer}",
  )
  override_namespace = local.ns_fn
  wait_for_rollout   = true

  depends_on = [
    terraform_data.image["consumer"],
    kubectl_manifest.consumer_normalizer,
    kubectl_manifest.normalizer_trigger,
  ]
}
