import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import subprocess
import time
import json 
import sys
import threading
import ffmpeg
from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración del bot desde variables de entorno
API_ID = os.getenv('API_ID', '20534584')
API_HASH = os.getenv('API_HASH', '6d5b13261d2c92a9a00afc1fd613b9df')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8562042457:AAGA__pfWDMVfdslzqwnoFl4yLrAre-HJ5I')

# Lista de administradores supremos (IDs de usuario)
SUPER_ADMINS = [7363341763]  # Reemplaza con los IDs de los administradores supremos

# Lista de administradores (IDs de usuario)
ADMINS = []  # Reemplaza con los IDs de los administradores

# Lista de usuarios autorizados (IDs de usuario)
AUTHORIZED_USERS = []

# Lista de grupos autorizados (IDs de grupo)
AUTHORIZED_GROUPS = []

# Calidad predeterminada
DEFAULT_QUALITY = {
    'resolution': '740x480',
    'crf': '32',
    'audio_bitrate': '60k',
    'fps': '28',
    'preset': 'ultrafast',
    'codec': 'libx265'
}

# Calidad actual (cambiar a un diccionario que almacene la calidad por usuario)
current_calidad = {}

# Límite de tamaño de video (en bytes)
max_video_size = 5 * 1024 * 1024 * 1024  # 5GB por defecto

# Configuración de logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicialización del bot
app = Client(
    "ffmpeg_bot", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    workdir="/app/session"
)

# Crear aplicación FastAPI para Render
web_app = FastAPI(title="Video Compressor Bot", version="1.0.0")

# Función para verificar si el usuario es un administrador supremo
def is_super_admin(user_id):
    return user_id in SUPER_ADMINS

# Función para verificar si el usuario es un administrador
def is_admin(user_id):
    return user_id in ADMINS or user_id in SUPER_ADMINS

# Función para verificar si el usuario es autorizado
def is_authorized(user_id):
    return user_id in AUTHORIZED_USERS or user_id in ADMINS or user_id in SUPER_ADMINS

# Función para verificar si el grupo es autorizado
def is_authorized_group(chat_id):
    if chat_id in AUTHORIZED_GROUPS:
        return True
    logger.info(f"❌ Grupo {chat_id} no autorizado ❌")
    return False

# Función para guardar los datos en un archivo JSON
def save_data():
    data = {
        'authorized_users': AUTHORIZED_USERS,
        'authorized_groups': AUTHORIZED_GROUPS,
        'admins': ADMINS,
        'super_admins': SUPER_ADMINS
    }
    with open('/app/data.json', 'w') as f:
        json.dump(data, f, indent=2)

# Función para cargar los datos desde un archivo JSON
def load_data():
    global AUTHORIZED_USERS, AUTHORIZED_GROUPS, ADMINS, SUPER_ADMINS
    try:
        with open('/app/data.json', 'r') as f:
            data = json.load(f)
            AUTHORIZED_USERS = data.get('authorized_users', [])
            AUTHORIZED_GROUPS = data.get('authorized_groups', [])
            ADMINS = data.get('admins', [])
            SUPER_ADMINS = data.get('super_admins', [])
        logger.info("✅ Datos cargados correctamente")
    except FileNotFoundError:
        logger.warning("📄 Archivo data.json no encontrado, usando valores por defecto")
        save_data()
    except Exception as e:
        logger.error(f"❌ Error al cargar datos: {e}")

# Cargar datos al iniciar el bot
load_data()

# Función para formatear el tiempo en HH:MM:SS
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# Función para comprimir el video
async def compress_video(input_file, output_file, user_id):
    # Obtener la calidad del usuario o usar la calidad predeterminada
    quality = current_calidad.get(user_id, DEFAULT_QUALITY)
    
    command = [
        'ffmpeg',
        '-i', input_file,
        '-vf', f'scale={quality["resolution"]},fps={quality["fps"]}',
        '-c:v', quality['codec'],
        '-crf', quality['crf'],
        '-preset', quality['preset'],
        '-b:a', quality['audio_bitrate'],
        '-threads', '0',  # Usar todos los hilos disponibles
        '-y', output_file
    ]
    
    logger.info(f"Ejecutando comando: {' '.join(command)}")
    
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Error desconocido"
        logger.error(f"‼️ Error en el proceso: {error_msg} ‼️")
    
    return process.returncode

