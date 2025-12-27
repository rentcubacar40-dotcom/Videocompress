FROM python:3.11-slim

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Crear directorios necesarios
RUN mkdir -p /app/session /app/downloads /app/compressed

# Copiar el código
COPY main.py .

# Variables de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Usar el puerto estándar de Render
ENV PORT=8080

# Exponer el puerto que Render espera
EXPOSE 8080

# Comando para ejecutar el bot (solo el bot, NO FastAPI)
CMD ["python", "main.py"]
