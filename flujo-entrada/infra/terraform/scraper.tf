# Scraper de Mercadona: secreto, PVC de volcados y CronJob, leidos de los YAML de scrappers/.
# Carrefour no se despliega: esta bloqueado por Cloudflare (ver docs/05-pendientes.md).

locals {
  scraper_dir = "${local.ingesta}/scrappers/scrapper_mercadona"
}

resource "kubectl_manifest" "scraper_secrets" {
  yaml_body = file("${local.ingesta}/scrappers/k8s/secrets.yaml")

  depends_on = [kubectl_manifest.namespace]
}

resource "kubectl_manifest" "scraper_pvc" {
  yaml_body          = file("${local.scraper_dir}/pvc.yaml")
  override_namespace = "scrappers"

  depends_on = [kubectl_manifest.namespace]
}

resource "kubectl_manifest" "scraper_cronjob" {
  yaml_body = replace(
    file("${local.scraper_dir}/cronjob.yaml"),
    "/image: scrapper-mercadona:\\S+/",
    "image: ${local.image.scraper}",
  )
  override_namespace = "scrappers"

  depends_on = [
    terraform_data.image["scraper"],
    kubectl_manifest.scraper_secrets,
    kubectl_manifest.scraper_pvc,
    kubectl_manifest.stream,
  ]
}
