#!/bin/bash
# ATALAIA ComSoc — subir no Docker (duplo-clique no macOS)
cd "$(dirname "$0")"

echo "🐳 Subindo o ATALAIA ComSoc no Docker..."
echo "   (na primeira vez ele builda a imagem — pode levar alguns minutos)"
echo ""

if ! docker info >/dev/null 2>&1; then
  echo "✗ O Docker não está rodando. Abra o Docker Desktop e tente de novo."
  read -p "Pressione Enter para fechar..."
  exit 1
fi

# 'up -d' builda automaticamente na primeira vez e reaproveita depois.
if ! docker compose up -d; then
  echo "✗ Falha ao subir. Veja a mensagem acima."
  read -p "Pressione Enter para fechar..."
  exit 1
fi

echo ""
echo "⏳ Aguardando o servidor ficar pronto..."
sleep 6
open "http://localhost:9001" 2>/dev/null

echo ""
echo "✓ ATALAIA rodando em http://localhost:9001"
echo "  • Ver logs:    docker compose logs -f"
echo "  • Derrubar:    duplo-clique em parar-docker.command"
echo ""
echo "Pode fechar esta janela."
