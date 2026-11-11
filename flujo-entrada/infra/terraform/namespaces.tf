# Namespaces scrappers, fission y messaging: se leen del mismo YAML que usa setup-vm.sh.

data "kubectl_file_documents" "namespaces" {
  content = file("${local.ingesta}/cluster/namespace.yaml")
}

resource "kubectl_manifest" "namespace" {
  for_each  = data.kubectl_file_documents.namespaces.manifests
  yaml_body = each.value
}

# Namespace de las funciones de Fission y del consumer. Antes era `default`; con uno propio
# la ingesta no se mezcla con lo que despliegue otro equipo en el mismo cluster.
resource "kubectl_manifest" "namespace_fn" {
  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name   = var.fission_namespace_functions
      labels = { "app.kubernetes.io/part-of" = "ingesta" }
    }
  })
}
