FROM python:3.11-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código
COPY main.py .

# Crear directorios necesarios
RUN mkdir -p /app/session /app/downloads /app/compressed

# Crear archivo data.json inicial si no existe
RUN echo '{"authorized_users": [], "authorized_groups": [], "admins": [], "super_admins": []}' > /app/data.json || true

# Variables de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=10000

# Exponer puerto (obligatorio para Render)
EXPOSE 10000

# Comando de inicio
CMD ["python", "main.py"]
