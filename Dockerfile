# Usar imagen base ligera de Python
FROM python:3.11-slim-bookworm

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root para seguridad
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements primero (para cache de Docker)
COPY --chown=appuser:appuser requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY --chown=appuser:appuser . .

# Cambiar al usuario no-root
USER appuser

# Verificar que ffmpeg esté instalado
RUN ffmpeg -version

# Exponer el puerto que Render requiere
EXPOSE 8080

# Comando para ejecutar la aplicación
CMD ["python", "main.py"]
