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

# Configuración de logging
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

class VideoCompressorBot:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.bot_token = os.getenv('BOT_TOKEN')
        self.client = None
        self.max_size = 2000 * 1024 * 1024  # 2GB máximo
        self.pending_videos = {}

        # Presets con todas las resoluciones posibles
        self.compression_presets = {
            'ultra_turbo': {'name': '🚀 ULTRA TURBO', 'crf': '35', 'preset': 'veryfast', 'resolutions': ['426:240','640:360','854:480'], 'audio_bitrate': '64k', 'description': 'Máxima compresión - Para compartir rápido', 'quality': 'Baja', 'speed': 'Muy Rápido'},
            'turbo': {'name': '⚡ TURBO', 'crf': '32', 'preset': 'veryfast', 'resolutions': ['640:360','854:480','1280:720'], 'audio_bitrate': '96k', 'description': 'Alta compresión - Buen balance', 'quality': 'Media-Baja', 'speed': 'Muy Rápido'},
            'balanced': {'name': '⚖️ BALANCEADO', 'crf': '28', 'preset': 'medium', 'resolutions': ['854:480','1280:720','1920:1080'], 'audio_bitrate': '128k', 'description': 'Calidad equilibrada - Recomendado', 'quality': 'Buena', 'speed': 'Rápido'},
            'quality': {'name': '🎨 CALIDAD', 'crf': '23', 'preset': 'slow', 'resolutions': ['1280:720','1920:1080'], 'audio_bitrate': '160k', 'description': 'Alta calidad - Poca compresión', 'quality': 'Muy Buena', 'speed': 'Medio'},
            'max_quality': {'name': '👑 MÁXIMA CALIDAD', 'crf': '18', 'preset': 'veryslow', 'resolutions': ['1920:1080','3840:2160'], 'audio_bitrate': '192k', 'description': 'Máxima calidad - Compresión mínima', 'quality': 'Excelente', 'speed': 'Lento'},
            'audio_only': {'name': '🎵 SOLO AUDIO', 'crf': 'N/A', 'preset': 'fast', 'resolutions': ['no_video'], 'audio_bitrate': '128k', 'description': 'Extrae solo el audio (MP3)', 'quality': 'Solo Audio', 'speed': 'Rápido'}
        }

    async def initialize(self):
        self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        logger.info("✅ Bot iniciado correctamente - Modo inteligente activo")

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
            'ultra_turbo': 0.10, 'turbo':0.2, 'balanced':0.35, 'quality':0.55, 'max_quality':0.75, 'audio_only':0.05
        }
        return int(original_size * ratios.get(preset_key, 0.35))

    async def handle_start(self, event):
        await event.message.reply("🎬 ¡Hola! Envía un video y te mostraré todas las opciones de compresión con progreso en tiempo real.")

    async def handle_video(self, event):
        message = event.message
        if not (message.video or (message.document and message.document.mime_type and 'video' in message.document.mime_type)):
            return
        file_size = message.file.size
        if file_size > self.max_size:
            await message.reply(f"❌ Archivo muy grande ({self.get_file_size(file_size)})")
            return
        self.pending_videos[message.sender_id] = {'file_size': file_size, 'message': message}
        await self.show_quality_options(message, file_size)

    async def show_quality_options(self, message, file_size):
        buttons = []
        menu_text = "📊 **Elige la calidad deseada**:\n\n"
        for key, preset in self.compression_presets.items():
            for res in preset['resolutions']:
                if res == 'no_video':
                    label = f"{preset['name']} (Audio) ~{self.get_file_size(self.estimate_size(file_size,key))}"
                    callback_data = f"compress_{key}_audio"
                else:
                    w,h = res.split(':')
                    label = f"{preset['name']} {h}p ~{self.get_file_size(self.estimate_size(file_size,key))}"
                    callback_data = f"compress_{key}_{h}p"
                buttons.append([Button.inline(label, callback_data.encode())])
        buttons.append([Button.inline("❌ CANCELAR", b"cancel")])
        await message.reply(menu_text, buttons=buttons)

    async def handle_button_callback(self, event):
        data = event.data.decode()
        user_id = event.sender_id
        if data.startswith("compress_"):
            parts = data.split("_")
            preset_key = parts[1]
            resolution = parts[2] if len(parts)>2 else None
            video_info = self.pending_videos.get(user_id)
            if not video_info:
                await event.answer("❌ No hay video pendiente", alert=True)
                return
            video_info['preset_key'] = preset_key
            video_info['resolution'] = resolution
            await self.process_video(event, video_info)
        elif data == "cancel":
            if user_id in self.pending_videos:
                del self.pending_videos[user_id]
            await event.edit("❌ Proceso cancelado.")

    async def process_video(self, event, video_info):
        message = video_info['message']
        preset_key = video_info['preset_key']
        resolution = video_info['resolution']
        preset = self.compression_presets[preset_key]

        await event.edit(f"⚙️ Iniciando compresión {preset['name']} {resolution or ''}")

        temp_dir = tempfile.gettempdir()
        input_path = os.path.join(temp_dir, f"input_{message.id}.mp4")
        await message.download_media(file=input_path, progress_callback=lambda d,t: asyncio.create_task(self.update_progress(event,d,t,"Descargando")))

        output_ext = '.mp3' if preset_key=='audio_only' else '.mp4'
        output_path = os.path.join(temp_dir, f"compressed_{message.id}{output_ext}")

        ffmpeg_cmd = ['ffmpeg', '-i', input_path]
        if preset_key=='audio_only':
            ffmpeg_cmd += ['-vn','-c:a','libmp3lame','-b:a',preset['audio_bitrate'],'-y',output_path]
        else:
            ffmpeg_cmd += ['-c:v','libx264','-crf',preset['crf'],'-preset',preset['preset'],'-c:a','aac','-b:a',preset['audio_bitrate'],'-movflags','+faststart']
            if resolution != 'audio':
                ffmpeg_cmd += ['-vf', f'scale=-2:{resolution}']
            ffmpeg_cmd.append(output_path)

        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await self.ffmpeg_progress(event, process, input_path)

        await self.client.send_file(message.chat_id, output_path, caption=f"🎥 {preset['name']} {resolution or ''}", progress_callback=lambda d,t: asyncio.create_task(self.update_progress(event,d,t,"Subiendo")))

        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)

        await event.edit("🎉 ¡Proceso completado exitosamente!")

    async def update_progress(self, event, done, total, stage):
        percent = int(done/total*100) if total else 0
        bar_len = 20
        filled = int(bar_len*percent/100)
        bar = '█'*filled + '─'*(bar_len-filled)
        try:
            await event.edit(f"{stage}: [{bar}] {percent}%")
        except Exception:
            pass

    async def ffmpeg_progress(self, event, process, input_path):
        import re
        duration = 0
        # Obtener duración total del video
        result = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1', input_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            duration = float(result.stdout)
        except:
            duration = 0

        while True:
            line = await process.stderr.readline()
            if not line:
                break
            line = line.decode('utf-8').strip()
            match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
            if match and duration>0:
                h,m,s = int(match.group(1)),int(match.group(2)),float(match.group(3))
                current = h*3600 + m*60 + s
                await self.update_progress(event, current, duration, "Comprimiendo")
        await process.wait()

    async def run(self):
        await self.initialize()
        self.client.add_event_handler(self.handle_start, events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.handle_button_callback, events.CallbackQuery())
        self.client.add_event_handler(self.handle_video, events.NewMessage(func=lambda e: e.message.video or (e.message.document and e.message.document.mime_type and 'video' in e.message.document.mime_type)))
        logger.info("🤖 Bot iniciado con progreso en tiempo real")
        await self.client.run_until_disconnected()

async def main():
    required_vars = ['API_ID','API_HASH','BOT_TOKEN']
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"❌ Faltan variables: {missing}")
        return
    bot = VideoCompressorBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
