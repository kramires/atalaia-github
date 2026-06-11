#!/bin/bash
# ATALAIA ComSoc — Starter macOS
# Duplo clique = sistema inicia + navegador abre
# Fechar o terminal = servidor para automaticamente

cd "$(dirname "$0")"

# Inicia servidor em background
python3 start.py &
SERVER_PID=$!

# Quando o terminal fechar (EXIT), mata o servidor
trap "kill $SERVER_PID 2>/dev/null; echo 'Servidor parado.'" EXIT

# Aguarda servidor ficar pronto
echo "⏳ Aguardando servidor iniciar..."
sleep 4

# Abre navegador
open "http://127.0.0.1:9001" 2>/dev/null

echo ""
echo "✓ Sistema rodando em http://127.0.0.1:9001"
echo "✓ Feche esta janela para parar o servidor."
echo ""

# Mantém o terminal aberto (aguarda o servidor)
wait $SERVER_PID
