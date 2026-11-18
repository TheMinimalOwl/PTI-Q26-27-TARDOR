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

output "grafana" {
  value = <<-TXT
    # Grafana (usuario admin) en http://localhost:3000 mientras este abierto el port-forward:
    kubectl --context ${var.minikube_profile} -n monitoring get secret grafana -o jsonpath='{.data.admin-password}' | base64 -d; echo
    kubectl --context ${var.minikube_profile} -n monitoring port-forward svc/grafana 3000:80
    # Prometheus en http://localhost:9090:
    kubectl --context ${var.minikube_profile} -n monitoring port-forward svc/prometheus 9090:80
  TXT
}
