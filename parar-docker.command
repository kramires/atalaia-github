#!/bin/bash
# ATALAIA ComSoc — derrubar o Docker (duplo-clique no macOS)
cd "$(dirname "$0")"

echo "🛑 Derrubando o ATALAIA ComSoc..."
docker compose down

echo ""
echo "✓ Parado. Os dados continuam salvos (volumes em ./data, ./output, ./logs)."
echo "  Para subir de novo: duplo-clique em iniciar-docker.command"
echo ""
read -p "Pressione Enter para fechar..."
