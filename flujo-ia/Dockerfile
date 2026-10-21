# Imagen del servicio de RAG (flujo-ia).
#
# Es una imagen "cocida": al construirla se descarga el modelo de embeddings y
# se genera el indice, de modo que el contenedor arranca sin red. Es la via
# rapida para la demo en el clúster (minikube image load).
#
# Si el indice cambia a menudo, la alternativa es no hornearlo y montarlo desde
# un volumen (ver docs/04-despliegue.md).
#
#   docker build -t flujo-ia:v1 .
#   minikube image load flujo-ia:v1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    RAG_CACHE_DIR=/app/.cache \
    RAG_EMBED_MODEL=bge-m3 \
    RAG_LLM=none \
    OLLAMA_HOST=http://host.docker.internal:11434

WORKDIR /app

# torch primero y en version CPU: la de PyPI arrastra CUDA (~2.5 GB).
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY rag/ ./rag/
COPY data/ ./data/
COPY tests/ ./tests/

# Modelo de embeddings + indice. Se hornea para que el contenedor no dependa
# de la red al arrancar.
RUN python -m rag.cli index --embed "${RAG_EMBED_MODEL}"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/health').read()"

CMD ["python", "-m", "rag.serve", "--host", "0.0.0.0", "--port", "8080"]
