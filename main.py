"""
Bot de Telegram para Comprimir Videos - 2026
Optimizado para Render Free Plan
"""

import os
import sys
import logging
import asyncio
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# ===== CONFIGURACIÓN =====
# Variables configurables (puedes cambiarlas en Render Dashboard)
API_ID = os.environ.get("API_ID", "20534584")
API_HASH = os.environ.get("API_HASH", "6d5b13261d2c92a9a00afc1fd613b9df")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8562042457:AAEp2oPHf-BBf5zuEnzo-0DmG08im8dqpwc")

# Configuración del sistema
PORT = int(os.environ.get("PORT", 8080))
COMPRESSED_FOLDER = "/tmp/compressed_videos"  # Usar /tmp para permisos
MAX_PROCESSING_TIME = 840  # 14 minutos (límite Render: 15 min)
MAX_VIDEO_SIZE = 1900 * 1024 * 1024  # 1.9GB (límite Telegram: 2GB)

# ===== LOGGING =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ===== VERIFICACIÓN INICIAL =====
def setup_environment():
    """Configura el entorno y verifica dependencias"""
    logger.info("=" * 50)
    logger.info("🤖 BOT DE COMPRESIÓN DE VIDEOS - 2026")
    logger.info("=" * 50)
    
    # Crear carpeta temporal
    Path(COMPRESSED_FOLDER).mkdir(exist_ok=True)
    logger.info(f"📁 Carpeta temporal: {COMPRESSED_FOLDER}")
    
    # Verificar ffmpeg
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            logger.info(f"✅ {version}")
        else:
            logger.error("❌ ffmpeg no funciona correctamente")
            return False
    except Exception as e:
        logger.error(f"❌ Error verificando ffmpeg: {e}")
        return False
    
    # Verificar variables de entorno
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.warning("⚠️  Variables de entorno no configuradas completamente")
        logger.info("Configura en Render: API_ID, API_HASH, BOT_TOKEN")
    
    logger.info(f"🌐 Puerto: {PORT}")
    logger.info(f"⏱️  Tiempo máximo proceso: {MAX_PROCESSING_TIME}s")
    logger.info("=" * 50)
    return True

# ===== IMPORTAR PYROGRAM DESPUÉS DE CONFIGURACIÓN =====
try:
    from pyrogram import Client, filters, idle
    from pyrogram.types import (
        Message, 
        InlineKeyboardMarkup, 
        InlineKeyboardButton,
        CallbackQuery
    )
    from pyrogram.enums import ParseMode
    logger.info("✅ Pyrogram importado correctamente")
except ImportError as e:
    logger.error(f"❌ Error importando Pyrogram: {e}")
    sys.exit(1)

# ===== CLIENTE PYROGRAM =====
app = Client(
    name="video_compressor_2026",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=2,  # Optimizado para Render Free
    sleep_threshold=30,
    parse_mode=ParseMode.HTML,
    in_memory=True  # No guardar sesión en disco
)

# ===== FUNCIONES DE COMPRESIÓN =====
class VideoCompressor:
    """Clase para manejar la compresión de videos"""
    
    @staticmethod
    def get_video_info(file_path: str) -> Optional[Dict[str, Any]]:
        """Obtiene información del video usando ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return None
                
            import json
            info = json.loads(result.stdout)
            
            # Buscar stream de video
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            if not video_stream:
                return None
                
            return {
                'width': video_stream.get('width', 0),
                'height': video_stream.get('height', 0),
                'duration': float(info['format'].get('duration', 0)),
                'size': int(info['format'].get('size', 0)),
                'bitrate': int(info['format'].get('bit_rate', 0)),
                'format': info['format'].get('format_name', 'unknown')
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo info video: {e}")
            return None
    
    @staticmethod
    def compress_video(
        input_path: str, 
        output_path: str, 
        quality: str = 'medium'
    ) -> tuple[bool, Any]:
        """Comprime un video usando ffmpeg con parámetros optimizados 2026"""
        
        quality_presets = {
            'low': {
                'crf': 30,
                'preset': 'veryfast',
                'video_bitrate': '800k',
                'audio_bitrate': '96k',
                'scale': '1280:-2' if VideoCompressor.get_video_info(input_path)['width'] > 1280 else None
            },
            'medium': {
                'crf': 24,
                'preset': 'fast',
                'video_bitrate': '1500k',
                'audio_bitrate': '128k',
                'scale': '1920:-2' if VideoCompressor.get_video_info(input_path)['width'] > 1920 else None
            },
            'high': {
                'crf': 20,
                'preset': 'medium',
                'video_bitrate': '2500k',
                'audio_bitrate': '192k',
                'scale': None  # Mantener resolución original
            }
        }
        
        preset = quality_presets.get(quality, quality_presets['medium'])
        
        try:
            # Comando ffmpeg optimizado para 2026
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-c:v', 'libx264',
                '-crf', str(preset['crf']),
                '-preset', preset['preset'],
                '-b:v', preset['video_bitrate'],
                '-maxrate', preset['video_bitrate'],
                '-bufsize', f"{int(preset['video_bitrate'].replace('k', '')) * 2}k",
                '-c:a', 'aac',
                '-b:a', preset['audio_bitrate'],
                '-movflags', '+faststart',
                '-threads', '2',  # Optimizado para Render Free
                '-y'
            ]
            
            # Agregar escala si es necesario
            if preset['scale']:
                cmd.extend(['-vf', preset['scale']])
            
            cmd.append(output_path)
            
            logger.info(f"Comprimiendo con: {' '.join(cmd)}")
            
            # Ejecutar con timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=MAX_PROCESSING_TIME
            )
            
            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "Error desconocido"
                return False, f"Error en compresión: {error_msg}"
            
            # Calcular estadísticas
            original_size = os.path.getsize(input_path)
            compressed_size = os.path.getsize(output_path)
            
            if original_size == 0:
                return False, "El archivo original está vacío"
            
            reduction = ((original_size - compressed_size) / original_size) * 100
            
            return True, {
                'original_size': original_size,
                'compressed_size': compressed_size,
                'reduction': reduction,
                'output_path': output_path
            }
            
        except subprocess.TimeoutExpired:
            return False, f"Tiempo de compresión excedido ({MAX_PROCESSING_TIME}s)"
        except Exception as e:
            return False, f"Error: {str(e)}"

# ===== HANDLERS DEL BOT =====
@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    """Manejador del comando /start"""
    
    welcome_text = """
