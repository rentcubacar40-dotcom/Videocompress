import os
import asyncio
import logging
import tempfile
import time
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

# SOLUCIÓN PARA IMGHDR - DEBE IR ANTES DE TELEthon
try:
    import imghdr
except ImportError:
    # Crear imghdr manualmente para Python 3.11+
    import types
    imghdr = types.ModuleType('imghdr')
    
    def test_jpeg(h):
        if h.startswith(b'\xff\xd8'):
            return 'jpeg'
        return None
    
    def test_png(h):
        if h.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'png'
        return None
    
    def test_gif(h):
        if h.startswith(b'GIF8'):
            return 'gif'
        return None
    
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
    # Registrar en sys.modules
    sys.modules['imghdr'] = imghdr

# AHORA importar telethon
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename
from telethon.tl.custom import Button

class VideoCompressorBot:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.bot_token = os.getenv('BOT_TOKEN')
        self.client = None
        self.max_size = 2000 * 1024 * 1024  # 2GB máximo
        self.pending_videos = {}
        
        # Presets de compresión
        self.compression_presets = {
            'ultra_turbo': {
                'name': '🚀 ULTRA TURBO',
                'crf': '35',
                'preset': 'veryfast',
                'scale': '854:480',
                'audio_bitrate': '64k',
                'quality': 'Baja'
            },
            'turbo': {
                'name': '⚡ TURBO', 
                'crf': '32',
                'preset': 'veryfast',
                'scale': '1280:720',
                'audio_bitrate': '96k',
                'quality': 'Media-Baja'
            },
            'balanced': {
                'name': '⚖️ BALANCEADO',
                'crf': '28', 
                'preset': 'medium',
                'scale': '1920:1080',
                'audio_bitrate': '128k',
                'quality': 'Buena'
            },
            'quality': {
                'name': '🎨 CALIDAD',
                'crf': '23',
                'preset': 'slow', 
                'scale': '1920:1080',
                'audio_bitrate': '160k',
                'quality': 'Muy Buena'
            }
        }
        
    async def initialize(self):
        """Inicializar el cliente de Telethon"""
        self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        logger.info("✅ Bot iniciado correctamente")
        
    async def download_file_simple(self, message):
        """Descarga simple y confiable"""
        try:
            status_msg = await message.reply("📥 Descargando video...")
            
            # Crear archivo temporal
            temp_dir = tempfile.gettempdir()
            file_name = f"video_{message.id}_{int(time.time())}.mp4"
            file_path = os.path.join(temp_dir, file_name)
            
            # Descargar directamente
            await message.download_media(file=file_path)
            
            # Verificar que se descargó
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                file_size = os.path.getsize(file_path)
                await status_msg.edit(f"✅ Descarga completada: {self.get_file_size(file_size)}")
                return file_path
            else:
                await status_msg.edit("❌ Error: Archivo vacío o no descargado")
                return None
                
        except Exception as e:
            logger.error(f"Error en descarga: {e}")
            await message.reply("❌ Error al descargar el video")
            return None
    
    async def show_compression_options(self, message, file_size):
        """Mostrar opciones de compresión"""
        try:
            buttons = []
            
            for preset_key, preset in self.compression_presets.items():
                estimated_size = self.calculate_estimated_size(file_size, preset_key)
                button_text = f"{preset['name']} (~{self.get_file_size(estimated_size)})"
                button = Button.inline(button_text, f"compress_{preset_key}".encode())
                buttons.append([button])
            
            menu_text = f"""
🎬 **VIDEO RECIBIDO: {self.get_file_size(file_size)}**

Elige cómo comprimir:

"""
            for preset_key, preset in self.compression_presets.items():
                estimated_size = self.calculate_estimated_size(file_size, preset_key)
                reduction = (1 - (estimated_size / file_size)) * 100
                menu_text += f"**{preset['name']}** - ~{self.get_file_size(estimated_size)} ({reduction:.1f}% reducción)\n"
            
            # Guardar video pendiente
            self.pending_videos[message.sender_id] = {
                'file_size': file_size,
                'message': message
            }
            
            await message.reply(menu_text, buttons=buttons)
            
        except Exception as e:
            logger.error(f"Error mostrando opciones: {e}")
            await message.reply("❌ Error al mostrar opciones")
    
    def calculate_estimated_size(self, original_size, preset_key):
        """Calcular tamaño estimado"""
        reduction_ratios = {
            'ultra_turbo': 0.10,  # 90% reducción
            'turbo': 0.20,        # 80% reducción  
            'balanced': 0.35,     # 65% reducción
            'quality': 0.55,      # 45% reducción
        }
        ratio = reduction_ratios.get(preset_key, 0.35)
        return original_size * ratio
    
    async def handle_button_callback(self, event):
        """Manejar botones"""
        try:
            data = event.data.decode()
            user_id = event.sender_id
            
            if data.startswith("compress_"):
                preset_key = data.replace("compress_", "")
                
                if user_id not in self.pending_videos:
                    await event.answer("❌ No hay video pendiente", alert=True)
                    return
                
                video_info = self.pending_videos[user_id]
                await self.process_video(event, preset_key, video_info)
                
        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await event.answer("❌ Error", alert=True)
    
    async def process_video(self, event, preset_key, video_info):
        """Procesar video completo"""
        try:
            message = video_info['message']
            file_size = video_info['file_size']
            preset = self.compression_presets[preset_key]
            
            await event.edit(f"🔄 Procesando con {preset['name']}...")
            
            # PASO 1: Descargar
            input_path = await self.download_file_simple(message)
            if not input_path:
                return
            
            # PASO 2: Comprimir
            await event.edit("⚙️ Comprimiendo video...")
            output_path = await self.compress_video(input_path, message, preset_key)
            
            if not output_path:
                self.cleanup_files(input_path)
                await event.edit("❌ Error en compresión")
                return
            
            # PASO 3: Subir
            await event.edit("📤 Subiendo resultado...")
            success = await self.upload_file(message, output_path, preset_key)
            
            # Limpiar
            self.cleanup_files(input_path, output_path)
            if user_id in self.pending_videos:
                del self.pending_videos[user_id]
            
            if success:
                await event.edit("🎉 ¡Completado!")
            else:
                await event.edit("❌ Error al subir")
                
        except Exception as e:
            logger.error(f"Error procesando: {e}")
            await event.edit("❌ Error inesperado")
    
    async def compress_video(self, input_path, message, preset_key):
        """Comprimir video"""
        try:
            preset = self.compression_presets[preset_key]
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, f"compressed_{message.id}.mp4")
            
            # Comando FFmpeg simple
            cmd = [
                'ffmpeg', '-i', input_path,
                '-c:v', 'libx264', '-crf', preset['crf'],
                '-preset', preset['preset'], '-c:a', 'aac',
                '-b:a', preset['audio_bitrate'], '-y', output_path
            ]
            
            # Ejecutar
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(output_path):
                return output_path
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error comprimiendo: {e}")
            return None
    
    async def upload_file(self, message, file_path, preset_key):
        """Subir archivo"""
        try:
            preset = self.compression_presets[preset_key]
            file_name = f"compressed_{preset_key}.mp4"
            
            await self.client.send_file(
                message.chat_id, file_path,
                caption=f"🎥 Comprimido con {preset['name']}",
                attributes=[
                    DocumentAttributeVideo(duration=0, w=0, h=0, supports_streaming=True),
                    DocumentAttributeFilename(file_name=file_name)
                ],
                force_document=False
            )
            return True
            
        except Exception as e:
            logger.error(f"Error subiendo: {e}")
            return False
    
    def get_file_size(self, size_bytes):
        """Formatear tamaño"""
        if size_bytes == 0: return "0B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_names[i]}"
    
    def cleanup_files(self, *files):
        """Limpiar archivos"""
        for file_path in files:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"Error limpiando {file_path}: {e}")
    
    async def handle_video(self, event):
        """Manejar video"""
        try:
            message = event.message
            
            if not (message.video or 
                   (message.document and message.document.mime_type and 
                    'video' in message.document.mime_type)):
                return
            
            file_size = message.file.size
            
            if file_size > self.max_size:
                await message.reply(f"❌ Muy grande: {self.get_file_size(file_size)}")
                return
            
            await self.show_compression_options(message, file_size)
                
        except Exception as e:
            logger.error(f"Error en handle_video: {e}")
            await event.message.reply("❌ Error")
    
    async def handle_start(self, event):
        """Comando /start"""
        start_text = """
🎬 **BOT COMPRESOR**

Envía un video y elige cómo comprimirlo.

📦 Límite: 2GB
⚡ Opciones: Turbo, Balanceado, Calidad

¡Envía un video para comenzar!
        """
        await event.message.reply(start_text)

    async def run(self):
        """Ejecutar bot"""
        await self.initialize()
        
        self.client.add_event_handler(self.handle_start, events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.handle_button_callback, events.CallbackQuery())
        self.client.add_event_handler(self.handle_video, events.NewMessage(
            func=lambda e: e.message.video or 
            (e.message.document and e.message.document.mime_type and 
             'video' in e.message.document.mime_type))
        )
        
        logger.info("🤖 Bot ejecutándose")
        await self.client.run_until_disconnected()

async def main():
    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Variables faltantes: {missing_vars}")
        return
    
    bot = VideoCompressorBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
