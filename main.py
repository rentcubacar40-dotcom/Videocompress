import os
import asyncio
import logging
import sys
import signal
from pathlib import Path
from typing import Optional

from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from dotenv import load_dotenv
import ffmpeg

# Cargar variables de entorno
load_dotenv()

# Configurar logging para Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Para ver logs en Render
    ]
)
logger = logging.getLogger(__name__)

# Configuración del bot
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Validar variables de entorno
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("Faltan variables de entorno. Verifica API_ID, API_HASH y BOT_TOKEN")
    sys.exit(1)

try:
    API_ID = int(API_ID)
except ValueError:
    logger.error("API_ID debe ser un número")
    sys.exit(1)

# Configuración específica para Render
IS_RENDER = os.getenv("RENDER", "false").lower() == "true"
PORT = int(os.getenv("PORT", 8080))  # Render asigna puerto automáticamente

# Configuración de compresión
COMPRESSION_PRESETS = {
    "low": {
        "video_bitrate": "500k",
        "audio_bitrate": "64k",
        "resolution": "854x480",
        "crf": 28,
        "preset": "ultrafast"  # Más rápido para servidor
    },
    "medium": {
        "video_bitrate": "1000k",
        "audio_bitrate": "128k",
        "resolution": "1280x720",
        "crf": 23,
        "preset": "fast"
    },
    "high": {
        "video_bitrate": "2000k",
        "audio_bitrate": "192k",
        "resolution": "1920x1080",
        "crf": 20,
        "preset": "medium"
    }
}

# Configuración para Render (límites de tiempo)
MAX_VIDEO_DURATION = 600  # 10 minutos máximo
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB máximo

# Crear carpetas necesarias
BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
COMPRESSED_DIR = BASE_DIR / "compressed"

DOWNLOADS_DIR.mkdir(exist_ok=True)
COMPRESSED_DIR.mkdir(exist_ok=True)

# Limpiador automático de archivos temporales
async def cleanup_temp_files():
    """Limpiar archivos temporales antiguos"""
    import time
    import shutil
    
    current_time = time.time()
    max_age = 3600  # 1 hora
    
    for temp_dir in [DOWNLOADS_DIR, COMPRESSED_DIR]:
        for file_path in temp_dir.glob("*"):
            try:
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age:
                        file_path.unlink()
                        logger.info(f"Eliminado archivo temporal: {file_path.name}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar {file_path}: {e}")

