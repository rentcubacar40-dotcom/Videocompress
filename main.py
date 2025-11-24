import os
import asyncio
import logging
import tempfile
import time
import subprocess
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de logging más detallada
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
    sys.modules['imghdr'] = imghdr

# Importar Telethon
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename
from telethon.tl.custom import Button
from concurrent.futures import ThreadPoolExecutor

class VideoCompressorBot:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.bot_token = os.getenv('BOT_TOKEN')
        self.client = None
        self.max_size = 2000 * 1024 * 1024  # 2GB máximo
        self.pending_videos = {}
        self.progress_messages = {}  # Para almacenar mensajes de progreso
        self.executor = ThreadPoolExecutor(max_workers=2)  # Para operaciones bloqueantes

        # Presets optimizados para mayor velocidad
        self.compression_presets = {
            'ultra_turbo': {'name': '🚀 ULTRA TURBO', 'crf': '35', 'preset': 'ultrafast', 'resolutions': ['426:240','640:360','854:480'], 'audio_bitrate': '64k', 'description': 'Máxima compresión - Para compartir rápido', 'quality': 'Baja', 'speed': 'Máxima'},
            'turbo': {'name': '⚡ TURBO', 'crf': '32', 'preset': 'superfast', 'resolutions': ['640:360','854:480','1280:720'], 'audio_bitrate': '96k', 'description': 'Alta compresión - Buen balance', 'quality': 'Media-Baja', 'speed': 'Muy Rápido'},
            'balanced': {'name': '⚖️ BALANCEADO', 'crf': '28', 'preset': 'fast', 'resolutions': ['854:480','1280:720','1920:1080'], 'audio_bitrate': '128k', 'description': 'Calidad equilibrada - Recomendado', 'quality': 'Buena', 'speed': 'Rápido'},
            'quality': {'name': '🎨 CALIDAD', 'crf': '23', 'preset': 'medium', 'resolutions': ['1280:720','1920:1080'], 'audio_bitrate': '160k', 'description': 'Alta calidad - Poca compresión', 'quality': 'Muy Buena', 'speed': 'Medio'},
            'max_quality': {'name': '👑 MÁXIMA CALIDAD', 'crf': '18', 'preset': 'slow', 'resolutions': ['1920:1080','3840:2160'], 'audio_bitrate': '192k', 'description': 'Máxima calidad - Compresión mínima', 'quality': 'Excelente', 'speed': 'Lento'},
            'audio_only': {'name': '🎵 SOLO AUDIO', 'crf': 'N/A', 'preset': 'fast', 'resolutions': ['no_video'], 'audio_bitrate': '128k', 'description': 'Extrae solo el audio (MP3)', 'quality': 'Solo Audio', 'speed': 'Rápido'}
        }

    async def initialize(self):
        self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        logger.info("✅ Bot iniciado correctamente - Modo optimizado activo")

    def get_file_size(self, size_bytes):
        if size_bytes == 0:
            return "0B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_names[i]}"

    def estimate_size(self, original_size, preset_key):
        ratios = {
            'ultra_turbo': 0.08, 'turbo': 0.15, 'balanced': 0.25, 'quality': 0.40, 'max_quality': 0.60, 'audio_only': 0.03
        }
        return int(original_size * ratios.get(preset_key, 0.25))

    async def handle_start(self, event):
        await event.message.reply(
            "🎬 **¡Hola! Soy tu compresor de videos optimizado**\n\n"
            "✅ **Características mejoradas:**\n"
            "• Progreso en tiempo real\n"
            "• Velocidad máxima de compresión\n"
            "• Optimizado para 4GB RAM\n"
            "• Procesamiento eficiente\n\n"
            "📤 **Envía un video y elige la calidad deseada**"
        )

    async def handle_video(self, event):
        message = event.message
        if not (message.video or (message.document and message.document.mime_type and 'video' in message.document.mime_type)):
            return
        
        file_size = message.file.size
        if file_size > self.max_size:
            await message.reply(f"❌ **Archivo muy grande** ({self.get_file_size(file_size)})\n\nMáximo permitido: {self.get_file_size(self.max_size)}")
            return
        
        # Limpiar videos pendientes antiguos
        current_time = time.time()
        self.pending_videos = {k: v for k, v in self.pending_videos.items() 
                             if current_time - v.get('timestamp', 0) < 3600}  # 1 hora
        
        self.pending_videos[message.sender_id] = {
            'file_size': file_size, 
            'message': message,
            'timestamp': current_time
        }
        
        await self.show_quality_options(message, file_size)

    async def show_quality_options(self, message, file_size):
        buttons = []
        menu_text = "📊 **Elige la calidad deseada**:\n\n"
        menu_text += f"📁 **Tamaño original:** {self.get_file_size(file_size)}\n\n"
        
        for key, preset in self.compression_presets.items():
            for res in preset['resolutions']:
                if res == 'no_video':
                    estimated_size = self.estimate_size(file_size, key)
                    label = f"{preset['name']} (Audio) ~{self.get_file_size(estimated_size)}"
                    callback_data = f"compress_{key}_audio"
                else:
                    w, h = res.split(':')
                    estimated_size = self.estimate_size(file_size, key)
                    label = f"{preset['name']} {h}p ~{self.get_file_size(estimated_size)}"
                    callback_data = f"compress_{key}_{h}p"
                buttons.append([Button.inline(label, callback_data.encode())])
        
        buttons.append([Button.inline("❌ CANCELAR", b"cancel")])
        await message.reply(menu_text, buttons=buttons)

    async def handle_button_callback(self, event):
        data = event.data.decode()
        user_id = event.sender_id
        
        try:
            if data.startswith("compress_"):
                parts = data.split("_")
                preset_key = parts[1]
                resolution = parts[2] if len(parts) > 2 else None
                video_info = self.pending_videos.get(user_id)
                
                if not video_info:
                    await event.answer("❌ No hay video pendiente o la sesión expiró", alert=True)
                    return
                
                video_info['preset_key'] = preset_key
                video_info['resolution'] = resolution
                await event.answer("⚙️ Iniciando compresión...")
                await self.process_video(event, video_info)
                
            elif data == "cancel":
                if user_id in self.pending_videos:
                    del self.pending_videos[user_id]
                await event.edit("❌ Proceso cancelado.")
                
        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await event.answer("❌ Error al procesar la solicitud", alert=True)

    async def process_video(self, event, video_info):
        user_id = event.sender_id
        message = video_info['message']
        preset_key = video_info['preset_key']
        resolution = video_info['resolution']
        preset = self.compression_presets[preset_key]

        # Crear mensaje de progreso inicial
        progress_msg = await event.edit(
            f"⚙️ **Iniciando compresión**\n"
            f"**Preset:** {preset['name']} {resolution or ''}\n"
            f"**Velocidad:** {preset['speed']}\n"
            f"**Calidad:** {preset['quality']}\n\n"
            f"📥 Descargando... 0%"
        )
        
        self.progress_messages[user_id] = progress_msg

        try:
            temp_dir = tempfile.gettempdir()
            input_path = os.path.join(temp_dir, f"input_{user_id}_{int(time.time())}.mp4")
            
            # Descargar con progreso
            await self.download_with_progress(message, input_path, user_id)
            
            output_ext = '.mp3' if preset_key == 'audio_only' else '.mp4'
            output_path = os.path.join(temp_dir, f"compressed_{user_id}_{int(time.time())}{output_ext}")

            # Comprimir con progreso en tiempo real
            await self.compress_with_progress(input_path, output_path, preset, resolution, user_id)
            
            # Subir con progreso
            await self.upload_with_progress(output_path, message.chat_id, preset, resolution, user_id)

            # Limpiar
            await self.cleanup_files([input_path, output_path])
            
            # Mensaje final
            final_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            await self.update_progress_message(
                user_id,
                f"🎉 **¡Proceso completado exitosamente!**\n\n"
                f"✅ **Compresión finalizada**\n"
                f"📊 **Tamaño final:** {self.get_file_size(final_size)}\n"
                f"⚡ **Preset usado:** {preset['name']} {resolution or ''}"
            )
            
        except Exception as e:
            logger.error(f"Error en process_video: {e}")
            await self.update_progress_message(
                user_id,
                f"❌ **Error durante el procesamiento**\n\n"
                f"**Detalles:** {str(e)}\n\n"
                f"Por favor, intenta con otro video o configuración."
            )
        finally:
            # Limpiar mensaje de progreso
            if user_id in self.progress_messages:
                del self.progress_messages[user_id]

    async def download_with_progress(self, message, input_path, user_id):
        """Descargar archivo con progreso en tiempo real"""
        last_update = 0
        async for chunk in self.client.iter_download(message.media, file=input_path):
            if time.time() - last_update > 0.5:  # Actualizar cada 500ms
                file_size = message.file.size
                downloaded = chunk if isinstance(chunk, int) else os.path.getsize(input_path)
                percent = min(100, int(downloaded / file_size * 100)) if file_size > 0 else 0
                
                await self.update_progress_message(
                    user_id,
                    f"📥 **Descargando video...**\n"
                    f"**Progreso:** {percent}%\n"
                    f"**Descargado:** {self.get_file_size(downloaded)} / {self.get_file_size(file_size)}"
                )
                last_update = time.time()

    async def compress_with_progress(self, input_path, output_path, preset, resolution, user_id):
        """Comprimir video con progreso en tiempo real usando ffmpeg"""
        
        # Obtener duración del video
        duration = await self.get_video_duration(input_path)
        
        if duration == 0:
            await self.update_progress_message(user_id, "❌ No se pudo obtener la duración del video")
            return

        # Construir comando ffmpeg optimizado
        ffmpeg_cmd = ['ffmpeg', '-i', input_path, '-y']
        
        if preset['name'] == '🎵 SOLO AUDIO':
            ffmpeg_cmd += ['-vn', '-c:a', 'libmp3lame', '-b:a', preset['audio_bitrate']]
        else:
            ffmpeg_cmd += [
                '-c:v', 'libx264', '-crf', preset['crf'], '-preset', preset['preset'],
                '-c:a', 'aac', '-b:a', preset['audio_bitrate'], '-movflags', '+faststart'
            ]
            if resolution != 'audio':
                ffmpeg_cmd += ['-vf', f'scale=-2:{resolution}']
        
        ffmpeg_cmd += [
            '-progress', 'pipe:1',  # Redirigir progreso a stdout
            '-loglevel', 'error',   # Solo errores para menos ruido
            output_path
        ]

        # Ejecutar ffmpeg y monitorear progreso
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Procesar salida de progreso en tiempo real
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            line = line.decode('utf-8').strip()
            if line.startswith('out_time='):
                try:
                    time_str = line.split('=')[1]
                    current_time = self.parse_time_string(time_str)
                    percent = min(100, int((current_time / duration) * 100)) if duration > 0 else 0
                    
                    await self.update_progress_message(
                        user_id,
                        f"🎬 **Comprimiendo video...**\n"
                        f"**Progreso:** {percent}%\n"
                        f"**Tiempo:** {self.format_time(current_time)} / {self.format_time(duration)}"
                    )
                except Exception as e:
                    logger.debug(f"Error parsing progress: {e}")

        await process.wait()

    async def upload_with_progress(self, file_path, chat_id, preset, resolution, user_id):
        """Subir archivo con progreso en tiempo real"""
        if not os.path.exists(file_path):
            raise FileNotFoundError("Archivo comprimido no encontrado")
        
        file_size = os.path.getsize(file_path)
        caption = f"🎥 **{preset['name']}** {resolution or ''}\n📊 **Tamaño:** {self.get_file_size(file_size)}"

        last_update = 0
        async for upload_progress in self.client.upload_file(file_path):
            if time.time() - last_update > 0.5:  # Actualizar cada 500ms
                if hasattr(upload_progress, 'total') and upload_progress.total:
                    percent = min(100, int(upload_progress.current / upload_progress.total * 100))
                    
                    await self.update_progress_message(
                        user_id,
                        f"📤 **Subiendo archivo...**\n"
                        f"**Progreso:** {percent}%\n"
                        f"**Subido:** {self.get_file_size(upload_progress.current)} / {self.get_file_size(upload_progress.total)}"
                    )
                    last_update = time.time()

        # Enviar archivo final
        await self.client.send_file(chat_id, file_path, caption=caption)

    async def update_progress_message(self, user_id, text):
        """Actualizar mensaje de progreso de forma eficiente"""
        try:
            if user_id in self.progress_messages:
                await self.progress_messages[user_id].edit(text)
        except Exception as e:
            logger.debug(f"Error updating progress: {e}")

    async def get_video_duration(self, input_path):
        """Obtener duración del video usando ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', 
                input_path
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return float(stdout.decode().strip())
        except Exception as e:
            logger.error(f"Error getting video duration: {e}")
            return 0

    def parse_time_string(self, time_str):
        """Convertir string de tiempo a segundos"""
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                h, m, s = parts
                return float(h) * 3600 + float(m) * 60 + float(s)
            elif len(parts) == 2:
                m, s = parts
                return float(m) * 60 + float(s)
            else:
                return float(time_str)
        except:
            return 0

    def format_time(self, seconds):
        """Formatear segundos a string legible"""
        if seconds >= 3600:
            return f"{int(seconds//3600)}:{int((seconds%3600)//60):02d}:{seconds%60:05.2f}"
        else:
            return f"{int(seconds//60)}:{seconds%60:05.2f}"

    async def cleanup_files(self, file_paths):
        """Limpiar archivos temporales"""
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.debug(f"Error cleaning up {path}: {e}")

    async def run(self):
        await self.initialize()
        
        # Registrar handlers
        self.client.add_event_handler(
            self.handle_start, 
            events.NewMessage(pattern='/start')
        )
        self.client.add_event_handler(
            self.handle_button_callback, 
            events.CallbackQuery()
        )
        self.client.add_event_handler(
            self.handle_video, 
            events.NewMessage(
                func=lambda e: e.message.video or (
                    e.message.document and 
                    e.message.document.mime_type and 
                    'video' in e.message.document.mime_type
                )
            )
        )
        
        logger.info("🤖 Bot iniciado - Modo optimizado con progreso en tiempo real")
        await self.client.run_until_disconnected()

async def main():
    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"❌ Faltan variables: {missing}")
        return
    
    bot = VideoCompressorBot()
    await bot.run()

if __name__ == '__main__':
    # Configurar asyncio para mejor rendimiento
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())
