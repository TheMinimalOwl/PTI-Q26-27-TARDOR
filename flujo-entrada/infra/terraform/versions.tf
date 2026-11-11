terraform {
  required_version = ">= 1.6"

  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
    # CRDs de Fission: se descargan del repo oficial en la version del chart.
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
    # kubectl_manifest aplica YAML sin validar el CRD en el plan: hace falta para los
    # objetos de Fission y de NACK, cuyos CRD no existen hasta que se instala el chart.
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.1"
    }
  }
}

provider "helm" {
  kubernetes = {
    config_path    = pathexpand(var.kubeconfig)
    config_context = var.minikube_profile
  }
}

provider "kubectl" {
  config_path      = pathexpand(var.kubeconfig)
  config_context   = var.minikube_profile
  load_config_file = true
}
