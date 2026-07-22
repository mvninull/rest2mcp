FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/* && \
    npm install -g swagger2openapi

RUN mkdir -p /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download do modelo ONNX (~30MB) durante o build
# Evita download no arranque do container em producao
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2')"

COPY . .

EXPOSE 8080

CMD ["python", "-m", "app.cloud"]