# ===================== ENDPOINTS FASTAPI =====================

@web_app.get("/")
async def root():
    return {
        "status": "active", 
        "service": "Telegram Video Compressor Bot",
        "version": "3.0",
        "endpoints": {
            "root": "/",
            "health": "/health",
            "stats": "/stats",
            "docs": "/docs"
        }
    }

@web_app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "bot_status": "running" if app.is_initialized else "starting",
        "authorized_users": len(AUTHORIZED_USERS),
        "authorized_groups": len(AUTHORIZED_GROUPS)
    }

@web_app.get("/stats")
async def get_stats():
    return {
        "users": {
            "authorized": len(AUTHORIZED_USERS),
            "admins": len(ADMINS),
            "super_admins": len(SUPER_ADMINS)
        },
        "groups": {
            "authorized": len(AUTHORIZED_GROUPS)
        },
        "quality_settings": {
            "default": DEFAULT_QUALITY,
            "custom_settings": len(current_calidad)
        },
        "storage": {
            "max_video_size_gb": max_video_size / (1024**3),
            "session_exists": os.path.exists("/app/session")
        }
    }

@web_app.get("/ping")
async def ping():
    return {"message": "pong", "timestamp": time.time()}

# ===================== COMANDOS DEL BOT =====================

# Comando de bienvenida
@app.on_message(filters.command("start") & (filters.private | filters.group))
async def start(client: Client, message: Message):
    if is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        await message.reply_text(
            "😄 Bienvenido a Compresor Video 🎬\n\n"
            "Envía un video para comprimirlo o usa /help para ver todos los comandos disponibles."
        )
    else:
        await message.reply_text(
            "⛔ No tienes acceso a este bot ⛔\n\n"
            "Contacta con el administrador para solicitar acceso.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👨‍💻 Desarrollador", url="https://t.me/Sasuke286")]
            ])
        )

