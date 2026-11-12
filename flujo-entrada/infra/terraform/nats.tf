# NATS con JetStream + NACK, y el stream y el consumidor declarados como CRDs.
# Sustituye a los `kubectl exec deploy/nats-box -- nats request $JS.API...` de setup-vm.sh.

resource "helm_release" "nats" {
  name       = "nats"
  namespace  = "messaging"
  repository = "https://nats-io.github.io/k8s/helm/charts/"
  chart      = "nats"
  version    = var.nats_chart_version
  values     = [file("${local.ingesta}/messaging/nats-values.yaml")]
  wait       = true
  atomic     = true # si falla, desinstala: el siguiente up.sh empieza limpio
  timeout    = 300

  depends_on = [kubectl_manifest.namespace]
}

resource "helm_release" "nack" {
  name       = "nack"
  namespace  = "messaging"
  repository = "https://nats-io.github.io/k8s/helm/charts/"
  chart      = "nack"
  version    = var.nack_chart_version
  wait       = true
  atomic     = true # si falla, desinstala: el siguiente up.sh empieza limpio
  timeout    = 300

  values = [yamlencode({
    jetstream = {
      nats = { url = "nats://nats.messaging.svc.cluster.local:4222" }
    }
  })]

  depends_on = [helm_release.nats]
}

# Mismo estado que dejaba setup-vm.sh: limits, Discard Old, file, 7d y ventana de dedupe 2m.
resource "kubectl_manifest" "stream" {
  yaml_body = yamlencode({
    apiVersion = "jetstream.nats.io/v1beta2"
    kind       = "Stream"
    metadata   = { name = lower(var.stream_name), namespace = "messaging" }
    spec = {
      name            = var.stream_name
      subjects        = var.stream_subjects
      retention       = "limits"
      discard         = "old"
      storage         = "file"
      maxAge          = var.stream_max_age
      duplicateWindow = "2m"
    }
  })

  depends_on = [helm_release.nack]
}

# Cola a la que se suscribe consumer.py (push). Sin ella el consumer no recibe nada.
resource "kubectl_manifest" "consumer_normalizer" {
  yaml_body = yamlencode({
    apiVersion = "jetstream.nats.io/v1beta2"
    kind       = "Consumer"
    metadata   = { name = var.normalizer_durable, namespace = "messaging" }
    spec = {
      streamName     = var.stream_name
      durableName    = var.normalizer_durable
      deliverSubject = var.normalizer_deliver_subject
      filterSubject  = var.normalizer_filter_subject
      ackPolicy      = "explicit"
      ackWait        = "30s"
      maxAckPending  = var.normalizer_max_ack_pending
      # Un lote que falla siempre no se reintenta 7 dias: tras maxDeliver entregas (~50 min con
      # AckWait de 30 s) se descarta y NATS publica un aviso ($JS.EVENT.ADVISORY...MAX_DELIVERIES).
      maxDeliver     = var.normalizer_max_deliver
      deliverPolicy  = "all"
      replayPolicy   = "instant"
    }
  })

  depends_on = [kubectl_manifest.stream]
}