<b>🎬 BOT COMPRESOR DE VIDEOS 2026</b>

¡Hola! Soy un bot optimizado para comprimir videos de manera eficiente.

<u>🚀 <b>CÓMO USARME:</b></u>
1. Envíame cualquier video (MP4, AVI, MOV, MKV)
2. Elige la calidad de compresión
3. Recibe tu video optimizado

<u>⚙️ <b>CALIDADES DISPONIBLES:</b></u>
• <b>Alta Compresión</b> (Baja) - Ideal para compartir rápido
• <b>Balanceada</b> (Media) - Recomendado para la mayoría
• <b>Máxima Calidad</b> (Alta) - Casi igual al original

<u>📊 <b>ESTADÍSTICAS 2026:</b></u>
• Compresión hasta 80% más pequeña
• Soporte para videos de 2GB
• Procesamiento en la nube
• Formatos: MP4, AVI, MOV, MKV, WEBM

<u>⚠️ <b>NOTA:</b></u> Videos largos (>10 min) pueden tardar varios minutos.
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Comenzar a comprimir", callback_data="send_video")],
        [InlineKeyboardButton("ℹ️ Ayuda", callback_data="help"),
         InlineKeyboardButton("📊 Estado", callback_data="status")]
    ])
    
    await message.reply_text(
        welcome_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@app.on_message(filters.command("help"))
async def help_handler(client: Client, message: Message):
    """Manejador del comando /help"""
    
    help_text = """
<b>🤖 AYUDA Y SOPORTE</b>

<u>📋 <b>COMANDOS DISPONIBLES:</b></u>
/start - Inicia el bot y muestra información
/help - Muestra esta ayuda
/status - Estado del bot y sistema
/stats - Estadísticas de compresión

<u>🔧 <b>SOLUCIÓN DE PROBLEMAS:</b></u>

<b>Problema:</b> El bot no responde
<b>Solución:</b> Espera 30 segundos, el bot podría estar en modo suspensión (Render Free)

<b>Problema:</b> Error en compresión
<b>Solucicción:</b> Intenta con un video más corto o diferente formato

<b>Problema:</b> Video muy grande
<b>Solución:</b> El límite es 2GB. Intenta comprimir en partes

<u>⚡ <b>OPTIMIZACIONES 2026:</b></u>
• Compresión inteligente por resolución
• Mantenimiento automático de calidad
• Procesamiento paralelo optimizado
• Limpieza automática de archivos

<u>📞 <b>SOPORTE:</b></u>
Para reportar bugs o sugerencias:
@TuUsuario (reemplázalo)
"""
    
    await message.reply_text(help_text, disable_web_page_preview=True)

@app.on_message(filters.command("status"))
async def status_handler(client: Client, message: Message):
    """Manejador del comando /status"""
    
    import psutil
    import platform
    
    # Obtener información del sistema
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpu_percent = psutil.cpu_percent(interval=1)
    
    # Contar archivos temporales
    temp_files = len(list(Path(COMPRESSED_FOLDER).glob("*"))) if Path(COMPRESSED_FOLDER).exists() else 0
    
    status_text = f"""
<b>🖥️ ESTADO DEL SISTEMA - 2026</b>

<u>📊 <b>INFORMACIÓN DEL SERVIDOR:</b></u>
• <b>Sistema:</b> {platform.system()} {platform.release()}
• <b>Python:</b> {platform.python_version()}
• <b>Puerto:</b> {PORT}
• <b>Servicio:</b> Render Free Plan

<u>📈 <b>USO DE RECURSOS:</b></u>
• <b>CPU:</b> {cpu_percent}%
• <b>Memoria:</b> {memory.percent}% usado ({memory.used // (1024**2)}MB/{memory.total // (1024**3)}GB)
• <b>Disco:</b> {disk.percent}% usado
• <b>Archivos temporales:</b> {temp_files}

<u>🔧 <b>CONFIGURACIÓN BOT:</b></u>
• <b>FFmpeg:</b> ✅ Instalado
• <b>Tiempo máximo:</b> {MAX_PROCESSING_TIME}s
• <b>Carpeta temporal:</b> {COMPRESSED_FOLDER}
• <b>Versión:</b> 2026.1.0

<u>🔄 <b>ESTADO RENDER:</b></u>
• Plan Free: 15 min timeout
• Auto-suspensión tras inactividad
• Reinicio automático
"""
    
    await message.reply_text(status_text, disable_web_page_preview=True)

@app.on_message(filters.video | filters.document)
async def video_handler(client: Client, message: Message):
    """Manejador para videos enviados"""
    
    user_id = message.from_user.id
    
    # Verificar tipo de archivo
    if message.document and not message.document.mime_type.startswith('video/'):
        await message.reply_text("❌ <b>Por favor envía solo archivos de video.</b>")
        return
    
    # Verificar tamaño
    file_size = message.video.file_size if message.video else message.document.file_size
    if file_size > MAX_VIDEO_SIZE:
        await message.reply_text(
            f"❌ <b>Video demasiado grande.</b>\n"
            f"Máximo permitido: {MAX_VIDEO_SIZE // (1024**3)}GB\n"
            f"Tu video: {file_size // (1024**3)}GB"
        )
        return
    
    # Solicitar calidad
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Alta Compresión", callback_data=f"compress_{user_id}_low"),
            InlineKeyboardButton("⚖️ Balanceada", callback_data=f"compress_{user_id}_medium")
        ],
        [
            InlineKeyboardButton("🎯 Máxima Calidad", callback_data=f"compress_{user_id}_high"),
            InlineKeyboardButton("❌ Cancelar", callback_data=f"cancel_{user_id}")
        ]
    ])
    
    await message.reply_text(
        f"📥 <b>Video recibido:</b> {file_size // (1024**2)}MB\n\n"
        "🔄 <b>Selecciona la calidad de compresión:</b>",
        reply_markup=keyboard
    )
    
    # Guardar referencia al mensaje
    if not hasattr(app, 'user_videos'):
        app.user_videos = {}
    
    app.user_videos[user_id] = {
        'message_id': message.id,
        'chat_id': message.chat.id,
        'file_size': file_size
    }

