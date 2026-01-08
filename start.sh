#!/bin/bash

# Bot de Telegram para Comprimir Videos - 2026
# Script optimizado para Render Free Plan

echo "========================================="
echo "🚀 Iniciando Bot de Compresión de Videos"
echo "📅 Versión 2026"
echo "========================================="

# 1. Actualizar repositorios
echo "🔄 Actualizando repositorios..."
apt-get update -qq

# 2. Instalar ffmpeg y dependencias del sistema
echo "📦 Instalando ffmpeg y dependencias..."
apt-get install -y -qq \
    ffmpeg \
    python3 \
    python3-pip \
    python3-venv

# 3. Verificar instalación
echo "✅ Verificando instalaciones..."
echo "• Python: $(python3 --version)"
echo "• FFmpeg: $(ffmpeg -version | head -n 1 | cut -d' ' -f1-3)"

# 4. Crear y activar entorno virtual
echo "🐍 Configurando entorno Python..."
python3 -m venv /opt/venv
source /opt/venv/bin/activate

# 5. Instalar dependencias Python
echo "📚 Instalando Pyrogram y dependencias..."
pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

# 6. Mostrar configuración
echo "🖥️  Configuración final:"
echo "• Puerto: ${PORT:-8080}"
echo "• Usuario: $(whoami)"
echo "• Directorio: $(pwd)"
echo "• Memoria libre: $(free -h | awk '/^Mem:/ {print $4}')"
echo "========================================="

# 7. Ejecutar el bot
echo "🤖 Iniciando bot de Telegram..."
exec python3 main.py
