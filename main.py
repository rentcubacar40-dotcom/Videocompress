import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename
import ffmpeg
import aiofiles
from dotenv import load_dotenv
import tempfile
import psutil

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        logger.info("Bot iniciado correctamente")
        
    async def download_file(self, message):
        """Descargar archivo grande sin límite de 50MB"""
        try:
            # Crear directorio temporal
            temp_dir = tempfile.gettempdir()
            file_name = f"input_{message.id}.mp4"
            file_path = os.path.join(temp_dir, file_name)
            
            # Descargar con progreso
            download_msg = await message.reply("📥 Descargando video...")
            
            # Descargar archivo
            await message.download_media(file=file_path)
            
            await download_msg.edit("✅ Descarga completada")
            return file_path
            
        except Exception as e:
            logger.error(f"Error descargando archivo: {e}")
            await message.reply("❌ Error al descargar el video")
            return None
    
    async def compress_video(self, input_path, message):
        """Comprimir video manteniendo calidad"""
        try:
            processing_msg = await message.reply("⚙️ Comprimiendo video...")
            
            # Crear path de salida
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, f"compressed_{os.path.basename(input_path)}")
            
            # Configuración de compresión inteligente
            input_size = os.path.getsize(input_path)
            
            # Ajustar calidad basado en tamaño original
            if input_size > 500 * 1024 * 1024:  # >500MB
                crf = 30  # Más compresión
                preset = 'fast'
            elif input_size > 100 * 1024 * 1024:  # >100MB
                crf = 28
                preset = 'medium'
            else:
                crf = 26  # Menos compresión para videos pequeños
                preset = 'slow'
            
            # Ejecutar FFmpeg
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(
                stream,
                output_path,
                crf=crf,
                preset=preset,
                vcodec='libx264',
                acodec='aac',
                audio_bitrate='128k',
                movflags='+faststart',
                **{'b:v': '0'}  # Bitrate variable
            )
            
            # Ejecutar en subprocess
            process = await asyncio.create_subprocess_exec(
                *ffmpeg.compile(stream, overwrite_output=True),
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
                await processing_msg.edit("❌ Error en la compresión")
                return None
                
        except Exception as e:
            logger.error(f"Error comprimiendo video: {e}")
            await message.reply("❌ Error al comprimir el video")
            return None
    
    async def upload_file(self, message, file_path, original_message):
        """Subir archivo comprimido"""
        try:
            upload_msg = await message.reply("📤 Subiendo video comprimido...")
            
            file_size = os.path.getsize(file_path)
            file_name = f"compressed_{original_message.id}.mp4"
            
            # Subir archivo
            await self.client.send_file(
                message.chat_id,
                file_path,
                caption="🎥 **Video Comprimido**\n"
                       f"✅ Listo para compartir",
                attributes=[
                    DocumentAttributeVideo(
                        duration=0,  # Se detecta automáticamente
                        w=0,
                        h=0,
                        round_message=False,
                        supports_streaming=True
                    ),
                    DocumentAttributeFilename(file_name=file_name)
                ],
                force_document=False,
                allow_cache=False
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
            
            # Procesar video
            input_path = await self.download_file(message)
            if not input_path:
                return
            
            output_path = await self.compress_video(input_path, message)
            if not output_path:
                self.cleanup_files(input_path)
                return
            
            # Subir resultado
            success = await self.upload_file(message, output_path, message)
            
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
• ✅ Mantiene calidad
• ✅ Sin límites de 50MB

🚀 **Cómo usar:**
Simplemente envía cualquier video y lo comprimiré automáticamente.

⚡ **Tecnología:**
Usamos Telethon para superar los límites normales de Telegram
        """
        await event.message.reply(start_text)
    
    async def run(self):
        """Ejecutar el bot"""
        await self.initialize()
        
        # Registrar manejadores
        self.client.add_event_handler(self.handle_start, events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.handle_video, events.NewMessage(func=lambda e: e.message.video or 
            (e.message.document and e.message.document.mime_type and 'video' in e.message.document.mime_type)))
        
        logger.info("Bot escuchando mensajes...")
        await self.client.run_until_disconnected()

async def main():
    bot = VideoCompressorBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