# Comando de ayuda
@app.on_message(filters.command("help") & (filters.private | filters.group))
async def help(client: Client, message: Message):
    if is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        help_text = """
        **🤖 Comandos Disponibles:**

        **👤 Comandos de Usuario:**
        - **/start**: Muestra mensaje de bienvenida
        - **/help**: Muestra esta ayuda
        - **/calidad**: Cambia calidad de compresión
          Ej: `/calidad resolution=1280x720 crf=28 fps=30`
        - **/id**: Obtiene ID de usuario/grupo

        **👨‍✈️ Comandos de Administrador:**
        - **/add user_id**: Agrega usuario autorizado
        - **/ban user_id**: Quita usuario autorizado
        - **/listusers**: Lista usuarios autorizados
        - **/grup group_id**: Agrega grupo autorizado
        - **/bangrup group_id**: Quita grupo autorizado
        - **/listgrup**: Lista grupos autorizados
        - **/add_admins user_id**: Agrega administrador
        - **/ban_admins user_id**: Quita administrador
        - **/listadmins**: Lista administradores
        - **/info mensaje**: Envía mensaje global
        - **/max tamaño**: Establece límite de tamaño (ej: /max 2GB)

        **🔧 Configuración de Calidad:**
        - **resolution**: Ancho x Alto (ej: 1280x720)
        - **crf**: Calidad (18-32, menor es mejor)
        - **audio_bitrate**: Bitrate de audio (ej: 128k)
        - **fps**: Cuadros por segundo (ej: 30)
        - **preset**: ultrafast, fast, medium, slow
        - **codec**: libx264 o libx265

        **📖 Uso:**
        Simplemente envía un video y el bot lo comprimirá automáticamente.
        """
        await message.reply_text(help_text)
    else:
        await message.reply_text(
            "⛔ No tienes acceso ⛔",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👨‍💻 Desarrollador", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para listar administradores
@app.on_message(filters.command("listadmins") & (filters.private | filters.group))
async def list_admins(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        if ADMINS:
            admin_list = "\n".join([f"👨‍💻 {admin}" for admin in ADMINS])
            await message.reply_text(f"**📓 Lista de Administradores:**\n{admin_list}")
        else:
            await message.reply_text("⭕ No hay administradores registrados ⭕")
    else:
        await message.reply_text("⛔ Acceso denegado ⛔")

# Comando para cambiar calidad
@app.on_message(filters.command("calidad") & (filters.private | filters.group))
async def set_calidad(client: Client, message: Message):
    if is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        args = message.text.split()[1:]
        
        if not args:
            current = current_calidad.get(message.from_user.id, DEFAULT_QUALITY)
            quality_text = "\n".join([f"**{k}**: {v}" for k, v in current.items()])
            await message.reply_text(
                f"**⚙️ Calidad Actual:**\n{quality_text}\n\n"
                "Para cambiar: `/calidad resolution=1280x720 crf=28 audio_bitrate=128k fps=30 preset=fast codec=libx265`"
            )
            return

        user_quality = current_calidad.get(message.from_user.id, DEFAULT_QUALITY.copy())
        errors = []
        
        for arg in args:
            if '=' not in arg:
                errors.append(f"Formato incorrecto: {arg}")
                continue
                
            key, value = arg.split('=', 1)
            if key in user_quality:
                user_quality[key] = value
            else:
                errors.append(f"Parámetro desconocido: {key}")

        if errors:
            await message.reply_text(f"❌ Errores:\n" + "\n".join(errors))
        else:
            current_calidad[message.from_user.id] = user_quality
            quality_text = "\n".join([f"**{k}**: {v}" for k, v in user_quality.items()])
            await message.reply_text(f"✅ **Calidad actualizada:**\n{quality_text}")
    else:
        await message.reply_text("⛔ Acceso denegado ⛔")

# Comando para agregar usuario
@app.on_message(filters.command("add") & (filters.private | filters.group))
async def add_user(client: Client, message: Message):
    if is_admin(message.from_user.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("❌ Uso: /add user_id")
            return

        results = []
        for user_id in args:
            try:
                user_id = int(user_id)
                if user_id not in AUTHORIZED_USERS:
                    AUTHORIZED_USERS.append(user_id)
                    save_data()
                    results.append(f"✅ Usuario {user_id} agregado")
                else:
                    results.append(f"⚠️ Usuario {user_id} ya existe")
            except ValueError:
                results.append(f"❌ ID inválido: {user_id}")

        await message.reply_text("\n".join(results))
    else:
        await message.reply_text("⛔ Solo administradores ⛔")

# Comando para quitar usuario
@app.on_message(filters.command("ban") & (filters.private | filters.group))
async def ban_user(client: Client, message: Message):
    if is_admin(message.from_user.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("❌ Uso: /ban user_id")
            return

        results = []
        for user_id in args:
            try:
                user_id = int(user_id)
                if user_id in AUTHORIZED_USERS:
                    AUTHORIZED_USERS.remove(user_id)
                    save_data()
                    results.append(f"✅ Usuario {user_id} eliminado")
                else:
                    results.append(f"⚠️ Usuario {user_id} no encontrado")
            except ValueError:
                results.append(f"❌ ID inválido: {user_id}")

        await message.reply_text("\n".join(results))
    else:
        await message.reply_text("⛔ Solo administradores ⛔")

# Comando para listar usuarios
@app.on_message(filters.command("listusers") & (filters.private | filters.group))
async def list_users(client: Client, message: Message):
    if is_admin(message.from_user.id):
        if AUTHORIZED_USERS:
            user_list = "\n".join([f"👤 {uid}" for uid in AUTHORIZED_USERS])
            await message.reply_text(f"**📘 Usuarios Autorizados ({len(AUTHORIZED_USERS)}):**\n{user_list}")
        else:
            await message.reply_text("📭 No hay usuarios autorizados")
    else:
        await message.reply_text("⛔ Solo administradores ⛔")

# Comando para agregar grupo
@app.on_message(filters.command("grup") & (filters.private | filters.group))
async def add_group(client: Client, message: Message):
    if is_admin(message.from_user.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("❌ Uso: /grup group_id")
            return

        results = []
        for group_id in args:
            try:
                group_id = int(group_id)
                if group_id not in AUTHORIZED_GROUPS:
                    AUTHORIZED_GROUPS.append(group_id)
                    save_data()
                    results.append(f"✅ Grupo {group_id} agregado")
                else:
                    results.append(f"⚠️ Grupo {group_id} ya existe")
            except ValueError:
                results.append(f"❌ ID inválido: {group_id}")

        await message.reply_text("\n".join(results))
    else:
        await message.reply_text("⛔ Solo administradores ⛔")

# Comando para quitar grupo
@app.on_message(filters.command("bangrup") & (filters.private | filters.group))
async def ban_group(client: Client, message: Message):
    if is_admin(message.from_user.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("❌ Uso: /bangrup group_id")
            return

        results = []
        for group_id in args:
            try:
                group_id = int(group_id)
                if group_id in AUTHORIZED_GROUPS:
                    AUTHORIZED_GROUPS.remove(group_id)
                    save_data()
                    results.append(f"✅ Grupo {group_id} eliminado")
                else:
                    results.append(f"⚠️ Grupo {group_id} no encontrado")
            except ValueError:
                results.append(f"❌ ID inválido: {group_id}")

        await message.reply_text("\n".join(results))
    else:
        await message.reply_text("⛔ Solo administradores ⛔")

# Comando para listar grupos
@app.on_message(filters.command("listgrup") & (filters.private | filters.group))
async def list_groups(client: Client, message: Message):
    if is_admin(message.from_user.id):
        if AUTHORIZED_GROUPS:
            group_list = "\n".join([f"👥 {gid}" for gid in AUTHORIZED_GROUPS])
            await message.reply_text(f"**📗 Grupos Autorizados ({len(AUTHORIZED_GROUPS)}):**\n{group_list}")
        else:
            await message.reply_text("📭 No hay grupos autorizados")
    else:
        await message.reply_text("⛔ Solo administradores ⛔")

# Comando para agregar administrador
@app.on_message(filters.command("add_admins") & filters.private)
async def add_admin(client: Client, message: Message):
    if is_super_admin(message.from_user.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("❌ Uso: /add_admins user_id")
            return

        results = []
        for user_id in args:
            try:
                user_id = int(user_id)
                if user_id not in ADMINS and user_id not in SUPER_ADMINS:
                    ADMINS.append(user_id)
                    save_data()
                    results.append(f"✅ Admin {user_id} agregado")
                else:
                    results.append(f"⚠️ Usuario {user_id} ya es admin")
            except ValueError:
                results.append(f"❌ ID inválido: {user_id}")

        await message.reply_text("\n".join(results))
    else:
        await message.reply_text("⛔ Solo super administradores ⛔")

# Comando para quitar administrador
@app.on_message(filters.command("ban_admins") & filters.private)
async def ban_admin(client: Client, message: Message):
    if is_super_admin(message.from_user.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("❌ Uso: /ban_admins user_id")
            return

        results = []
        for user_id in args:
            try:
                user_id = int(user_id)
                if user_id in ADMINS and user_id not in SUPER_ADMINS:
                    ADMINS.remove(user_id)
                    save_data()
                    results.append(f"✅ Admin {user_id} eliminado")
                else:
                    results.append(f"⚠️ Usuario {user_id} no es admin o es super admin")
            except ValueError:
                results.append(f"❌ ID inválido: {user_id}")

        await message.reply_text("\n".join(results))
    else:
        await message.reply_text("⛔ Solo super administradores ⛔")

# Comando para obtener ID
@app.on_message(filters.command("id") & (filters.private | filters.group))
async def get_id(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        await message.reply_text(
            f"**👤 Tu ID:** `{message.from_user.id}`\n"
            f"**👥 Chat ID:** `{message.chat.id}`"
        )
    else:
        await message.reply_text("⛔ Acceso denegado ⛔")

# Comando para enviar mensaje global
@app.on_message(filters.command("info") & filters.private)
async def send_info(client: Client, message: Message):
    if is_admin(message.from_user.id):
        args = message.text.split(None, 1)
        if len(args) == 1:
            await message.reply_text("❌ Uso: /info mensaje")
            return

        info_message = args[1]
        sent_count = 0
        error_count = 0

        # Enviar a usuarios
        for user_id in AUTHORIZED_USERS:
            try:
                await client.send_message(user_id, f"📢 **Anuncio Global:**\n\n{info_message}")
                sent_count += 1
                await asyncio.sleep(0.1)  # Pequeña pausa para evitar flood
            except Exception as e:
                logger.error(f"Error enviando a usuario {user_id}: {e}")
                error_count += 1

        # Enviar a grupos
        for group_id in AUTHORIZED_GROUPS:
            try:
                await client.send_message(group_id, f"📢 **Anuncio Global:**\n\n{info_message}")
                sent_count += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error enviando a grupo {group_id}: {e}")
                error_count += 1

        await message.reply_text(
            f"✅ Mensaje enviado:\n"
            f"• ✅ Éxitos: {sent_count}\n"
            f"• ❌ Fallos: {error_count}"
        )
    else:
        await message.reply_text("⛔ Solo administradores ⛔")

# Comando para cambiar límite de tamaño
@app.on_message(filters.command("max") & filters.private)
async def set_max_size(client: Client, message: Message):
    if is_admin(message.from_user.id):
        global max_video_size
        args = message.text.split(None, 1)
        if len(args) == 1:
            current_gb = max_video_size / (1024 * 1024 * 1024)
            await message.reply_text(f"📏 **Límite actual:** {current_gb:.2f} GB\n\nUso: /max 2GB o /max 500MB")
            return

        size = args[1].upper().strip()
        try:
            if size.endswith("GB"):
                size_gb = float(size[:-2])
                max_video_size = int(size_gb * 1024 * 1024 * 1024)
                await message.reply_text(f"✅ Límite cambiado a {size_gb} GB")
            elif size.endswith("MB"):
                size_mb = float(size[:-2])
                max_video_size = int(size_mb * 1024 * 1024)
                await message.reply_text(f"✅ Límite cambiado a {size_mb} MB")
            else:
                await message.reply_text("❌ Formato incorrecto. Usa MB o GB")
        except ValueError:
            await message.reply_text("❌ Número inválido")
    else:
        await message.reply_text("⛔ Solo administradores ⛔")

# Manejador de videos
@app.on_message(filters.video & (filters.private | filters.group))
async def handle_video(client: Client, message: Message):
    if not (is_authorized(message.from_user.id) or is_authorized_group(message.chat.id)):
        await message.reply_text("⛔ No autorizado ⛔")
        return

    # Verificar tamaño del video
    if message.video.file_size > max_video_size:
        max_gb = max_video_size / (1024 * 1024 * 1024)
        await message.reply_text(f"❌ Video demasiado grande. Máximo: {max_gb:.1f} GB")
        return

    await message.reply_text("📥 Descargando video...")

    # Preparar nombres de archivo
    file_name = message.video.file_name or f"{message.video.file_id}.mp4"
    base_name = os.path.splitext(file_name)[0]
    input_file = f"/app/downloads/{base_name}_input.mp4"
    output_file = f"/app/compressed/{base_name}_compressed.mkv"

    # Crear directorios si no existen
    os.makedirs("/app/downloads", exist_ok=True)
    os.makedirs("/app/compressed", exist_ok=True)

    try:
        # Descargar video
        download_msg = await message.reply_text("⬇️ Descargando... 0%")
        last_progress = 0
        
        def progress(current, total):
            nonlocal last_progress
            progress_percent = (current / total) * 100
            if progress_percent - last_progress >= 10:  # Actualizar cada 10%
                asyncio.create_task(download_msg.edit_text(f"⬇️ Descargando... {int(progress_percent)}%"))
                last_progress = progress_percent

        await message.download(file_name=input_file, progress=progress)
        await download_msg.edit_text("✅ Descarga completada\n⚙️ Comprimiendo video...")

        # Comprimir video
        start_time = time.time()
        return_code = await compress_video(input_file, output_file, message.from_user.id)
        processing_time = time.time() - start_time

        if return_code != 0:
            await message.reply_text("❌ Error al comprimir el video")
            return

        # Calcular estadísticas
        original_size = os.path.getsize(input_file)
        compressed_size = os.path.getsize(output_file)
        compression_ratio = (original_size - compressed_size) / original_size * 100

        # Enviar video comprimido
        await message.reply_text("📤 Subiendo video comprimido...")
        
        caption = (
            f"✅ **Video Comprimido**\n\n"
            f"📊 **Estadísticas:**\n"
            f"• 📏 Original: {original_size / (1024*1024):.2f} MB\n"
            f"• 📏 Comprimido: {compressed_size / (1024*1024):.2f} MB\n"
            f"• 📉 Compresión: {compression_ratio:.1f}%\n"
            f"• ⏱️ Tiempo: {processing_time:.1f}s\n"
            f"• 🎬 Duración: {format_time(message.video.duration)}"
        )

        await client.send_video(
            chat_id=message.chat.id,
            video=output_file,
            caption=caption,
            duration=message.video.duration,
            thumb=message.video.thumbs[0].file_id if message.video.thumbs else None
        )

    except Exception as e:
        logger.error(f"Error procesando video: {e}")
        await message.reply_text(f"❌ Error: {str(e)}")
    finally:
        # Limpiar archivos temporales
        try:
            if os.path.exists(input_file):
                os.remove(input_file)
            if os.path.exists(output_file):
                os.remove(output_file)
        except:
            pass

# Comando about
@app.on_message(filters.command("about") & (filters.private | filters.group))
async def about(client: Client, message: Message):
    about_text = (
        "🤖 **Video Compressor Bot**\n\n"
        "• 📱 **Versión:** 3.0\n"
        "• 👨‍💻 **Creador:** @Sasuke286\n"
        "• 🛠️ **Funciones:** Compresión de videos con FFmpeg\n"
        "• 🔧 **Soporte:** Contacta al desarrollador\n\n"
        "¡Gracias por usar el bot! 🎬"
    )
    await message.reply_text(about_text)

# ===================== INICIALIZACIÓN =====================

def run_telegram_bot():
    """Función para ejecutar el bot de Telegram"""
    logger.info("🤖 Iniciando bot de Telegram...")
    
    # Verificar credenciales
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.error("❌ Faltan credenciales de Telegram")
        return
    
    try:
        app.run()
        logger.info("✅ Bot de Telegram iniciado correctamente")
    except Exception as e:
        logger.error(f"❌ Error iniciando bot: {e}")

def run_fastapi_server():
    """Función para ejecutar el servidor FastAPI"""
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 Iniciando servidor web en puerto {port}...")
    
    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    # Crear directorios necesarios
    os.makedirs("/app/session", exist_ok=True)
    os.makedirs("/app/downloads", exist_ok=True)
    os.makedirs("/app/compressed", exist_ok=True)
    
    # Iniciar bot en hilo separado
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    # Iniciar servidor web (bloqueante)
    run_fastapi_server()
