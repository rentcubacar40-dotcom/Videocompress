import os
import asyncio
import logging
import tempfile
import sys
import re
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Compatibilidad imghdr
try:
    import imghdr
except ImportError:
    import types
    imghdr = types.ModuleType('imghdr')
    def test_jpeg(h): return 'jpeg' if h.startswith(b'\xff\xd8') else None
    def test_png(h): return 'png' if h.startswith(b'\x89PNG\r\n\x1a\n') else None
    def test_gif(h): return 'gif' if h.startswith(b'GIF8') else None
    imghdr.test_jpeg = test_jpeg
    imghdr.test_png = test_png
    imghdr.test_gif = test_gif
    def what(file,h=None):
        if h is None:
            with open(file,'rb') as f: h=f.read(32)
        for test in [test_jpeg,test_png,test_gif]:
            result=test(h)
            if result: return result
        return None
    imghdr.what=what
    sys.modules['imghdr']=imghdr

# Telethon
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename

class VideoCompressorBot:
    def __init__(self):
        self.api_id = int(os.getenv("API_ID"))
        self.api_hash = os.getenv("API_HASH")
        self.bot_token = os.getenv("BOT_TOKEN")
        self.client = None
        self.max_size = 2*1024*1024*1024  # 2GB
        self.pending_videos = {}

        # Presets completos
        self.compression_presets = {
            'ultra_turbo': {'crf':'35','preset':'veryfast','scale':'854:480','audio_bitrate':'64k','name':'🚀 ULTRA TURBO','description':'Máxima compresión','quality':'Baja','speed':'Muy Rápido'},
            'turbo': {'crf':'32','preset':'veryfast','scale':'1280:720','audio_bitrate':'96k','name':'⚡ TURBO','description':'Alta compresión','quality':'Media-Baja','speed':'Muy Rápido'},
            'balanced': {'crf':'28','preset':'medium','scale':'1920:1080','audio_bitrate':'128k','name':'⚖️ BALANCEADO','description':'Calidad equilibrada','quality':'Buena','speed':'Rápido'},
            'quality': {'crf':'23','preset':'slow','scale':'1920:1080','audio_bitrate':'160k','name':'🎨 CALIDAD','description':'Alta calidad','quality':'Muy Buena','speed':'Medio'},
            'max_quality': {'crf':'18','preset':'veryslow','scale':'original','audio_bitrate':'192k','name':'👑 MÁXIMA CALIDAD','description':'Máxima calidad','quality':'Excelente','speed':'Lento'},
            'audio_only': {'crf':'N/A','preset':'fast','scale':'no_video','audio_bitrate':'128k','name':'🎵 SOLO AUDIO','description':'Extrae solo audio','quality':'Solo Audio','speed':'Rápido'}
        }

    async def initialize(self):
        self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        logger.info("✅ Bot iniciado correctamente")

    def get_file_size(self,size_bytes):
        if size_bytes==0: return "0B"
        size_names=["B","KB","MB","GB"]
        i=0
        while size_bytes>=1024 and i<len(size_names)-1:
            size_bytes/=1024.0
            i+=1
        return f"{size_bytes:.2f} {size_names[i]}"

    def calculate_estimated_size(self,original_size,preset_key):
        ratios={'ultra_turbo':0.10,'turbo':0.20,'balanced':0.35,'quality':0.55,'max_quality':0.75,'audio_only':0.05}
        return original_size*ratios.get(preset_key,0.35)

    async def download_file(self,message):
        try:
            temp_dir=tempfile.gettempdir()
            file_name=f"input_{message.id}.mp4"
            file_path=os.path.join(temp_dir,file_name)
            await message.download_media(file=file_path)
            return file_path
        except Exception as e:
            logger.error(f"Error descargando: {e}")
            return None

    async def get_video_duration(self, file_path):
        """Obtener duración del video en segundos usando FFmpeg"""
        try:
            proc = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            duration = float(stdout.decode().strip())
            return duration
        except Exception as e:
            logger.error(f"Error obteniendo duración: {e}")
            return None

    async def compress_video_with_preset(self,input_path,message,preset_key,event=None):
        try:
            preset=self.compression_presets[preset_key]
            temp_dir=tempfile.gettempdir()
            output_path=os.path.join(temp_dir,f"compressed_{message.id}.mp4")
            input_size=os.path.getsize(input_path)

            # Obtener duración para calcular progreso
            duration = await self.get_video_duration(input_path)
            if not duration: duration=1  # evitar división por cero

            cmd=['ffmpeg','-i',input_path]
            if preset_key=='audio_only':
                output_path=output_path.replace('.mp4','.mp3')
                cmd.extend(['-vn','-c:a','libmp3lame','-b:a',preset['audio_bitrate'],'-y'])
            else:
                cmd.extend(['-c:v','libx264','-crf',preset['crf'],'-preset',preset['preset'],
                            '-c:a','aac','-b:a',preset['audio_bitrate'],'-movflags','+faststart'])
                if preset['scale']!='original':
                    cmd.extend(['-vf',f'scale={preset["scale"]}'])
                cmd.append('-y')
            cmd.append(output_path)

            process=await asyncio.create_subprocess_exec(*cmd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

            # Leer progreso en tiempo real
            if event:
                pattern = re.compile(r'time=(\d+):(\d+):(\d+.\d+)')
                while True:
                    line=await process.stderr.readline()
                    if not line: break
                    line=line.decode()
                    match = pattern.search(line)
                    if match:
                        h,m,s = map(float, match.groups())
                        elapsed = h*3600 + m*60 + s
                        percent = min(100, elapsed/duration*100)
                        await event.edit(f"⚙️ **Procesando {preset['name']}**: {percent:.1f}%")

            stdout,stderr=await process.communicate()
            if process.returncode==0 and os.path.exists(output_path):
                return output_path
            else:
                logger.error(f"FFmpeg error: {stderr.decode() if stderr else 'Unknown'}")
                return None
        except Exception as e:
            logger.error(f"Error comprimiendo: {e}")
            return None

    async def upload_file(self,message,file_path,preset_key):
        try:
            preset=self.compression_presets[preset_key]
            file_ext='.mp3' if preset_key=='audio_only' else '.mp4'
            file_name=f"compressed_{preset_key}{file_ext}"
            if preset_key=='audio_only':
                await self.client.send_file(message.chat_id,file_path,
                    caption=f"🎵 **Audio Extraído**\nPreset: {preset['name']}",
                    attributes=[DocumentAttributeFilename(file_name=file_name)])
            else:
                await self.client.send_file(message.chat_id,file_path,
                    caption=f"🎥 **Video Comprimido**\nPreset: {preset['name']}",
                    attributes=[
                        DocumentAttributeVideo(duration=0,w=0,h=0,
                        round_message=False,supports_streaming=True),
                        DocumentAttributeFilename(file_name=file_name)],
                    force_document=False)
            return True
        except Exception as e:
            logger.error(f"Error subiendo: {e}")
            return False

    def cleanup_files(self,*files):
        for f in files:
            try:
                if f and os.path.exists(f): os.remove(f)
            except Exception as e:
                logger.error(f"Error limpiando {f}: {e}")

    async def handle_start(self,event):
        text="""
🎬 **BOT COMPRESOR INTELIGENTE**
Envía un video y te mostraré todas las opciones de compresión con progreso en tiempo real.
"""
        await event.message.reply(text)

    async def handle_video(self,event):
        message=event.message
        if not (message.video or (message.document and message.document.mime_type and 'video' in message.document.mime_type)):
            return
        file_size=message.file.size
        if file_size>self.max_size:
            await message.reply(f"❌ Archivo muy grande ({self.get_file_size(file_size)})")
            return

        self.pending_videos[message.sender_id]={'message':message,'file_size':file_size}
        buttons=[[Button.inline(f"{p['name']} (~{self.get_file_size(self.calculate_estimated_size(file_size,k))})",f"compress_{k}".encode())] for k,p in self.compression_presets.items()]
        buttons.append([Button.inline("❌ CANCELAR",b"cancel")])
        await message.reply("📊 Selecciona la compresión que desees:",buttons=buttons)

    async def handle_button(self,event):
        try:
            data=event.data.decode()
            user_id=event.sender_id
            if user_id not in self.pending_videos:
                await event.answer("❌ No hay video pendiente",alert=True)
                return
            video_info=self.pending_videos[user_id]
            message=video_info['message']

            if data.startswith("compress_"):
                preset_key=data.replace("compress_","")
                await event.edit(f"⚙️ Iniciando compresión: {self.compression_presets[preset_key]['name']}...")
                file_path=await self.download_file(message)
                if not file_path:
                    await event.edit("❌ Error descargando el video")
                    return
                output_path=await self.compress_video_with_preset(file_path,message,preset_key,event)
                if not output_path:
                    await event.edit("❌ Error en compresión")
                    self.cleanup_files(file_path)
                    return
                await event.edit("📤 Subiendo resultado...")
                await self.upload_file(message,output_path,preset_key)
                self.cleanup_files(file_path,output_path)
                del self.pending_videos[user_id]
                await event.edit("🎉 ¡Proceso completado!")

            elif data=="cancel":
                del self.pending_videos[user_id]
                await event.edit("❌ Compresión cancelada")

        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await event.answer("❌ Error procesando selección",alert=True)

    async def run(self):
        await self.initialize()
        self.client.add_event_handler(self.handle_start,events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.handle_video,events.NewMessage(func=lambda e:e.message.video or (e.message.document and e.message.document.mime_type and 'video' in e.message.document.mime_type)))
        self.client.add_event_handler(self.handle_button,events.CallbackQuery())
        logger.info("🤖 Bot iniciado")
        await self.client.run_until_disconnected()

async def main():
    required_vars=['API_ID','API_HASH','BOT_TOKEN']
    missing_vars=[v for v in required_vars if not os.getenv(v)]
    if missing_vars:
        logger.error(f"❌ Faltan variables: {missing_vars}")
        return
    bot=VideoCompressorBot()
    await bot.run()

if __name__=='__main__':
    asyncio.run(main())
