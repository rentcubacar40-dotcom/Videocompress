import os
import logging
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Variables de entorno (puedes cambiarlas aquí o en Render Dashboard)
API_ID = os.environ.get("API_ID", "20534584")  # Puedes setear en Render
API_HASH = os.environ.get("API_HASH", "6d5b13261d2c92a9a00afc1fd613b9df")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8562042457:AAGA__pfWDMVfdslzqwnoFl4yLrAre-HJ5I")
MAX_VIDEO_SIZE = 1000 * 1024 * 1024  # 50MB límite para Telegram
COMPRESSED_FOLDER = "compressed_videos"
PORT = int(os.environ.get("PORT", 8080))  # Render asigna este puerto

# Importamos pyrogram después de definir variables
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import subprocess
import shutil

def check_ffmpeg():
    """Verifica que ffmpeg esté instalado"""
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            logger.info(f"✅ ffmpeg instalado: {version_line}")
            return True
        else:
            logger.error("❌ ffmpeg no responde correctamente")
            return False
    except Exception as e:
        logger.error(f"❌ Error verificando ffmpeg: {e}")
        return False

# Verificar ffmpeg al inicio
if not check_ffmpeg():
    logger.error("FFmpeg no está disponible. El bot no puede funcionar.")
    sys.exit(1)

# Crear carpeta para videos comprimidos
Path(COMPRESSED_FOLDER).mkdir(exist_ok=True)

# Inicializar cliente Pyrogram
app = Client(
    "video_compressor_bot",
    api_id=int(API_ID) if API_ID.isdigit() else API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=2,  # Menos workers para plan free
    workdir="/app"  # Especificar workdir explícitamente
)

def get_video_info(file_path):
    """Obtiene información del video usando ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration,bit_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        info = result.stdout.strip().split('\n')
        
        return {
            'width': int(info[0]) if len(info) > 0 else 0,
            'height': int(info[1]) if len(info) > 1 else 0,
            'duration': float(info[2]) if len(info) > 2 else 0,
            'bitrate': int(info[3]) if len(info) > 3 else 0
        }
    except Exception as e:
        logger.error(f"Error obteniendo info del video: {e}")
        return None

def compress_video(input_path, output_path, quality='medium'):
    """Comprime un video usando ffmpeg"""
    try:
        video_info = get_video_info(input_path)
        if not video_info:
            return False, "No se pudo obtener información del video"
        
        # Determinar parámetros de compresión según calidad
        quality_presets = {
            'low': {
                'crf': 28,
                'preset': 'fast',
                'maxrate': '500k',
                'bufsize': '1000k'
            },
            'medium': {
                'crf': 23,
                'preset': 'medium',
                'maxrate': '1500k',
                'bufsize': '3000k'
            },
            'high': {
                'crf': 18,
                'preset': 'slow',
                'maxrate': '2500k',
                'bufsize': '5000k'
            }
        }
        
        preset = quality_presets.get(quality, quality_presets['medium'])
        
        # Ajustar resolución si es necesario
        scale_filter = ""
        if video_info['width'] > 1280:
            scale_filter = "scale=1280:-2"
        
        # Comando de compresión
        cmd = [
            'ffmpeg', '-i', input_path,
            '-c:v', 'libx264',
            '-crf', str(preset['crf']),
            '-preset', preset['preset'],
            '-maxrate', preset['maxrate'],
            '-bufsize', preset['bufsize'],
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-y'  # Sobrescribir sin preguntar
        ]
        
        if scale_filter:
            cmd.extend(['-vf', scale_filter])
        
        cmd.append(output_path)
        
        logger.info(f"Ejecutando comando: {' '.join(cmd)}")
        
        # Ejecutar compresión con timeout (15 minutos para Render Free)
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            timeout=900  # 15 minutos timeout
        )
        
        if result.returncode != 0:
            logger.error(f"Error en compresión: {result.stderr}")
            return False, f"Error en compresión: {result.stderr[:200]}"
        
        # Verificar tamaño del archivo comprimido
        compressed_size = os.path.getsize(output_path)
        original_size = os.path.getsize(input_path)
        
        reduction = ((original_size - compressed_size) / original_size) * 100
        
        return True, {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'reduction': reduction,
            'output_path': output_path
        }
        
    except subprocess.TimeoutExpired:
        logger.error("Timeout en compresión (más de 15 minutos)")
        return False, "La compresión tardó demasiado tiempo (>15 min)"
    except Exception as e:
        logger.error(f"Error comprimiendo video: {e}")
        return False, f"Error: {str(e)}"

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Maneja el comando /start"""
    welcome_text = """
🎬 **Bot Compresor de Videos**

¡Hola! Soy un bot que te ayuda a comprimir videos para que ocupen menos espacio.

📤 **Cómo usarme:**
1. Envíame un video (hasta 2GB)
2. Elige la calidad de compresión
3. ¡Recibe tu video comprimido!

⚙️ **Calidades disponibles:**
• **Baja** - Máxima compresión (calidad aceptable)
• **Media** - Balance entre tamaño y calidad
• **Alta** - Mínima compresión (casi igual al original)

📝 **Comandos disponibles:**
/start - Muestra este mensaje
/help - Muestra ayuda
/status - Muestra el estado del bot

⚠️ **Nota:** Los videos muy largos pueden tardar varios minutos en procesarse.
    """
    
    await message.reply_text(welcome_text)

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Maneja el comando /help"""
    help_text = """
