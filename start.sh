#!/bin/bash
set -e

echo "🚀 Iniciando Video Compressor Bot..."

# Verificar variables de entorno
if [ -z "$API_ID" ] || [ -z "$API_HASH" ] || [ -z "$BOT_TOKEN" ]; then
    echo "❌ Error: Faltan variables de entorno"
    echo "Por favor configura API_ID, API_HASH y BOT_TOKEN"
    exit 1
fi

echo "✅ Variables de entorno verificadas"

# Crear carpetas si no existen
mkdir -p downloads compressed

echo "📁 Carpetas preparadas"

# Limpiar archivos temporales viejos (opcional)
find downloads -type f -mmin +60 -delete 2>/dev/null || true
find compressed -type f -mmin +60 -delete 2>/dev/null || true

echo "🧹 Limpieza completada"

# Ejecutar el bot
echo "🤖 Iniciando bot..."
exec python main.py
