import os
import asyncio
import logging
import tempfile
import subprocess
import sys
from dotenv import load_dotenv

# Cargar variables de entorno PRIMERO
load_dotenv()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Solución para imghdr en Python 3.11+ - DEBE IR ANTES de importar telethon
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
    sys.modules['imghdr'] = imghdr

# AHORA importamos telethon DESPUÉS de arreglar imghdr
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
        logger.info("✅ Bot iniciado correctamente")
        
    async def download_file(self, message):
        """Descargar archivo grande sin límite de 50MB"""
        try:
            temp_dir = tempfile.gettempdir()
            file_name = f"input_{message.id}.mp4"
            file_path = os.path.join(temp_dir, file_name)
            
            download_msg = await message.reply("📥 Descargando video...")
            await message.download_media(file=file_path)
            await download_msg.edit("✅ Descarga completada")
            
            return file_path
            
        except Exception as e:
            logger.error(f"Error descargando archivo: {e}")
            await message.reply("❌ Error al descargar el video")
            return None
    
    async def compress_video(self, input_path, message):
        """Comprimir video usando FFmpeg directamente"""
        try:
            processing_msg = await message.reply("⚙️ Comprimiendo video...")
            
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, f"compressed_{message.id}.mp4")
            
            # Obtener tamaño original
            input_size = os.path.getsize(input_path)
            
            # Configuración de compresión basada en tamaño
            if input_size > 500 * 1024 * 1024:  # >500MB
                crf = "30"
                preset = "fast"
            elif input_size > 100 * 1024 * 1024:  # >100MB
                crf = "28" 
                preset = "medium"
            else:
                crf = "26"
                preset = "slow"
            
            # Comando FFmpeg
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-c:v', 'libx264',
                '-crf', crf,
                '-preset', preset,
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                '-y',  # Sobrescribir archivo
                output_path
            ]
            
            # Ejecutar FFmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(output_path):
                output_size = os.path.getsize(output_path)
                compression_ratio = (1 - output_size / input_size) * 100
                
                await processing_msg.edit(
                    f"✅ Compresión completada!\n"
                    f"📊 Reducción: {compression_ratio:.1f}%\n"
                    f"📁 Original: {self.get_file_size(input_size)}\n"
                    f"📁 Comprimido: {self.get_file_size(output_size)}"
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
    
    async def upload_file(self, message, file_path):
        """Subir archivo comprimido"""
        try:
            upload_msg = await message.reply("📤 Subiendo video comprimido...")
            
            file_name = f"video_comprimido_{message.id}.mp4"
            
            # Subir archivo
            await self.client.send_file(
                message.chat_id,
                file_path,
                caption="🎥 **Video Comprimido**\n✅ Optimizado para compartir",
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
                force_document=False
            )
            
            await upload_msg.delete()
            return True
            
        except Exception as e:
            logger.error(f"Error subiendo archivo: {e}")
            await message.reply("❌ Error al subir el video comprimido")
            return False
    
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
                    f"❌ El archivo es muy grande ({self.get_file_size(file_size)}).\n"
                    f"📦 Máximo permitido: {self.get_file_size(self.max_size)}"
                )
                return
            
            # Información inicial
            await message.reply(
                f"🎬 **Video recibido**\n"
                f"📊 Tamaño: {self.get_file_size(file_size)}\n"
                f"⚙️ Iniciando compresión..."
            )
            
            # Procesar video
            input_path = await self.download_file(message)
            if not input_path:
                return
            
            output_path = await self.compress_video(input_path, message)
            if not output_path:
                self.cleanup_files(input_path)
                return
            
            # Subir resultado
            success = await self.upload_file(message, output_path)
            
            # Limpiar archivos
            self.cleanup_files(input_path, output_path)
            
            if success:
                await message.reply("🎉 ¡Proceso completado exitosamente!")
                
        except Exception as e:
            logger.error(f"Error en handle_video: {e}")
            await event.message.reply("❌ Ocurrió un error inesperado")
    
    async def handle_start(self, event):
        """Manejador para comando /start"""
        start_text = """
🎬 **Bot Compresor de Videos** 🎬

¡Hola! Soy un bot que puede comprimir videos de **hasta 2GB** sin límites de tamaño.

📦 **Características:**
• ✅ Videos hasta 2GB
• ✅ Compresión inteligente  
• ✅ Mantiene calidad aceptable
• ✅ Sin límites de 50MB

🚀 **Cómo usar:**
Simplemente envía cualquier video y lo comprimiré automáticamente.

🔧 **Tecnología:**
Usamos Telethon + FFmpeg para máxima compatibilidad
        """
        await event.message.reply(start_text)
    
    async def handle_help(self, event):
        """Manejador para comando /help"""
        help_text = """
📖 **Guía de Uso**

1. **Envía un video** de hasta 2GB
2. **Espera** mientras lo proceso
3. **Recibe** el video comprimido

⚡ **Proceso:**
- 📥 Descarga (sin límites)
- ⚙️ Compresión optimizada  
- 📤 Subida del resultado

💡 **Consejos:**
- Videos más largos toman más tiempo
- La compresión mantiene calidad visible
- Archivos muy grandes pueden tomar varios minutos
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
        
        logger.info("🤖 Bot escuchando mensajes...")
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