🤖 **Ayuda del Bot Compresor**

**Para comprimir un video:**
1. Simplemente envíame cualquier video
2. Te preguntaré qué calidad prefieres
3. Procesaré el video y te lo enviaré de vuelta

**Formatos soportados:**
- MP4, AVI, MOV, MKV, FLV, WMV, y más

**Límites:**
- Máximo 2GB por video (límite de Telegram)
- Procesamiento: 10-15 minutos máximo (límite de Render)

**Problemas comunes:**
• Si el bot no responde, espera unos segundos
• Los videos muy largos tardan más
• Asegúrate de enviar solo videos

**Soporte:** Si tienes problemas, intenta reiniciar el bot con /start
    """
    
    await message.reply_text(help_text)

@app.on_message(filters.command("status"))
async def status_command(client: Client, message: Message):
    """Maneja el comando /status"""
    import psutil
    
    # Obtener uso de memoria
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    status_text = f"""
🟢 **Estado del Bot - Docker**

• **Servidor:** Render (Free Tier)
• **Puerto:** {PORT}
• **Hora actual:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
• **Directorio de trabajo:** {os.getcwd()}
• **FFmpeg:** ✅ Instalado

**Uso de recursos:**
• **Memoria:** {memory.percent}% usado
• **Disco:** {disk.percent}% usado
• **CPU:** {psutil.cpu_percent()}% usado

**Configuración Docker:**
• Usuario: appuser (no-root)
• Workdir: /app
• Puerto expuesto: 8080

