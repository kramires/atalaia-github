# ATALAIA ComSoc — imagem de execução
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo

WORKDIR /app

# Dependências primeiro (aproveita cache de camada do Docker)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código da aplicação
COPY . .

# Diretórios de dados/saída (normalmente montados como volumes)
RUN mkdir -p data data/uploads output/dashboards output/briefings logs \
    && chmod +x docker-entrypoint.sh

EXPOSE 9001

# Inicializa o schema do banco e sobe o servidor (ver docker-entrypoint.sh)
ENTRYPOINT ["./docker-entrypoint.sh"]
