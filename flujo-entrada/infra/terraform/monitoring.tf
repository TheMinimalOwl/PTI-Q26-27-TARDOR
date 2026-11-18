# Monitorizacion: Prometheus (metricas) + Grafana (panel y alertas) en el namespace
# `monitoring`. La configuracion esta en monitoring/: values de los charts, el panel
# (dashboards/*.json) y las alertas (alerts.yaml, en formato corto que aqui se expande al de
# Grafana). Ver monitoring/README.md.

locals {
  mon_dir  = "${local.ingesta}/monitoring"
  telegram = var.alert_telegram_bot_token != "" && var.alert_telegram_chat_id != ""

  # Cada alerta de alerts.yaml -> regla de Grafana: A = consulta instantanea a Prometheus,
  # C = umbral "A > 0" (las consultas solo devuelven valores positivos cuando algo va mal).
  alert_rules = [for r in yamldecode(file("${local.mon_dir}/alerts.yaml")) : {
    uid          = r.uid
    title        = r.title
    condition    = "C"
    for          = try(r.for, "0m")
    noDataState  = "OK"
    execErrState = "Error"
    labels       = { severity = try(r.severity, "warning") }
    # El chart pasa estos ficheros por `tpl` de Helm: hay que escapar las plantillas de Grafana.
    annotations = { summary = replace(replace(replace(replace(r.summary,
    "{{", "\u0001"), "}}", "\u0002"), "\u0001", "{{`{{`}}"), "\u0002", "{{`}}`}}") }
    data = [
      {
        refId             = "A"
        datasourceUid     = "prometheus"
        relativeTimeRange = { from = 600, to = 0 }
        model = {
          refId      = "A"
          expr       = r.expr
          instant    = true
          datasource = { type = "prometheus", uid = "prometheus" }
        }
      },
      {
        refId         = "C"
        datasourceUid = "__expr__"
        model = {
          refId      = "C"
          type       = "threshold"
          expression = "A"
          conditions = [{ evaluator = { type = "gt", params = [0] } }]
          datasource = { type = "__expr__", uid = "__expr__" }
        }
      },
    ]
  }]

  grafana_rules = {
    "rules.yaml" = {
      apiVersion = 1
      groups = [{
        orgId    = 1
        name     = "ingesta"
        folder   = "Ingesta"
        interval = "1m"
        rules    = local.alert_rules
      }]
    }
  }

  # Solo si hay bot de Telegram: punto de contacto y politica por defecto hacia el. Va en un
  # values aparte (Helm los fusiona) porque sin bot no hay que anadir nada.
  grafana_telegram = {
    "contactpoints.yaml" = {
      apiVersion = 1
      contactPoints = [{
        orgId = 1
        name  = "telegram"
        receivers = [{
          uid  = "telegram"
          type = "telegram"
          settings = {
            bottoken = "$TELEGRAM_BOT_TOKEN" # del secreto grafana-telegram, no del values
            chatid   = var.alert_telegram_chat_id
          }
        }]
      }]
    }
    "policies.yaml" = {
      apiVersion = 1
      policies   = [{ orgId = 1, receiver = "telegram", group_by = ["alertname"] }]
    }
  }

  grafana_dashboards = {
    for f in fileset("${local.mon_dir}/dashboards", "*.json") :
    trimsuffix(f, ".json") => { json = file("${local.mon_dir}/dashboards/${f}") }
  }
}

resource "kubectl_manifest" "namespace_monitoring" {
  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata   = { name = "monitoring", labels = { "app.kubernetes.io/part-of" = "ingesta" } }
  })
}

resource "helm_release" "prometheus" {
  name       = "prometheus"
  namespace  = "monitoring"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "prometheus"
  version    = var.prometheus_chart_version
  values     = [file("${local.mon_dir}/prometheus-values.yaml")]
  wait       = true
  atomic     = true
  timeout    = 600

  depends_on = [kubectl_manifest.namespace_monitoring]
}

resource "kubectl_manifest" "grafana_telegram" {
  count = local.telegram ? 1 : 0
  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "Secret"
    metadata   = { name = "grafana-telegram", namespace = "monitoring" }
    type       = "Opaque"
    stringData = { TELEGRAM_BOT_TOKEN = var.alert_telegram_bot_token }
  })
  sensitive_fields = ["stringData"]

  depends_on = [kubectl_manifest.namespace_monitoring]
}

resource "helm_release" "grafana" {
  name       = "grafana"
  namespace  = "monitoring"
  repository = "https://grafana-community.github.io/helm-charts"
  chart      = "grafana"
  version    = var.grafana_chart_version
  wait       = true
  atomic     = true
  timeout    = 600

  values = concat(
    [
      file("${local.mon_dir}/grafana-values.yaml"),
      yamlencode({
        alerting   = local.grafana_rules
        dashboards = { ingesta = local.grafana_dashboards }
      }),
    ],
    local.telegram ? [yamlencode({
      alerting      = local.grafana_telegram
      envFromSecret = "grafana-telegram"
    })] : [],
  )

  depends_on = [helm_release.prometheus, kubectl_manifest.grafana_telegram]
}