**Nota:** El bot se reiniciará después de 15 minutos de inactividad.
    """
    
    await message.reply_text(status_text)

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    """Maneja los videos enviados por el usuario"""
    try:
        # Verificar si es un video
        if message.document and not message.document.mime_type.startswith('video/'):
            await message.reply_text("❌ Por favor, envía solo archivos de video.")
            return
        
        # Notificar que se está procesando
        processing_msg = await message.reply_text("📥 **Descargando video...**")
        
        # Descargar el video
        download_path = await message.download()
        
        if not download_path:
            await processing_msg.edit_text("❌ Error al descargar el video.")
            return
        
        await processing_msg.edit_text("✅ **Video descargado**\n\nSelecciona la calidad de compresión:")
        
        # Crear teclado para seleccionar calidad
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Baja", callback_data="quality_low"),
                InlineKeyboardButton("🟡 Media", callback_data="quality_medium"),
                InlineKeyboardButton("🔴 Alta", callback_data="quality_high")
            ],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ])
        
        await processing_msg.edit_text(
            "✅ **Video descargado**\n\n"
            "**Selecciona la calidad de compresión:**\n\n"
            "• 🟢 **Baja** - Máxima compresión\n"
            "• 🟡 **Media** - Balance recomendado\n"
            "• 🔴 **Alta** - Mínima compresión",
            reply_markup=keyboard
        )
        
        # Guardar información temporal
        if not hasattr(app, 'user_data'):
            app.user_data = {}
        
        app.user_data[message.from_user.id] = {
            'download_path': download_path,
            'processing_msg_id': processing_msg.id,
            'original_message_id': message.id
        }
        
    except Exception as e:
        logger.error(f"Error manejando video: {e}")
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_callback_query()
async def handle_callback(client: Client, callback_query):
    """Maneja las selecciones de calidad"""
    try:
        user_id = callback_query.from_user.id
        
        if callback_query.data == "cancel":
            await callback_query.message.edit_text("❌ **Proceso cancelado**")
            
            # Limpiar datos temporales
            if hasattr(app, 'user_data') and user_id in app.user_data:
                data = app.user_data[user_id]
                if os.path.exists(data['download_path']):
                    os.remove(data['download_path'])
                del app.user_data[user_id]
            
            await callback_query.answer()
            return
        
        if not hasattr(app, 'user_data') or user_id not in app.user_data:
            await callback_query.answer("Sesión expirada. Envía el video nuevamente.", show_alert=True)
            return
        
        data = app.user_data[user_id]
        download_path = data['download_path']
        
        # Determinar calidad
        quality_map = {
            'quality_low': 'low',
            'quality_medium': 'medium',
            'quality_high': 'high'
        }
        
        quality = quality_map.get(callback_query.data, 'medium')
        quality_names = {
            'low': 'Baja',
            'medium': 'Media',
            'high': 'Alta'
        }
        
        await callback_query.message.edit_text(f"⚙️ **Comprimiendo video ({quality_names[quality]})...**\n\nEsto puede tardar varios minutos...")
        
        # Crear nombre para archivo comprimido
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        compressed_path = os.path.join(
            COMPRESSED_FOLDER,
            f"compressed_{timestamp}_{user_id}.mp4"
        )
        
        # Comprimir video
        success, result = compress_video(download_path, compressed_path, quality)
        
        if not success:
            await callback_query.message.edit_text(f"❌ **Error en compresión:**\n{result}")
            
            # Limpiar archivos
            if os.path.exists(download_path):
                os.remove(download_path)
            if user_id in app.user_data:
                del app.user_data[user_id]
            
            return
        
        # Enviar video comprimido
        await callback_query.message.edit_text("📤 **Enviando video comprimido...**")
        
        # Preparar mensaje con estadísticas
        stats = result
        original_mb = stats['original_size'] / (1024 * 1024)
        compressed_mb = stats['compressed_size'] / (1024 * 1024)
        
        caption = (
            f"✅ **Video Comprimido**\n\n"
            f"**Calidad:** {quality_names[quality]}\n"
            f"**Tamaño original:** {original_mb:.2f} MB\n"
            f"**Tamaño comprimido:** {compressed_mb:.2f} MB\n"
            f"**Reducción:** {stats['reduction']:.1f}%\n\n"
            f"⚡ **Proceso completado con éxito!**"
        )
        
        # Enviar video
        await client.send_video(
            chat_id=callback_query.message.chat.id,
            video=compressed_path,
            caption=caption,
            supports_streaming=True
        )
        
        await callback_query.message.delete()
        
        # Limpiar archivos temporales
        if os.path.exists(download_path):
            os.remove(download_path)
        if os.path.exists(compressed_path):
            os.remove(compressed_path)
        
        # Limpiar datos de usuario
        if hasattr(app, 'user_data') and user_id in app.user_data:
            del app.user_data[user_id]
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error en callback: {e}")
        await callback_query.message.edit_text(f"❌ **Error:** {str(e)}")
        await callback_query.answer()

async def web_server():
    """Servidor web simple para mantener el bot activo en Render"""
    from aiohttp import web
    
    async def handle(request):
        return web.Response(text="Bot de Telegram activo y funcionando ✅")
    
    async def health_check(request):
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "telegram-video-compressor"
        })
    
    app_web = web.Application()
    app_web.router.add_get('/', handle)
    app_web.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"Servidor web iniciado en puerto {PORT}")

async def main():
    """Función principal para ejecutar el bot"""
    logger.info("Iniciando bot de compresión de videos...")
    logger.info(f"Directorio actual: {os.getcwd()}")
    logger.info(f"Puerto: {PORT}")
    
    # Iniciar servidor web en segundo plano
    web_task = asyncio.create_task(web_server())
    
    # Iniciar el bot de Telegram
    await app.start()
    
    # Obtener información del bot
    me = await app.get_me()
    logger.info(f"✅ Bot iniciado como: @{me.username}")
    logger.info(f"✅ ID del bot: {me.id}")
    
    # Mantener el bot corriendo
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        sys.exit(1)
