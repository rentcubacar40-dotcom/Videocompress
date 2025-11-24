import os
import asyncio
import logging
import tempfile
import time
import subprocess
import sys
import re
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename
from telethon.tl.custom import Button

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
    sys.modules['imghdr'] = imghdr

class VideoCompressorBot:
    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.bot_token = os.getenv('BOT_TOKEN')
        self.client = None
        self.max_size = 2000 * 1024 * 1024  # 2GB máximo
        self.pending_videos = {}  # videos pendientes
        
        # Presets con múltiples resoluciones
        self.compression_presets = {
            'ultra_turbo': {'name':'🚀 ULTRA TURBO','crf':'35','preset':'veryfast','audio_bitrate':'64k','description':'Máxima compresión','quality':'Baja','speed':'Muy Rápido','resolutions':['480p','360p']},
            'turbo': {'name':'⚡ TURBO','crf':'32','preset':'veryfast','audio_bitrate':'96k','description':'Alta compresión','quality':'Media-Baja','speed':'Muy Rápido','resolutions':['720p','480p','360p']},
            'balanced': {'name':'⚖️ BALANCEADO','crf':'28','preset':'medium','audio_bitrate':'128k','description':'Calidad equilibrada','quality':'Buena','speed':'Rápido','resolutions':['1080p','720p','480p']},
            'quality': {'name':'🎨 CALIDAD','crf':'23','preset':'slow','audio_bitrate':'160k','description':'Alta calidad','quality':'Muy Buena','speed':'Medio','resolutions':['1080p','720p','480p','360p']},
            'max_quality': {'name':'👑 MÁXIMA CALIDAD','crf':'18','preset':'veryslow','audio_bitrate':'192k','description':'Máxima calidad','quality':'Excelente','speed':'Lento','resolutions':['4k','1080p','720p']},
            'audio_only': {'name':'🎵 SOLO AUDIO','crf':'N/A','preset':'fast','audio_bitrate':'128k','description':'Extrae solo el audio','quality':'Solo Audio','speed':'Rápido','resolutions':['audio']}
        }
    
    async def initialize(self):
        self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        logger.info("✅ Bot iniciado correctamente")
    
    def get_file_size(self, size_bytes):
        if size_bytes==0: return "0B"
        size_names=["B","KB","MB","GB"]
        i=0
        while size_bytes>=1024 and i<len(size_names)-1:
            size_bytes/=1024.0
            i+=1
        return f"{size_bytes:.2f} {size_names[i]}"
    
    async def show_compression_options(self, message, file_size, file_path=None):
        user_id = message.sender_id
        self.pending_videos[user_id]={'file_size':file_size,'file_path':file_path,'message':message}
        buttons=[]
        for key,preset in self.compression_presets.items():
            for res in preset['resolutions']:
                btn_text=f"{preset['name']} {res}"
                buttons.append([Button.inline(btn_text,f"compress_{key}_{res}".encode())])
        buttons.append([Button.inline("❌ CANCELAR",b"cancel")])
        menu_text=f"🎬 Video recibido: {self.get_file_size(file_size)}\nSelecciona compresión y resolución:"
        await message.reply(menu_text,buttons=buttons)
    
    async def handle_button_callback(self,event):
        try:
            data = event.data.decode()
            user_id = event.sender_id
            if data.startswith("compress_"):
                _,preset_key,resolution=data.split("_",2)
                video_info=self.pending_videos.get(user_id)
                if not video_info:
                    await event.answer("❌ No hay video pendiente",alert=True)
                    return
                await event.edit(f"⚙️ Iniciando compresión {self.compression_presets[preset_key]['name']} {resolution}")
                # Descargar
                if not video_info.get('file_path'):
                    file_path=await self.download_file(video_info['message'])
                    video_info['file_path']=file_path
                output_path=await self.compress_video(video_info['file_path'],preset_key,resolution,event)
                if output_path:
                    await self.upload_file(video_info['message'],output_path,preset_key,event)
                self.cleanup_files(video_info['file_path'],output_path)
                if user_id in self.pending_videos: del self.pending_videos[user_id]
            elif data=="cancel":
                if user_id in self.pending_videos: del self.pending_videos[user_id]
                await event.edit("❌ Compresión cancelada")
        except Exception as e:
            logger.error(f"Error callback: {e}")
    
    async def download_file(self,message):
        temp_dir=tempfile.gettempdir()
        path=os.path.join(temp_dir,f"input_{message.id}.mp4")
        await message.download_media(file=path,progress_callback=self.download_progress(message))
        return path
    
    def download_progress(self,message):
        async def progress(current,total):
            percent=int(current*100/total)
            bar='█'*(percent//5)+'-'*(20-(percent//5))
            await message.edit(f"📥 Descargando...\n[{bar}] {percent}%")
        return progress
    
    async def compress_video(self,input_path,preset_key,resolution,event):
        preset=self.compression_presets[preset_key]
        temp_dir=tempfile.gettempdir()
        output_path=os.path.join(temp_dir,f"compressed_{event.sender_id}_{resolution}.mp4")
        # Duración total
        proc = await asyncio.create_subprocess_exec('ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',input_path,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,_=await proc.communicate()
        try: duration=float(stdout.decode().strip())
        except: duration=None
        scale={'4k':'3840:2160','1080p':'1920:1080','720p':'1280:720','480p':'854:480','360p':'640:360','audio':'no_video'}.get(resolution,'-1:-1')
        cmd=['ffmpeg','-i',input_path]
        if resolution=='audio':
            output_path=output_path.replace('.mp4','.mp3')
            cmd+=['-vn','-c:a','libmp3lame','-b:a',preset['audio_bitrate'],'-y']
        else:
            cmd+=['-c:v','libx264','-crf',preset['crf'],'-preset',preset['preset'],'-c:a','aac','-b:a',preset['audio_bitrate'],'-vf',f'scale={scale}','-movflags','+faststart','-y']
        process=await asyncio.create_subprocess_exec(*cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        pattern=re.compile(r'time=(\d+:\d+:\d+.\d+)')
        last_update=0
        while True:
            line=await process.stderr.readline()
            if not line: break
            line=line.decode()
            match=pattern.search(line)
            if match and duration:
                h,m,s=map(float,match.group(1).split(':'))
                seconds=h*3600+m*60+s
                percent=min(int((seconds/duration)*100),100)
                if percent-last_update>=2:
                    bar='█'*(percent//5)+'-'*(20-(percent//5))
                    await event.edit(f"⚙️ Comprimiendo {preset['name']} {resolution}\n[{bar}] {percent}%")
                    last_update=percent
        await process.wait()
        if process.returncode!=0: return None
        return output_path
    
    async def upload_file(self,message,file_path,preset_key,event):
        preset=self.compression_presets[preset_key]
        ext='.mp3' if 'audio' in file_path else '.mp4'
        fname=f"compressed_{preset_key}{ext}"
        await self.client.send_file(message.chat_id,file_path,caption=f"🎥 {preset['name']}",attributes=[DocumentAttributeFilename(file_name=fname)],progress_callback=self.upload_progress(message))
    
    def upload_progress(self,message):
        async def progress(current,total):
            percent=int(current*100/total)
            bar='█'*(percent//5)+'-'*(20-(percent//5))
            await message.edit(f"📤 Subiendo...\n[{bar}] {percent}%")
        return progress
    
    def cleanup_files(self,*files):
        for f in files:
            try:
                if f and os.path.exists(f): os.remove(f)
            except: pass
    
    async def handle_video(self,event):
        message=event.message
        if not (message.video or (message.document and message.document.mime_type and 'video' in message.document.mime_type)): return
        size=message.file.size
        if size>self.max_size:
            await message.reply(f"❌ Archivo muy grande ({self.get_file_size(size)})")
            return
        await self.show_compression_options(message,size)
    
    async def handle_start(self,event):
        await event.message.reply("🎬 Bot Compresor Inteligente\nEnvíame un video y elige la calidad para comenzar la compresión.")
    
    async def run(self):
        await self.initialize()
        self.client.add_event_handler(self.handle_start,events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.handle_button_callback,events.CallbackQuery())
        self.client.add_event_handler(self.handle_video,events.NewMessage(func=lambda e:e.message.video or (e.message.document and e.message.document.mime_type and 'video' in e.message.document.mime_type)))
        logger.info("🤖 Bot iniciado")
        await self.client.run_until_disconnected()

async def main():
    required_vars=['API_ID','API_HASH','BOT_TOKEN']
    missing=[v for v in required_vars if not os.getenv(v)]
    if missing: logger.error(f"❌ Faltan variables: {missing}"); return
    bot=VideoCompressorBot()
    await bot.run()

if __name__=='__main__':
    asyncio.run(main())
