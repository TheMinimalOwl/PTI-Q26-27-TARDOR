# Scrapers: secreto, PVC de volcados (compartido) y un CronJob por cadena, leidos de los YAML
# de scrappers/. Activos: Mercadona y Consum, los dos a las 02:00 (hora de Madrid).
# Carrefour no se despliega: esta bloqueado por Cloudflare (ver docs/05-pendientes.md).

locals {
  scraper_dir = "${local.ingesta}/scrappers/scrapper_mercadona"

  # Sustituye el valor de SCRAPER_POSTAL_CODES de los YAML por var.postal_codes.
  postal_codes_re  = "/(name: SCRAPER_POSTAL_CODES\\s+value: )\"[^\"]*\"/"
  postal_codes_val = "$${1}\"${join(",", var.postal_codes)}\""
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
  yaml_body = replace(replace(
    file("${local.scraper_dir}/cronjob.yaml"),
    "/image: scrapper-mercadona:\\S+/",
    "image: ${local.image.scraper}",
  ), local.postal_codes_re, local.postal_codes_val)
  override_namespace = "scrappers"

  depends_on = [
    terraform_data.image["scraper"],
    kubectl_manifest.scraper_secrets,
    kubectl_manifest.scraper_pvc,
    kubectl_manifest.stream,
  ]
}

resource "kubectl_manifest" "scraper_consum_cronjob" {
  yaml_body = replace(replace(
    file("${local.ingesta}/scrappers/scrapper_consum/cronjob.yaml"),
    "/image: scrapper-consum:\\S+/",
    "image: ${local.image.scraper_consum}",
  ), local.postal_codes_re, local.postal_codes_val)
  override_namespace = "scrappers"

  depends_on = [
    terraform_data.image["scraper_consum"],
    kubectl_manifest.scraper_pvc,
    kubectl_manifest.stream,
  ]
}
