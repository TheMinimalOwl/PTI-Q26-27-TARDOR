variable "minikube_profile" {
  description = "Perfil de minikube (y contexto de kubectl) donde se despliega la ingesta."
  type        = string
  default     = "ingesta"
}

variable "kubeconfig" {
  description = "Ruta del kubeconfig."
  type        = string
  default     = "~/.kube/config"
}

# --- Scrapers ---

variable "postal_codes" {
  description = "Codigos postales que recorren los scrapers. Mas adelante los dara la API (los de los usuarios de la app); de momento, uno de ejemplo."
  type        = list(string)
  default     = ["08016"]

  validation {
    condition     = length(var.postal_codes) > 0 && alltrue([for c in var.postal_codes : can(regex("^[0-9]{5}$", c))])
    error_message = "postal_codes tiene que tener al menos un codigo postal de 5 cifras."
  }
}

# --- Charts (versiones fijadas: las mismas que se montaron a mano en la VM) ---

variable "nats_chart_version" {
  type    = string
  default = "2.15.1"
}

variable "nack_chart_version" {
  description = "NACK: controlador que crea el stream y el consumidor de JetStream a partir de CRDs."
  type        = string
  default     = "0.35.0"
}

variable "fission_chart_version" {
  description = "Tiene que coincidir con la version del CLI `fission` si se sigue usando a mano."
  type        = string
  default     = "1.27.0"
}

# --- JetStream ---

variable "stream_name" {
  type    = string
  default = "SCRAPERS"
}

variable "stream_subjects" {
  type    = list(string)
  default = ["scraper.>"]
}

variable "stream_max_age" {
  type    = string
  default = "168h" # 7d
}

variable "normalizer_durable" {
  description = "Consumidor push al que se suscribe consumer.py."
  type        = string
  default     = "normalizer"
}

variable "normalizer_filter_subject" {
  description = "Crudos que lee el normalizador: todas las cadenas (scraper.<cadena>.raw)."
  type        = string
  default     = "scraper.*.raw"
}

variable "normalizer_deliver_subject" {
  type    = string
  default = "deliver.normalizer"
}

variable "normalizer_max_ack_pending" {
  type    = number
  default = 1000
}

variable "normalizer_max_deliver" {
  description = "Entregas maximas de un mismo crudo al normalizador antes de descartarlo."
  type        = number
  default     = 100
}

# --- Fission ---

variable "fission_namespace_functions" {
  description = "Namespace propio de la ingesta para la Function, el Environment, sus pods y el consumer. Fission solo vigila este namespace (no `default`)."
  type        = string
  default     = "ingesta"
}

variable "fission_env_name" {
  type    = string
  default = "python"
}

variable "fission_env_poolsize" {
  type    = number
  default = 3
}

variable "fission_python_base" {
  description = "Imagen base del entorno de Fission (Dockerfile.env le anade pydantic)."
  type        = string
  default     = "ghcr.io/fission/python-env@sha256:446f2cd7c2a8c835deb925586d8f761aed288e0eba4437230996573612bab266"
}