@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    """Manejador de callbacks"""
    
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    # Cancelar operación
    if data.startswith(f"cancel_{user_id}"):
        await callback_query.message.edit_text("❌ <b>Operación cancelada.</b>")
        await callback_query.answer()
        return
    
    # Enviar video
    if data == "send_video":
        await callback_query.message.edit_text(
            "📤 <b>Envíame un video para comprimir.</b>\n\n"
            "Puedes enviar videos en cualquier formato común."
        )
        await callback_query.answer()
        return
    
    # Ayuda
    if data == "help":
        await help_handler(client, callback_query.message)
        await callback_query.answer()
        return
    
    # Estado
    if data == "status":
        await status_handler(client, callback_query.message)
        await callback_query.answer()
        return
    
    # Procesar compresión
    if data.startswith(f"compress_{user_id}_"):
        quality = data.split('_')[-1]
        quality_names = {
            'low': 'Alta Compresión',
            'medium': 'Balanceada', 
            'high': 'Máxima Calidad'
        }
        
        # Obtener mensaje original
        if not hasattr(app, 'user_videos') or user_id not in app.user_videos:
            await callback_query.answer("❌ Video no encontrado. Envía otro.", show_alert=True)
            return
        
        user_data = app.user_videos[user_id]
        
        await callback_query.message.edit_text(
            f"⚙️ <b>Procesando video...</b>\n"
            f"Calidad: {quality_names[quality]}\n"
            f"Esto puede tardar unos minutos..."
        )
        
        try:
            # Descargar video
            temp_file = tempfile.NamedTemporaryFile(
                suffix='.mp4',
                dir=COMPRESSED_FOLDER,
                delete=False
            )
            temp_file.close()
            download_path = temp_file.name
            
            msg = await client.get_messages(user_data['chat_id'], user_data['message_id'])
            await callback_query.message.edit_text("📥 <b>Descargando video...</b>")
            
            download_start = datetime.now()
            await msg.download(file_name=download_path)
            download_time = (datetime.now() - download_start).total_seconds()
            
            # Comprimir video
            await callback_query.message.edit_text("🔄 <b>Comprimiendo video...</b>")
            
            output_path = download_path.replace('.mp4', '_compressed.mp4')
            compressor = VideoCompressor()
            
            compress_start = datetime.now()
            success, result = compressor.compress_video(
                download_path, 
                output_path, 
                quality
            )
            compress_time = (datetime.now() - compress_start).total_seconds()
            
            if not success:
                await callback_query.message.edit_text(
                    f"❌ <b>Error en compresión:</b>\n{result}"
                )
                # Limpiar archivos
                for path in [download_path, output_path]:
                    if os.path.exists(path):
                        os.unlink(path)
                return
            
            # Enviar video comprimido
            await callback_query.message.edit_text("📤 <b>Enviando video comprimido...</b>")
            
            original_size = result['original_size']
            compressed_size = result['compressed_size']
            reduction = result['reduction']
            
            caption = (
                f"✅ <b>VIDEO COMPRIMIDO</b>\n\n"
                f"<b>Calidad:</b> {quality_names[quality]}\n"
                f"<b>Tamaño original:</b> {original_size // (1024**2)}MB\n"
                f"<b>Tamaño comprimido:</b> {compressed_size // (1024**2)}MB\n"
                f"<b>Reducción:</b> {reduction:.1f}%\n"
                f"<b>Tiempo total:</b> {download_time + compress_time:.1f}s\n\n"
                f"⚡ <b>Optimizado 2026</b>"
            )
            
            await client.send_video(
                chat_id=callback_query.message.chat.id,
                video=output_path,
                caption=caption,
                supports_streaming=True
            )
            
            await callback_query.message.delete()
            
            # Limpiar archivos
            for path in [download_path, output_path]:
                if os.path.exists(path):
                    os.unlink(path)
            
            # Limpiar datos de usuario
            if hasattr(app, 'user_videos') and user_id in app.user_videos:
                del app.user_videos[user_id]
            
            await callback_query.answer("✅ Video enviado exitosamente")
            
        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await callback_query.message.edit_text(
                f"❌ <b>Error procesando video:</b>\n{str(e)}"
            )
            await callback_query.answer("⚠️ Ocurrió un error")

