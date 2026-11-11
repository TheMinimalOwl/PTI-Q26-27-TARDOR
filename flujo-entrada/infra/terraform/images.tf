# Imagenes de la ingesta. No hay registry: se construyen con `docker build` y se cargan en el
# nodo de minikube con `minikube image load`. La etiqueta es un hash de los ficheros que entran en
# cada imagen, asi que solo se reconstruye lo que cambia y el cambio de etiqueta fuerza el
# rollout del Deployment, del pool de Fission y de los siguientes Jobs del CronJob.

locals {
  ingesta = abspath("${path.module}/../..")

  image_src = {
    scraper = {
      name       = "scrapper-mercadona"
      dir        = "scrappers/scrapper_mercadona"
      dockerfile = "Dockerfile"
      files      = ["Dockerfile", "requirements.txt", "src/**/*.py"]
      build_args = {}
    }
    scraper_consum = {
      name       = "scrapper-consum"
      dir        = "scrappers/scrapper_consum"
      dockerfile = "Dockerfile"
      files      = ["Dockerfile", "requirements.txt", "src/**/*.py"]
      build_args = {}
    }
    scraper_condis = {
      name       = "scrapper-condis"
      dir        = "scrappers/scrapper_condis"
      dockerfile = "Dockerfile"
      files      = ["Dockerfile", "requirements.txt", "src/**/*.py"]
      build_args = {}
    }
    scraper_caprabo = {
      name       = "scrapper-caprabo"
      dir        = "scrappers/scrapper_caprabo"
      dockerfile = "Dockerfile"
      files      = ["Dockerfile", "requirements.txt", "src/**/*.py"]
      build_args = {}
    }
    normalizer_env = {
      name       = "normalizer-env"
      dir        = "fission/normalizer"
      dockerfile = "Dockerfile.env"
      files      = ["Dockerfile.env", "requirements.txt"]
      build_args = { FISSION_PY_ENV = var.fission_python_base }
    }
    consumer = {
      name       = "normalizer-consumer"
      dir        = "fission/normalizer"
      dockerfile = "Dockerfile.consumer"
      files      = ["Dockerfile.consumer", "requirements.txt", "consumer.py", "normalizer.py"]
      build_args = {}
    }
  }

  image_hash = {
    for k, v in local.image_src : k => substr(sha1(join("", concat(
      [for f in sort(distinct(flatten([for p in v.files : tolist(fileset("${local.ingesta}/${v.dir}", p))]))) :
      filesha1("${local.ingesta}/${v.dir}/${f}")],
      [jsonencode(v.build_args)],
    ))), 0, 12)
  }

  image = { for k, v in local.image_src : k => "${v.name}:${local.image_hash[k]}" }
}

resource "terraform_data" "image" {
  for_each = local.image_src

  triggers_replace = [local.image[each.key], var.minikube_profile]

  # docker build en el host + minikube image load (lo mismo que setup-vm.sh/deploy.sh).
  # `minikube image build` no acepta --build-arg y sale con 0 aunque falle, asi que al
  # final se comprueba que la imagen esta de verdad en el nodo.
  provisioner "local-exec" {
    working_dir = "${local.ingesta}/${each.value.dir}"
    interpreter = ["/bin/bash", "-euo", "pipefail", "-c"]
    command     = <<-EOT
      docker build -t '${local.image[each.key]}' -f '${each.value.dockerfile}' ${join(" ", [for k, v in each.value.build_args : "--build-arg '${k}=${v}'"])} .
      minikube -p '${var.minikube_profile}' image load '${local.image[each.key]}'
      minikube -p '${var.minikube_profile}' image ls | grep -q '${local.image[each.key]}$' \
        || { echo 'la imagen ${local.image[each.key]} no ha llegado al nodo' >&2; exit 1; }
    EOT
  }
}