class VideoCompressorBot:
    def __init__(self):
        self.app = Client(
            "video_compressor_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            in_memory=True,  # Optimizar para Render
            workers=2  # Reducir workers para ahorrar recursos
        )
        self.setup_handlers()
        
    def setup_handlers(self):
        """Configurar manejadores de comandos"""
        
        @self.app.on_message(filters.command(["start", "help"]))
        async def start_command(client: Client, message: Message):
            """Manejador del comando /start"""
            welcome_text = """
🎬 **VIDEO COMPRESSOR BOT**

¡Hola! Soy un bot que comprime videos para reducir su tamaño.

**📊 Límites del servidor:**
• Máximo 10 minutos por video
• Máximo 500 MB por video
• Formatos: MP4, AVI, MKV, MOV, etc.

**⚡ Comandos:**
/start - Mostrar este mensaje
/compress - Comprimir un video
/stats - Ver estadísticas
/clean - Limpiar archivos temporales

**🔧 ¿Cómo funciona?**
1. Envíame un video
2. Elige calidad (Baja/Media/Alta)
3. Recibe el video comprimido

**🚀 Optimizado para calidad/servidor**
"""
            await message.reply_text(
                welcome_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 Enviar Video", callback_data="send_video")],
                    [InlineKeyboardButton("⚙️ Ver Opciones", callback_data="show_options")]
                ])
            )
        
        @self.app.on_message(filters.command("stats"))
        async def stats_command(client: Client, message: Message):
            """Mostrar estadísticas del bot"""
            import psutil
            import shutil
            
            # Obtener uso de recursos
            disk_usage = shutil.disk_usage(BASE_DIR)
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=1)
            
            stats_text = f"""
📈 **ESTADÍSTICAS DEL BOT**

**💾 Uso de Disco:**
• Total: {self.format_size(disk_usage.total)}
• Usado: {self.format_size(disk_usage.used)}
• Libre: {self.format_size(disk_usage.free)}

**🖥️ Uso de Recursos:**
• CPU: {cpu_percent}%
• RAM: {memory.percent}%

**🗂️ Archivos Temporales:**
• Downloads: {len(list(DOWNLOADS_DIR.glob('*')))} archivos
• Compressed: {len(list(COMPRESSED_DIR.glob('*')))} archivos

**🌐 Entorno:**
• Render: {'✅ Sí' if IS_RENDER else '❌ No'}
• Puerto: {PORT}
"""
            await message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        
        @self.app.on_message(filters.command("clean"))
        async def clean_command(client: Client, message: Message):
            """Limpiar archivos temporales"""
            await cleanup_temp_files()
            await message.reply_text("✅ Archivos temporales limpiados")
        
        @self.app.on_message(filters.video | filters.document)
        async def handle_video(client: Client, message: Message):
            """Manejar video enviado"""
            user_id = message.from_user.id
            
            # Verificar si es un video
            if message.document and not (message.document.mime_type and message.document.mime_type.startswith('video/')):
                await message.reply_text("❌ Por favor, envía un archivo de video válido")
                return
            
            # Verificar tamaño del archivo
            file_size = (message.video.file_size if message.video 
                        else message.document.file_size if message.document 
                        else 0)
            
            if file_size > MAX_VIDEO_SIZE:
                await message.reply_text(
                    f"❌ El video es demasiado grande.\n"
                    f"Máximo permitido: {self.format_size(MAX_VIDEO_SIZE)}\n"
                    f"Tu video: {self.format_size(file_size)}"
                )
                return
            
            # Procesar video
            await self.process_video(message, user_id)
        
        @self.app.on_callback_query()
        async def handle_callback(client, callback_query):
            """Manejar callbacks"""
            data = callback_query.data
            user_id = callback_query.from_user.id
            
            try:
                if data.startswith("compress_"):
                    await self.handle_compression(callback_query, data)
                elif data == "send_video":
                    await callback_query.message.reply_text(
                        "📤 Envíame un video para comprimir (máx. 10min, 500MB)"
                    )
                elif data == "show_options":
                    await callback_query.message.reply_text(
                        "⚙️ **Opciones de compresión:**\n\n"
                        "• **Baja**: 480p, máxima compresión\n"
                        "• **Media**: 720p, balanceado\n"
                        "• **Alta**: 1080p, mejor calidad\n\n"
                        "Envía un video para comenzar!"
                    )
                elif data.startswith("cancel_"):
                    await self.cancel_compression(callback_query, data)
                
                await callback_query.answer()
                
            except Exception as e:
                logger.error(f"Error en callback: {e}")
                await callback_query.answer("❌ Error procesando solicitud", show_alert=True)
    
    async def process_video(self, message: Message, user_id: int):
        """Procesar video recibido"""
        try:
            # Enviar mensaje de procesamiento
            status_msg = await message.reply_text("📥 **Descargando video...**", parse_mode=ParseMode.MARKDOWN)
            
            # Generar nombres de archivo únicos
            file_id = message.video.file_id if message.video else message.document.file_id
            timestamp = int(asyncio.get_event_loop().time())
            original_filename = f"{user_id}_{file_id}_{timestamp}"
            
            download_path = DOWNLOADS_DIR / f"original_{original_filename}.mp4"
            
            # Descargar video
            download_task = asyncio.create_task(
                message.download(file_name=str(download_path))
            )
            
            # Esperar descarga con timeout
            try:
                await asyncio.wait_for(download_task, timeout=300)  # 5 minutos timeout
            except asyncio.TimeoutError:
                await status_msg.edit_text("❌ Timeout al descargar el video")
                if download_path.exists():
                    download_path.unlink()
                return
            
            await status_msg.edit_text("🔍 **Analizando video...**")
            
            # Verificar duración
            try:
                probe = ffmpeg.probe(str(download_path))
                video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
                
                if not video_stream:
                    await status_msg.edit_text("❌ No se encontró stream de video")
                    download_path.unlink()
                    return
                
                duration = float(video_stream.get('duration', 0))
                if duration > MAX_VIDEO_DURATION:
                    await status_msg.edit_text(
                        f"❌ Video demasiado largo.\n"
                        f"Máximo: {MAX_VIDEO_DURATION//60} minutos\n"
                        f"Tu video: {duration//60:.0f} minutos"
                    )
                    download_path.unlink()
                    return
                
                # Mostrar opciones de compresión
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔻 Baja", callback_data=f"compress_{original_filename}_low"),
                        InlineKeyboardButton("⚡ Media", callback_data=f"compress_{original_filename}_medium"),
                    ],
                    [
                        InlineKeyboardButton("🌟 Alta", callback_data=f"compress_{original_filename}_high"),
                        InlineKeyboardButton("❌ Cancelar", callback_data=f"cancel_{original_filename}")
                    ]
                ])
                
                file_size = download_path.stat().st_size
                
                await status_msg.edit_text(
                    f"✅ **Video recibido!**\n\n"
                    f"📊 **Información:**\n"
                    f"• Duración: {duration:.1f}s\n"
                    f"• Tamaño: {self.format_size(file_size)}\n"
                    f"• Resolución: {video_stream.get('width', '?')}x{video_stream.get('height', '?')}\n\n"
                    f"🎚 **Selecciona calidad:**",
                    reply_markup=keyboard
                )
                
            except ffmpeg.Error as e:
                await status_msg.edit_text("❌ Error al analizar el video")
                logger.error(f"FFmpeg error: {e}")
                if download_path.exists():
                    download_path.unlink()
                    
        except Exception as e:
            logger.error(f"Error procesando video: {e}")
            await message.reply_text("❌ Error al procesar el video")
    
    async def handle_compression(self, callback_query, data: str):
        """Manejar solicitud de compresión"""
        parts = data.split("_")
        if len(parts) < 3:
            return
        
        user_id = callback_query.from_user.id
        original_filename = parts[1]
        preset = parts[2]
        
        message = callback_query.message
        download_path = DOWNLOADS_DIR / f"original_{original_filename}.mp4"
        compressed_path = COMPRESSED_DIR / f"compressed_{original_filename}_{preset}.mp4"
        
        if not download_path.exists():
            await message.edit_text("❌ El video original ya no está disponible")
            return
        
        await message.edit_text(f"⚙️ **Comprimiendo ({preset})...**\n⏳ Por favor espera...")
        
        # Comprimir video
        success = await self.compress_video(str(download_path), str(compressed_path), preset)
        
        if success and compressed_path.exists():
            # Calcular reducción
            original_size = download_path.stat().st_size
            compressed_size = compressed_path.stat().st_size
            reduction = ((original_size - compressed_size) / original_size) * 100
            
            await message.edit_text(
                f"✅ **Compresión completada!**\n\n"
                f"📊 **Resultados ({preset}):**\n"
                f"• Original: {self.format_size(original_size)}\n"
                f"• Comprimido: {self.format_size(compressed_size)}\n"
                f"• Reducción: {reduction:.1f}%\n\n"
                f"📤 **Enviando video...**"
            )
            
            # Enviar video comprimido
            try:
                await self.app.send_video(
                    user_id,
                    video=str(compressed_path),
                    caption=f"🎬 Video comprimido ({preset})\n"
                           f"📏 Tamaño: {self.format_size(compressed_size)}\n"
                           f"📉 Reducción: {reduction:.1f}%",
                    supports_streaming=True
                )
                
                await message.edit_text("✅ **Video enviado exitosamente!**")
                
            except Exception as e:
                logger.error(f"Error enviando video: {e}")
                await message.edit_text("❌ Error al enviar el video")
            
            # Limpiar archivos temporales
            try:
                download_path.unlink()
                compressed_path.unlink()
            except:
                pass
                
        else:
            await message.edit_text("❌ Error al comprimir el video")
            if download_path.exists():
                download_path.unlink()
    
    async def compress_video(self, input_path: str, output_path: str, preset: str) -> bool:
        """Comprimir video"""
        try:
            preset_config = COMPRESSION_PRESETS.get(preset, COMPRESSION_PRESETS["medium"])
            
            # Configurar FFmpeg optimizado para servidor
            stream = ffmpeg.input(input_path)
            
            output_kwargs = {
                'c:v': 'libx264',
                'c:a': 'aac',
                'b:v': preset_config["video_bitrate"],
                'b:a': preset_config["audio_bitrate"],
                'crf': preset_config["crf"],
                'preset': preset_config["preset"],  # Usar preset apropiado
                'movflags': '+faststart',
                'threads': 2,  # Limitar threads para Render
                'max_muxing_queue_size': 1024,
            }
            
            # Ejecutar de forma síncrona (pero en thread separado)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, 
                lambda: ffmpeg.output(stream, output_path, **output_kwargs).run(
                    overwrite_output=True,
                    quiet=True  # Reducir output
                )
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error comprimiendo: {e}")
            return False
    
    async def cancel_compression(self, callback_query, data: str):
        """Cancelar compresión"""
        parts = data.split("_")
        if len(parts) < 2:
            return
        
        original_filename = parts[1]
        download_path = DOWNLOADS_DIR / f"original_{original_filename}.mp4"
        
        if download_path.exists():
            download_path.unlink()
        
        await callback_query.message.edit_text("❌ Compresión cancelada")
    
    def format_size(self, size_bytes: int) -> str:
        """Formatear tamaño"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    async def start(self):
        """Iniciar bot"""
        logger.info("🚀 Iniciando Video Compressor Bot en Render...")
        
        # Limpiar archivos temporales al inicio
        await cleanup_temp_files()
        
        # Iniciar cliente
        await self.app.start()
        
        # Obtener información del bot
        me = await self.app.get_me()
        logger.info(f"🤖 Bot iniciado como @{me.username}")
        logger.info(f"🌐 Puerto: {PORT}")
        logger.info(f"💾 Directorio: {BASE_DIR}")
        
        # Mantener servicio web activo (para Render)
        if IS_RENDER:
            from aiohttp import web
            
            async def health_check(request):
                return web.Response(text="Bot is running")
            
            app = web.Application()
            app.router.add_get('/', health_check)
            app.router.add_get('/health', health_check)
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', PORT)
            await site.start()
            
            logger.info(f"✅ Servicio web iniciado en puerto {PORT}")
        
        # Mantener bot activo
        await idle()
        
        # Detener
        await self.stop()
    
    async def stop(self):
        """Detener bot"""
        logger.info("🛑 Deteniendo bot...")
        await cleanup_temp_files()
        await self.app.stop()
        logger.info("✅ Bot detenido")

# Manejar señales de sistema
def signal_handler(signum, frame):
    logger.info(f"Recibida señal {signum}, deteniendo...")
    asyncio.get_event_loop().create_task(bot.stop())

async def main():
    """Función principal"""
    global bot
    
    # Configurar manejador de señales
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Crear e iniciar bot
    bot = VideoCompressorBot()
    
    try:
        await bot.start()
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Verificar FFmpeg
    try:
        ffmpeg.probe("")  # Prueba simple
        logger.info("✅ FFmpeg está disponible")
    except:
        logger.error("❌ FFmpeg no está instalado. El bot no funcionará.")
        sys.exit(1)
    
    # Ejecutar
    asyncio.run(main())