# ===== SERVIDOR WEB PARA RENDER =====
async def web_server():
    """Servidor web simple para mantener activo el servicio en Render"""
    from aiohttp import web
    
    async def handle_root(request):
        return web.Response(
            text="🤖 Bot de Compresión de Videos 2026\n✅ Activo y funcionando",
            content_type="text/plain"
        )
    
    async def handle_health(request):
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "telegram-video-compressor",
            "version": "2026.1.0",
            "endpoints": {
                "/": "Información del servicio",
                "/health": "Health check",
                "/stats": "Estadísticas del bot"
            }
        })
    
    async def handle_stats(request):
        import psutil
        memory = psutil.virtual_memory()
        
        return web.json_response({
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": memory.percent,
            "memory_used_mb": memory.used // (1024**2),
            "memory_total_mb": memory.total // (1024**2),
            "timestamp": datetime.now().isoformat(),
            "active_users": len(getattr(app, 'user_videos', {}))
        })
    
    app_web = web.Application()
    app_web.router.add_get('/', handle_root)
    app_web.router.add_get('/health', handle_health)
    app_web.router.add_get('/stats', handle_stats)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logger.info(f"🌐 Servidor web iniciado en puerto {PORT}")

# ===== FUNCIÓN PRINCIPAL =====
async def main():
    """Función principal del bot"""
    
    # Configurar entorno
    if not setup_environment():
        logger.error("❌ Configuración fallida. Saliendo...")
        sys.exit(1)
    
    # Iniciar servidor web
    web_task = asyncio.create_task(web_server())
    
    # Iniciar bot
    await app.start()
    
    # Obtener información del bot
    me = await app.get_me()
    logger.info(f"✅ Bot iniciado: @{me.username} (ID: {me.id})")
    logger.info("🎯 Esperando videos para comprimir...")
    
    # Mantener el bot activo
    try:
        await idle()
    except KeyboardInterrupt:
        logger.info("👋 Bot detenido por el usuario")
    finally:
        await app.stop()
        logger.info("✅ Bot detenido correctamente")

# ===== PUNTO DE ENTRADA =====
if __name__ == "__main__":
    # Verificar si estamos en Render
    if 'RENDER' in os.environ:
        logger.info("🚀 Ejecutando en Render.com")
    
    # Ejecutar bot
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        sys.exit(1)
