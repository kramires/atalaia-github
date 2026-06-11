#!/bin/bash
# ATALAIA ComSoc — parar o Docker (duplo-clique no macOS)
# Usa 'stop' (não 'down'): o container apenas PARA e continua na lista do
# Docker Desktop, pronto pra subir de novo rápido. Os dados sempre ficam salvos
# nos volumes (./data, ./output, ./logs), com stop OU com down.
cd "$(dirname "$0")"

echo "🛑 Parando o ATALAIA ComSoc (o container continua na lista, só parado)..."
docker compose stop

echo ""
echo "✓ Parado. Para subir de novo: duplo-clique em iniciar-docker.command"
echo "  (Os dados continuam salvos em ./data, ./output e ./logs.)"
echo ""
read -p "Pressione Enter para fechar..."
