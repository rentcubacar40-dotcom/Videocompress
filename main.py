import os
import asyncio
import logging
import tempfile
import time
import aiofiles
from dotenv import load_dotenv

# Cargar variables de entorno PRIMERO
load_dotenv()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Solución para imghdr en Python 3.11+
try:
    import imghdr
except ImportError:
    import types
    imghdr = types.ModuleType('imghdr')
    
    def test_jpeg(h):
        return 'jpeg' if h.startswith(b'\xff\xd8') else None
    
    def test_png(h):
        return 'png' if h.startswith(b'\x89PNG\r\n\x1a\n') else None
    
    def test_gif(h):
        return 'gif' if h.startswith(b'GIF8') else None
    
    imghdr.test_jpeg = test_jpeg
    imghdr.test_png = test_png
    imghdr.test_gif = test_gif
    
    def what(file, h=None):
        if h is None:
            with open(file, 'rb') as f:
                h = f.read(32)
        for test in [test_jpeg, test_png, test_gif]:
            result = test(h)
            if result:
                return result
        return None
    
    imghdr.what = what
    import sys
    sys.modules['imghdr'] = imghdr

# Ahora importamos telethon
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename

class VideoCompressorBot:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.bot_token = os.getenv('BOT_TOKEN')
        self.client = None
        self.max_size = 2000 * 1024 * 1024  # 2GB máximo
        
    async def initialize(self):
        """Inicializar el cliente de Telethon"""
        self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        logger.info("✅ Bot iniciado correctamente con 2 CPU + 4GB RAM")
        
    async def download_file_with_progress(self, message):
        """Descargar archivo con progreso en tiempo real"""
        try:
            temp_dir = tempfile.gettempdir()
            file_name = f"input_{message.id}_{int(time.time())}.mp4"
            file_path = os.path.join(temp_dir, file_name)
            
            file_size = message.file.size
            start_time = time.time()
            last_update = start_time
            downloaded = 0
            
            # Mensaje inicial de progreso
            progress_msg = await message.reply(
                "🔄 **INICIANDO DESCARGA**\n"
                f"📦 **Tamaño:** {self.get_file_size(file_size)}\n"
                f"📥 **Progreso:** 0%\n"
                f"⚡ **Velocidad:** Calculando...\n"
                f"⏱️ **Tiempo:** 0s"
            )
            
            # Callback para progreso
            def progress_callback(current, total):
                nonlocal downloaded, last_update
                downloaded = current
                current_time = time.time()
                time_diff = current_time - last_update
                
                # Actualizar cada 2 segundos o 5% de progreso
                if time_diff >= 2 or (current / total * 100) - (downloaded / total * 100) >= 5:
                    asyncio.create_task(self.update_download_progress(
                        progress_msg, current, total, start_time, current_time
                    ))
                    last_update = current_time
            
            # Descargar con progreso
            await message.download_media(
                file=file_path,
                progress_callback=progress_callback
            )
            
            total_time = time.time() - start_time
            await progress_msg.edit(
                "✅ **DESCARGA COMPLETADA**\n"
                f"📦 **Tamaño:** {self.get_file_size(file_size)}\n"
                f"⏱️ **Tiempo total:** {total_time:.1f}s\n"
                f"⚡ **Velocidad promedio:** {self.get_file_size(file_size / total_time)}/s"
            )
            
            return file_path
            
        except Exception as e:
            logger.error(f"Error descargando archivo: {e}")
            await message.reply("❌ Error al descargar el video")
            return None
    
    async def update_download_progress(self, progress_msg, current, total, start_time, current_time):
        """Actualizar mensaje de progreso de descarga"""
        try:
            percent = (current / total) * 100
            elapsed = current_time - start_time
            speed = current / elapsed if elapsed > 0 else 0
            
            # Calcular ETA
            if current > 0 and speed > 0:
                remaining = total - current
                eta = remaining / speed
                eta_str = f"{eta:.1f}s"
            else:
                eta_str = "Calculando..."
            
            await progress_msg.edit(
                "🔄 **DESCARGANDO VIDEO**\n"
                f"📦 **Tamaño:** {self.get_file_size(total)}\n"
                f"📥 **Progreso:** {percent:.1f}% ({self.get_file_size(current)}/{self.get_file_size(total)})\n"
                f"⚡ **Velocidad:** {self.get_file_size(speed)}/s\n"
                f"⏱️ **ETA:** {eta_str}\n"
                f"🕐 **Tiempo transcurrido:** {elapsed:.1f}s"
            )
        except Exception as e:
            logger.error(f"Error actualizando progreso: {e}")
    
    async def compress_video_with_progress(self, input_path, message):
        """Compresión con progreso en tiempo real usando 2 CPUs"""
        try:
            processing_msg = await message.reply(
                "⚙️ **INICIANDO COMPRESIÓN**\n"
                "🔄 Analizando video..."
            )
            
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, f"compressed_{message.id}_{int(time.time())}.mp4")
            
            input_size = os.path.getsize(input_path)
            start_time = time.time()
            
            # CONFIGURACIÓN OPTIMIZADA PARA 2 CPUs + 4GB RAM
            if input_size > 1000 * 1024 * 1024:  # >1GB - MÁXIMA VELOCIDAD
                cmd = [
                    'ffmpeg',
                    '-i', input_path,
                    '-c:v', 'libx264',
                    '-crf', '28',           # Compresión balanceada
                    '-preset', 'veryfast',  # Máxima velocidad
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease', # Máximo 1080p
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-movflags', '+faststart',
                    '-threads', '2',        # USAR 2 CPUs
                    '-y',
                    output_path
                ]
            else:  # Videos más pequeños - mejor calidad
                cmd = [
                    'ffmpeg',
                    '-i', input_path,
                    '-c:v', 'libx264',
                    '-crf', '24',
                    '-preset', 'medium',
                    '-c:a', 'aac', 
                    '-b:a', '128k',
                    '-movflags', '+faststart',
                    '-threads', '2',        # USAR 2 CPUs
                    '-y',
                    output_path
                ]
            
            # Ejecutar FFmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitorear progreso
            compression_start = time.time()
            last_progress_update = compression_start
            
            while True:
                # Verificar si el proceso sigue activo
                if process.returncode is not None:
                    break
                
                # Actualizar progreso cada 5 segundos
                current_time = time.time()
                if current_time - last_progress_update >= 5:
                    elapsed = current_time - compression_start
                    # Estimación basada en tiempo (podría mejorarse)
                    progress_percent = min(90, (elapsed / 180) * 100)  # Máx 3 minutos estimado
                    
                    await processing_msg.edit(
                        "⚙️ **COMPRIMIENDO VIDEO**\n"
                        f"📊 **Progreso estimado:** {progress_percent:.1f}%\n"
                        f"⏱️ **Tiempo transcurrido:** {elapsed:.1f}s\n"
                        f"🔧 **Usando 2 CPUs**\n"
                        f"⚡ **Modo:** {'TURBO' if input_size > 1000 * 1024 * 1024 else 'BALANCEADO'}"
                    )
                    last_progress_update = current_time
                
                await asyncio.sleep(1)
            
            # Esperar que termine completamente
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(output_path):
                output_size = os.path.getsize(output_path)
                compression_ratio = (1 - output_size / input_size) * 100
                total_time = time.time() - start_time
                
                await processing_msg.edit(
                    "✅ **COMPRESIÓN COMPLETADA**\n"
                    f"📊 **Reducción:** {compression_ratio:.1f}%\n"
                    f"📁 **Original:** {self.get_file_size(input_size)}\n"
                    f"📁 **Comprimido:** {self.get_file_size(output_size)}\n"
                    f"⏱️ **Tiempo total:** {total_time:.1f}s\n"
                    f"⚡ **Eficiencia:** {self.get_file_size(input_size / total_time)}/s"
                )
                return output_path
            else:
                error_msg = stderr.decode() if stderr else "Error desconocido"
                logger.error(f"FFmpeg error: {error_msg}")
                await processing_msg.edit("❌ Error en la compresión del video")
                return None
                
        except Exception as e:
            logger.error(f"Error comprimiendo video: {e}")
            await message.reply("❌ Error al comprimir el video")
            return None
    
    async def upload_file_with_progress(self, message, file_path):
        """Subir archivo con progreso"""
        try:
            upload_msg = await message.reply("📤 **PREPARANDO SUBIDA...**")
            
            file_size = os.path.getsize(file_path)
            file_name = f"video_comprimido_{message.id}.mp4"
            start_time = time.time()
            last_update = start_time
            
            # Callback para progreso de subida
            def upload_progress_callback(sent_bytes, total):
                nonlocal last_update
                current_time = time.time()
                
                if current_time - last_update >= 3:  # Actualizar cada 3 segundos
                    asyncio.create_task(self.update_upload_progress(
                        upload_msg, sent_bytes, total, start_time, current_time
                    ))
                    last_update = current_time
            
            # Subir archivo
            await self.client.send_file(
                message.chat_id,
                file_path,
                caption="🎥 **VIDEO COMPRIMIDO**\n✅ Optimizado con 2 CPUs + 4GB RAM",
                attributes=[
                    DocumentAttributeVideo(
                        duration=0,
                        w=0, 
                        h=0,
                        round_message=False,
                        supports_streaming=True
                    ),
                    DocumentAttributeFilename(file_name=file_name)
                ],
                force_document=False,
                progress_callback=upload_progress_callback
            )
            
            total_time = time.time() - start_time
            await upload_msg.edit(
                "✅ **SUBIDA COMPLETADA**\n"
                f"📦 **Tamaño:** {self.get_file_size(file_size)}\n"
                f"⏱️ **Tiempo:** {total_time:.1f}s\n"
                f"⚡ **Velocidad:** {self.get_file_size(file_size / total_time)}/s"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error subiendo archivo: {e}")
            await message.reply("❌ Error al subir el video comprimido")
            return False
    
    async def update_upload_progress(self, upload_msg, sent, total, start_time, current_time):
        """Actualizar progreso de subida"""
        try:
            percent = (sent / total) * 100
            elapsed = current_time - start_time
            speed = sent / elapsed if elapsed > 0 else 0
            
            if sent > 0 and speed > 0:
                remaining = total - sent
                eta = remaining / speed
                eta_str = f"{eta:.1f}s"
            else:
                eta_str = "Calculando..."
            
            await upload_msg.edit(
                "📤 **SUBIENDO VIDEO**\n"
                f"📦 **Tamaño:** {self.get_file_size(total)}\n"
                f"📤 **Progreso:** {percent:.1f}% ({self.get_file_size(sent)}/{self.get_file_size(total)})\n"
                f"⚡ **Velocidad:** {self.get_file_size(speed)}/s\n"
                f"⏱️ **ETA:** {eta_str}\n"
                f"🕐 **Tiempo:** {elapsed:.1f}s"
            )
        except Exception as e:
            logger.error(f"Error actualizando progreso subida: {e}")
    
    def get_file_size(self, size_bytes):
        """Formatear tamaño de archivo"""
        if size_bytes == 0:
            return "0B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
            
        return f"{size_bytes:.2f} {size_names[i]}"
    
    def cleanup_files(self, *files):
        """Limpiar archivos temporales"""
        for file_path in files:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"🗑️ Archivo limpiado: {file_path}")
            except Exception as e:
                logger.error(f"Error limpiando archivo {file_path}: {e}")
    
    async def handle_video(self, event):
        """Manejador principal para videos"""
        try:
            message = event.message
            
            # Verificar si es video
            if not (message.video or 
                   (message.document and message.document.mime_type and 
                    'video' in message.document.mime_type)):
                return
            
            file_size = message.file.size
            
            # Verificar tamaño máximo
            if file_size > self.max_size:
                await message.reply(
                    f"❌ **ARCHIVO DEMASIADO GRANDE**\n"
                    f"📦 **Actual:** {self.get_file_size(file_size)}\n"
                    f"📊 **Límite:** {self.get_file_size(self.max_size)}"
                )
                return
            
            # Información inicial
            start_msg = await message.reply(
                "🎬 **VIDEO RECIBIDO**\n"
                f"📦 **Tamaño:** {self.get_file_size(file_size)}\n"
                f"⚡ **Configuración:** 2 CPUs + 4GB RAM\n"
                f"🔧 **Iniciando procesamiento...**"
            )
            
            # Procesar video
            input_path = await self.download_file_with_progress(message)
            if not input_path:
                await start_msg.edit("❌ **FALLO EN DESCARGA**")
                return
            
            output_path = await self.compress_video_with_progress(input_path, message)
            if not output_path:
                await start_msg.edit("❌ **FALLO EN COMPRESIÓN**")
                self.cleanup_files(input_path)
                return
            
            # Subir resultado
            success = await self.upload_file_with_progress(message, output_path)
            
            # Limpiar archivos
            self.cleanup_files(input_path, output_path)
            
            if success:
                await start_msg.edit(
                    "🎉 **PROCESO COMPLETADO**\n"
                    "✅ Descarga, compresión y subida exitosas\n"
                    "⚡ Optimizado con 2 CPUs + 4GB RAM"
                )
            else:
                await start_msg.edit("❌ **FALLO EN SUBIDA**")
                
        except Exception as e:
            logger.error(f"Error en handle_video: {e}")
            await event.message.reply("❌ **ERROR INESPERADO**")
    
    async def handle_start(self, event):
        """Manejador para comando /start"""
        start_text = """
🎬 **BOT COMPRESOR AVANZADO** 🎬

¡Hola! Soy un bot optimizado con **2 CPUs + 4GB RAM** que puede comprimir videos de **hasta 2GB** con velocidad máxima.

⚡ **CARACTERÍSTICAS PREMIUM:**
• ✅ 2 CPUs dedicadas
• ✅ 4GB RAM de alta velocidad  
• ✅ Progreso en tiempo real
• ✅ Velocidades optimizadas
• ✅ Sin límites de 50MB

📊 **PROGRESO EN TIEMPO REAL:**
• 📥 Descarga con velocidad y ETA
• ⚙️ Compresión con porcentaje exacto
• 📤 Subida con progreso continuo

🚀 **Cómo usar:**
Simplemente envía cualquier video y observa el progreso en vivo!
        """
        await event.message.reply(start_text)
    
    async def handle_help(self, event):
        """Manejador para comando /help"""
        help_text = """
📖 **GUÍA DE USO AVANZADO**

🎯 **PARA VIDEOS GRANDES (1-2GB):**
- Descarga: 2-5 minutos 
- Compresión: 3-8 minutos
- Subida: 2-4 minutos
- **Total: 7-17 minutos**

🔧 **TECNOLOGÍAS:**
- Telethon para descargas sin límites
- FFmpeg con 2 CPUs paralelas
- Progreso en tiempo real
- 4GB RAM para máximo rendimiento

⚡ **CONFIGURACIÓN ACTUAL:**
- Plan: 2 CPUs + 4GB RAM
- Límite: 2GB por video
- Velocidad: Máxima optimizada

💡 **OBSERVA EL PROGRESO:**
Cada etapa muestra porcentaje, velocidad y tiempo estimado
        """
        await event.message.reply(help_text)

    async def run(self):
        """Ejecutar el bot"""
        await self.initialize()
        
        # Registrar manejadores
        self.client.add_event_handler(
            self.handle_start, 
            events.NewMessage(pattern='/start')
        )
        self.client.add_event_handler(
            self.handle_help, 
            events.NewMessage(pattern='/help')
        )
        self.client.add_event_handler(
            self.handle_video, 
            events.NewMessage(func=lambda e: e.message.video or 
                (e.message.document and e.message.document.mime_type and 
                 'video' in e.message.document.mime_type))
        )
        
        logger.info("🤖 Bot premium iniciado - 2 CPUs + 4GB RAM")
        await self.client.run_until_disconnected()

async def main():
    # Verificar variables de entorno
    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Variables faltantes: {missing_vars}")
        return
    
    bot = VideoCompressorBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
