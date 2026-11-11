output "kube_context" {
  value = var.minikube_profile
}

output "images" {
  value = local.image
}

output "normalizer_package" {
  value = local.normalizer_pkg
}

output "functions_namespace" {
  value = local.ns_fn
}

output "prueba_manual" {
  value = <<-TXT
    # pasada completa automatica (scraper -> raw -> normalizer -> clean):
    bash ${abspath("${path.module}/../e2e.sh")}
    # o a mano:
    kubectl --context ${var.minikube_profile} -n scrappers create job --from=cronjob/scrapper-mercadona prueba-manual
    kubectl --context ${var.minikube_profile} -n ${local.ns_fn} logs deploy/normalizer-consumer -f
    kubectl --context ${var.minikube_profile} -n scrappers delete job prueba-manual
  TXT
}
