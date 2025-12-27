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

# Configuración del bot
API_ID = '20534584'
API_HASH = '6d5b13261d2c92a9a00afc1fd613b9df'
BOT_TOKEN = '8562042457:AAGA__pfWDMVfdslzqwnoFl4yLrAre-HJ5I'

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
max_video_size = 5 * 1024 * 1024 * 1024  # 1GB por defecto

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Inicialización del bot
app = Client("ffmpeg_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workdir="/app/session")

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
    logger.info(f"❌𝐆𝐫𝐮𝐩𝐨 {chat_id} 𝐧𝐨 𝐚𝐮𝐭𝐨𝐫𝐢𝐳𝐚𝐝𝐨❌.")
    return False

# Función para guardar los datos en un archivo JSON
def save_data():
    data = {
        'authorized_users': AUTHORIZED_USERS,
        'authorized_groups': AUTHORIZED_GROUPS,
        'admins': ADMINS
    }
    with open('data.json', 'w') as f:
        json.dump(data, f)

# Función para cargar los datos desde un archivo JSON
def load_data():
    global AUTHORIZED_USERS, AUTHORIZED_GROUPS, ADMINS
    try:
        with open('data.json', 'r') as f:
            data = json.load(f)
            AUTHORIZED_USERS = data.get('authorized_users', [])
            AUTHORIZED_GROUPS = data.get('authorized_groups', [])
            ADMINS = data.get('admins', [])
    except FileNotFoundError:
        pass

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
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()  # Por si tiene error en la compresión
    if process.returncode != 0:
        logger.error(f"‼️𝐄𝐫𝐫𝐨𝐫 𝐞𝐧 𝐞𝐥 𝐩𝐫𝐨𝐜𝐞𝐬𝐨: {stderr.decode()}‼️")
    return process.returncode
    
# Comando de bienvenida
@app.on_message(filters.command("start") & (filters.private | filters.group))
async def start(client: Client, message: Message):
    if is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        await message.reply_text(
            "😄 Bienvenido a Compresor Video use /help para mas ayuda 📚"
        )
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando de ayuda
@app.on_message(filters.command("help") & (filters.private | filters.group))
async def help(client: Client, message: Message):
    if is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        help_text = """
        **🤖𝐂𝐨𝐦𝐚𝐧𝐝𝐨𝐬 𝐃𝐢𝐬𝐩𝐨𝐧𝐢𝐛𝐥𝐞𝐬🤖:**

        **👤𝐋𝐨𝐬 𝐝𝐞 𝐔𝐬𝐮𝐚𝐫𝐢𝐨👤:**
        - **/start**: Muestra un mensaje de bienvenida.
        - **/help**: Muestra esta lista de comandos.
        - **/calidad**: Cambia la calidad de compresión del video. Uso: `/calidad resolution=740x480 crf=32 audio_bitrate=60k fps=28 preset=ultrafast codec=libx265`
        - **/id**: Obtiene el ID de un usuario. Uso: `/id @username` (Solo Administradores)

        **👨‍✈️𝐋𝐨𝐬 𝐝𝐞 𝐚𝐝𝐦𝐢𝐧𝐢𝐬𝐭𝐫𝐚𝐝𝐨𝐫👨‍✈️:**
        - **/add**: Agrega un usuario autorizado. Uso: `/add user_id`
        - **/ban**: Quita un usuario autorizado. Uso: `/ban user_id`
        - **/listusers**: Lista los usuarios autorizados.
        - **/grup**: Agrega un grupo autorizado. Uso: `/grup group_id`
        - **/bangrup**: Quita un grupo autorizado. Uso: `/bangrup group_id`
        - **/listgrup**: Lista los grupos autorizados.
        - **/add_admins**: Agrega un nuevo administrador. Uso: `/add_admins user_id` (Solo Administradores Supremos)
        - **/ban_admins**: Quita un administrador. Uso: `/ban_admins user_id` (Solo Administradores Supremos)
        - **/listadmins**: Lista los administradores.
        - **/info**: Envia un mensaje a todos los usuarios y grupos autorizados. Uso: `/info [mensaje]`
        - **/max**: Establece el límite de tamaño para los videos. Uso: `/max [tamaño en MB o GB]`

        **𝐂𝐚𝐥𝐢𝐝𝐚𝐝 𝐩𝐫𝐞𝐝𝐞𝐭𝐞𝐫𝐦𝐢𝐧𝐚𝐝𝐚📔:**
        - resolution: 740x480
        - crf: 32
        - audio_bitrate: 60k
        - fps: 28
        - preset: ultrafast
        - codec: libx265

        **𝐔𝐬𝐨 𝐝𝐞𝐥 𝐛𝐨𝐭📖:**
        - Envía un video y el bot lo comprimirá con la calidad actual.
        """
        await message.reply_text(help_text)
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para listar administradores
@app.on_message(filters.command("listadmins") & (filters.private | filters.group))
async def list_admins(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        if ADMINS:
            admin_list = "\n".join(map(str, ADMINS))
            await message.reply_text(f"𝐋𝐢𝐬𝐭 𝐀𝐝𝐦𝐢𝐧𝐬 📓:\n{admin_list}")
        else:
            await message.reply_text("⭕𝐍𝐨 𝐡𝐚𝐲 𝐚𝐝𝐦𝐢𝐧⭕.")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )


@app.on_message(filters.command("calidad") & (filters.private | filters.group))
async def set_calidad(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        global current_calidad
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("𝐔𝐬𝐨: /calidad resolution=740x480 crf=32 audio_bitrate=60k fps=28 preset=ultrafast codec=libx265")
            return

        user_quality = current_calidad.get(message.from_user.id, DEFAULT_QUALITY.copy())
        for arg in args:
            try:
                key, value = arg.split('=')
                if key in user_quality:
                    user_quality[key] = value
                else:
                    await message.reply_text(f"⭕𝐏𝐚𝐫𝐚́𝐦𝐞𝐭𝐫𝐨 𝐝𝐞𝐬𝐜𝐨𝐧𝐨𝐜𝐢𝐝𝐨: {key}⭕")
                    return
            except ValueError:
                await message.reply_text(f"⭕𝐄𝐫𝐫𝐨𝐫 𝐫𝐞𝐩𝐢𝐭𝐚𝐧𝐝𝐨 𝐩𝐚𝐫𝐚́𝐦𝐞𝐭𝐫𝐨: {arg}⭕")
                return

        current_calidad[message.from_user.id] = user_quality
        await message.reply_text(f"‼️𝐂𝐚𝐥𝐢𝐝𝐚𝐝 𝐚𝐜𝐭𝐮𝐚𝐥: {current_calidad[message.from_user.id]}‼️")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para agregar un usuario autorizado
@app.on_message(filters.command("add") & (filters.private | filters.group))
async def add_user(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("𝐔𝐬𝐨: /add user_id")
            return

        for user_id in args:
            try:
                user_id = int(user_id)
                if user_id not in AUTHORIZED_USERS:
                    AUTHORIZED_USERS.append(user_id)
                    save_data()
                    await message.reply_text(f"✅𝐔𝐬𝐮𝐚𝐫𝐢𝐨 {user_id} 𝐚𝐠𝐠 𝐚 𝐥𝐚 𝐥𝐢𝐬𝐭𝐮𝐬𝐞𝐫✅.")
                else:
                    await message.reply_text(f"‼️𝐔𝐬𝐮𝐚𝐫𝐢𝐨 {user_id} 𝐲𝐚 𝐞𝐬𝐭𝐚 𝐞𝐧 𝐥𝐚 𝐥𝐢𝐬𝐭𝐮𝐬𝐞𝐫‼️.")
            except ValueError:
                await message.reply_text(f"⭕𝐈𝐃 𝐞𝐫𝐫𝐨𝐧𝐞𝐚: {user_id}⭕")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para quitar un usuario autorizado
@app.on_message(filters.command("ban") & (filters.private | filters.group))
async def ban_user(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("𝐔𝐬𝐨: /ban user_id")
            return

        for user_id in args:
            try:
                user_id = int(user_id)
                if user_id in AUTHORIZED_USERS:
                    AUTHORIZED_USERS.remove(user_id)
                    save_data()
                    await message.reply_text(f"✅𝐔𝐬𝐮𝐚𝐫𝐢𝐨 {user_id} 𝐫𝐞𝐦𝐨𝐯𝐢𝐝𝐨 𝐝𝐞 𝐥𝐚 𝐥𝐢𝐬𝐭𝐮𝐬𝐞𝐫✅.")
                else:
                    await message.reply_text(f"‼️𝐔𝐬𝐮𝐚𝐫𝐢𝐨 {user_id} 𝐧𝐨 𝐞𝐬𝐭𝐚 𝐞𝐧 𝐥𝐚 𝐥𝐢𝐬𝐭𝐮𝐬𝐞𝐫‼️.")
            except ValueError:
                await message.reply_text(f"⭕𝐈𝐃 𝐞𝐫𝐫𝐨𝐧𝐞𝐚: {user_id}⭕")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para listar usuarios autorizados
@app.on_message(filters.command("listusers") & (filters.private | filters.group))
async def list_users(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        if AUTHORIZED_USERS:
            user_list = "\n".join(map(str, AUTHORIZED_USERS))
            await message.reply_text(f"𝐋𝐢𝐬𝐭 𝐔𝐬𝐞𝐫 📘:\n{user_list}")
        else:
            await message.reply_text("❌𝐍𝐨 𝐡𝐚𝐲 𝐮𝐬𝐮𝐚𝐫𝐢𝐨𝐬 𝐚𝐮𝐭𝐨𝐫𝐢𝐳𝐚𝐝𝐨𝐬❌.")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para agregar un grupo autorizado
@app.on_message(filters.command("grup") & (filters.private | filters.group))
async def add_group(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("𝐔𝐬𝐨: /grup group_id")
            return

        for group_id in args:
            try:
                group_id = int(group_id)
                if group_id not in AUTHORIZED_GROUPS:
                    AUTHORIZED_GROUPS.append(group_id)
                    save_data()
                    await message.reply_text(f"✅𝐆𝐫𝐮𝐩𝐨 {group_id} 𝐚𝐠𝐠 𝐚 𝐥𝐚 𝐥𝐢𝐬𝐭 𝐠𝐫𝐮𝐩✅")
                else:
                    await message.reply_text(f"‼️𝐆𝐫𝐮𝐩𝐨 {group_id} 𝐲𝐚 𝐞𝐬𝐭𝐚 𝐞𝐧 𝐥𝐚 𝐥𝐢𝐬𝐭 𝐠𝐫𝐮𝐩‼️.")
            except ValueError:
                await message.reply_text(f"⭕𝐈𝐃 𝐞𝐫𝐫𝐨𝐧𝐞𝐚: {group_id}⭕")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para quitar un grupo autorizado
@app.on_message(filters.command("bangrup") & (filters.private | filters.group))
async def ban_group(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("𝐔𝐬𝐨: /bangrup group_id")
            return

        for group_id in args:
            try:
                group_id = int(group_id)
                if group_id in AUTHORIZED_GROUPS:
                    AUTHORIZED_GROUPS.remove(group_id)
                    save_data()
                    await message.reply_text(f"✅𝐆𝐫𝐮𝐩𝐨 {group_id} 𝐫𝐞𝐦𝐨𝐯𝐢𝐝𝐨 𝐝𝐞 𝐥𝐚 𝐥𝐢𝐬𝐭 𝐠𝐫𝐮𝐩✅.")
                else:
                    await message.reply_text(f"‼️𝐆𝐫𝐮𝐩𝐨 {group_id} 𝐧𝐨 𝐞𝐬𝐭𝐚 𝐞𝐧 𝐥𝐚 𝐥𝐢𝐬𝐭 𝐠𝐫𝐮𝐩‼️.")
            except ValueError:
                await message.reply_text(f"⭕𝐈𝐃 𝐞𝐫𝐫𝐨𝐧𝐞𝐚: {group_id}⭕")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para listar grupos autorizados
@app.on_message(filters.command("listgrup") & (filters.private | filters.group))
async def list_groups(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        if AUTHORIZED_GROUPS:
            group_list = "\n".join(map(str, AUTHORIZED_GROUPS))
            await message.reply_text(f"𝐋𝐢𝐬𝐭 𝐠𝐫𝐮𝐩 📗:\n{group_list}")
        else:
            await message.reply_text("❌𝐍𝐨 𝐡𝐚𝐲 𝐠𝐫𝐮𝐩𝐨𝐬 𝐚𝐮𝐭𝐨𝐫𝐢𝐳𝐚𝐝𝐨𝐬❌.")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜??𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para agregar un administrador
@app.on_message(filters.command("add_admins") & filters.private)
async def add_admin(client: Client, message: Message):
    if is_super_admin(message.from_user.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("𝐔𝐬𝐞: /add_admins user_id")
            return

        for user_id in args:
            try:
                user_id = int(user_id)
                if user_id not in ADMINS and user_id not in SUPER_ADMINS:
                    ADMINS.append(user_id)
                    save_data()
                    await message.reply_text(f"✅𝐔𝐬𝐮𝐚𝐫𝐢𝐨 {user_id} 𝐚𝐠𝐠 𝐚 𝐥𝐚 𝐥𝐢𝐬𝐭 𝐚𝐝𝐦𝐢𝐧𝐬✅.")
                else:
                    await message.reply_text(f"‼️𝐔𝐬𝐮𝐚𝐫𝐢𝐨 {user_id} 𝐲𝐚 𝐞𝐬 𝐚𝐝𝐦𝐢𝐧‼️.")
            except ValueError:
                await message.reply_text(f"⭕𝐈𝐃 𝐞𝐫𝐫𝐨𝐧𝐞𝐚: {user_id}⭕")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para quitar un administrador
@app.on_message(filters.command("ban_admins") & filters.private)
async def ban_admin(client: Client, message: Message):
    if is_super_admin(message.from_user.id):
        args = message.text.split()[1:]
        if not args:
            await message.reply_text("𝐔𝐬𝐞: /ban_admins user_id")
            return

        for user_id in args:
            try:
                user_id = int(user_id)
                if user_id in ADMINS and user_id not in SUPER_ADMINS:
                    ADMINS.remove(user_id)
                    save_data()
                    await message.reply_text(f"✅𝐔𝐬𝐮𝐚𝐫𝐢𝐨 {user_id} 𝐫𝐞𝐦𝐨𝐯𝐢𝐝𝐨 𝐝𝐞 𝐥𝐚 𝐥𝐢𝐬𝐭 𝐚𝐝𝐦𝐢𝐧𝐬✅.")
                else:
                    await message.reply_text(f"‼️𝐔𝐬𝐮𝐚𝐫𝐢𝐨 {user_id} 𝐧𝐨 𝐞𝐬 𝐚𝐝𝐦𝐢𝐧‼️.")
            except ValueError:
                await message.reply_text(f"⭕𝐈𝐃 𝐞𝐫𝐫𝐨𝐧𝐞𝐚: {user_id}⭕")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para obtener el ID de un usuario
@app.on_message(filters.command("id") & (filters.private | filters.group))
async def get_id(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        if len(message.command) == 1:
            await message.reply_text(f"𝐓𝐮 𝐈𝐃: {message.from_user.id}")
        else:
            username = message.command[1]
            user = await client.get_users(username)
            await message.reply_text(f"𝐈𝐃 𝐝𝐞 @{user.username}: {user.id}")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para Enviar un Mensaje a Todos los Usuarios y Grupos Autorizados
@app.on_message(filters.command("info") & filters.private)
async def send_info(client: Client, message: Message):
    if is_admin(message.from_user.id):
        args = message.text.split(None, 1)
        if len(args) == 1:
            await message.reply_text("𝐔𝐬𝐞: /info [mensaje]")
            return

        info_message = args[1]

        # Enviar mensaje a todos los usuarios autorizados
        for user_id in AUTHORIZED_USERS:
            try:
                await client.send_message(user_id, info_message)
            except Exception as e:
                logger.error(f"⭕𝐄𝐫𝐫𝐨𝐫 𝐚𝐥 𝐞𝐧𝐯𝐢𝐚𝐫 𝐦𝐞𝐧𝐬𝐚𝐣𝐞 𝐚 𝐮𝐬𝐮𝐚𝐫𝐢𝐨 {user_id}: {e}⭕")

        # Enviar mensaje a todos los grupos autorizados
        for group_id in AUTHORIZED_GROUPS:
            try:
                await client.send_message(group_id, info_message)
            except Exception as e:
                logger.error(f"⭕𝐄𝐫𝐫𝐨𝐫 𝐚𝐥 𝐞𝐧𝐯𝐢𝐚𝐫 𝐦𝐞𝐧𝐬𝐚𝐣𝐞 𝐚 𝐠𝐫𝐮𝐩𝐨 {group_id}: {e}⭕")

        await message.reply_text("✅𝐌𝐞𝐧𝐬𝐚𝐣𝐞 𝐠𝐥𝐨𝐛𝐚𝐥 𝐞𝐧𝐯𝐢𝐚𝐝𝐨 𝐜𝐨𝐫𝐫𝐞𝐜𝐭𝐚𝐦𝐞𝐧𝐭𝐞✅.")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Comando para cambiar el límite de tamaño de video
@app.on_message(filters.command("max") & filters.private)
async def set_max_size(client: Client, message: Message):
    if is_admin(message.from_user.id):
        args = message.text.split(None, 1)
        if len(args) == 1:
            await message.reply_text("𝐔𝐬𝐞: /max [tamaño en MB o GB]")
            return

        size = args[1].upper()
        if size.endswith("GB"):
            try:
                size_gb = int(size[:-2])
                max_video_size = size_gb * 1024 * 1024 * 1024
            except ValueError:
                await message.reply_text("❌𝐄𝐫𝐫𝐨𝐫 𝐮𝐬𝐞 𝐮𝐧𝐚 𝐜𝐢𝐟𝐫𝐚 𝐲 𝐝𝐞𝐬𝐩𝐮𝐞𝐬 'GB'❌")
                return
        elif size.endswith("MB"):
            try:
                size_mb = int(size[:-2])
                max_video_size = size_mb * 1024 * 1024
            except ValueError:
                await message.reply_text("❌𝐄𝐫𝐫𝐨𝐫 𝐮𝐬𝐞 𝐮𝐧𝐚 𝐜𝐢𝐟𝐫𝐚 𝐲 𝐝𝐞𝐬𝐩𝐮𝐞𝐬 'MB'❌")
                return
        else:
            await message.reply_text("❌𝐄𝐫𝐫𝐨𝐫 𝐮𝐬𝐞 𝐮𝐧𝐚 𝐜𝐢𝐟𝐫𝐚 𝐲 𝐝𝐞𝐬𝐩𝐮𝐞𝐬 'MB' 𝐨 'GB'❌")
            return

        await message.reply_text(f"✅𝐋𝐢𝐦𝐢𝐭𝐞 𝐜𝐚𝐦𝐛𝐢𝐚𝐝𝐨 𝐚 {size}✅.")
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )

# Manejador de videos
@app.on_message(filters.video & (filters.private | filters.group))
async def handle_video(client: Client, message: Message):
    if is_admin(message.from_user.id) or is_authorized(message.from_user.id) or is_authorized_group(message.chat.id):
        await message.reply_text("📤𝐃𝐞𝐬𝐜𝐚𝐫𝐠𝐚𝐧𝐝𝐨 𝐕𝐢𝐝𝐞𝐨📥")

        # Extraer el nombre del archivo original
        file_name = message.video.file_name
        if not file_name:
            file_name = f"{message.video.file_id}.mkv"  # Usar el file_id como nombre por defecto si no hay nombre
        else:
             # Cambiar la extensión del archivo a .mkv
             base_name, _ = os.path.splitext(file_name)
             file_name = f"{base_name}.mkv"

        # Descargar el video
        input_file = f"downloads/{file_name}"
        os.makedirs("downloads", exist_ok=True)
        try:
            await message.download(file_name=input_file)
        except Exception as e:
            logger.error(f"⭕𝐄𝐫𝐫𝐨𝐫 𝐚𝐥 𝐝𝐞𝐬𝐜𝐚𝐫𝐠𝐚𝐫 𝐞𝐥 𝐯𝐢𝐝𝐞𝐨: {e}⭕")
            await message.reply_text("⭕𝐄𝐫𝐫𝐨𝐫 𝐚𝐥 𝐝𝐞𝐬𝐜𝐚𝐫𝐠𝐚𝐫 𝐞𝐥 𝐯𝐢𝐝𝐞𝐨⭕.")
            return

        # Obtener el tamaño del video original
        original_size = os.path.getsize(input_file)

        # Verificar si el video excede el límite de tamaño
        if original_size > max_video_size:
            await message.reply_text(f"⛔𝐄𝐬𝐭𝐞 𝐯𝐢𝐝𝐞𝐨 𝐞𝐱𝐞𝐝𝐞 𝐞𝐥 𝐥𝐢𝐦𝐢??𝐞 𝐝𝐞 {max_video_size / (1024 * 1024 * 1024):.2f}𝐌𝐁⛔")
            os.remove(input_file)
            return

        # Comprimir el video
        output_file = f"compressed/{file_name}"
        os.makedirs("compressed", exist_ok=True)
        start_time = time.time()
        await message.reply_text("𝐂𝐨𝐧𝐯𝐢𝐫𝐭𝐢𝐞𝐧𝐝𝐨 𝐕𝐢𝐝𝐞𝐨📹")
        returncode = await compress_video(input_file, output_file, message.from_user.id)
        end_time = time.time()

        if returncode != 0:
            await message.reply_text("⭕𝐄𝐫𝐫𝐨𝐫 𝐚𝐥 𝐜𝐨𝐧𝐯𝐞𝐫𝐭𝐢𝐫⭕.")
        else:
            # Obtener el tamaño del video procesado
            processed_size = os.path.getsize(output_file)
            processing_time = end_time - start_time
            video_duration = message.video.duration

            # Formatear los tiempos
            processing_time_formatted = format_time(processing_time)
            video_duration_formatted = format_time(video_duration)

            # Crear la descripción
            description = f"""
            ꧁༺ 𝙋𝙧𝙤𝙘𝙚𝙨𝙤 𝙩𝙚𝙧𝙢𝙞𝙣𝙖𝙙𝙤 𝙘𝙤𝙧𝙧𝙚𝙘𝙩𝙖𝙢𝙚𝙣𝙩𝙚 ༻꧂\n
×͡× 𝐏𝐞𝐬𝐨 𝐨𝐫𝐢𝐠𝐢𝐧𝐚𝐥: {original_size / (1024 * 1024):.2f} MB
×͜× 𝐏𝐞𝐬𝐨 𝐩𝐫𝐨𝐜𝐞𝐬𝐚𝐝𝐨: {processed_size / (1024 * 1024):.2f} MB
✯ 𝐓𝐢𝐞𝐦𝐩𝐨 𝐝𝐞 𝐩𝐫𝐨𝐜𝐞𝐬𝐚𝐦𝐢𝐞𝐧𝐭𝐨: {processing_time_formatted}
𖤍 𝐓𝐢𝐞𝐦𝐩𝐨 𝐝𝐞𝐥 𝐯𝐢𝐝𝐞𝐨: {video_duration_formatted}
♠ ¡𝐐𝐮𝐞 𝐥𝐨 𝐝𝐢𝐬𝐟𝐫𝐮𝐭𝐞𝐬!♣
            """
            # Subir el video comprimido
            try:
                await client.send_video(message.chat.id, output_file, caption=description)
            except Exception as e:
                logger.error(f"⭕𝐄𝐫𝐫𝐨𝐫 𝐚𝐥 𝐬𝐮𝐛𝐢𝐫 𝐞𝐥 𝐯𝐢𝐝𝐞𝐨: {e}⭕")
                await message.reply_text("⭕𝐄𝐫𝐫𝐨𝐫 𝐚𝐥 𝐬𝐮𝐛𝐢𝐫 𝐞𝐥 𝐕𝐢𝐝𝐞𝐨⭕.")
            finally:
                os.remove(input_file)
                os.remove(output_file)
    else:
        await message.reply_text(
            "⛔𝐍𝐨 𝐩𝐨𝐬𝐞𝐞 𝐚𝐜𝐜𝐞𝐬𝐨⛔\n\n𝐇𝐚𝐛𝐥𝐞 𝐜𝐨𝐧 𝐞𝐥 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐚𝐝𝐨𝐫 👨‍💻", url="https://t.me/Sasuke286")]
            ])
        )
        
# Comando para mostrar información del bot
@app.on_message(filters.command("about") & (filters.private | filters.group))
async def about(client: Client, message: Message):
    bot_version = "𝐕.3"
    bot_creator = "@Sasuke286"
    bot_creation_date = "14/11/24"

    about_text = f"🤖 **𝐀𝐜𝐞𝐫𝐜𝐚 𝐝𝐞𝐥 𝐁𝐨𝐭:**\n\n" \
                 f" - 📔𝐕𝐞𝐫𝐬𝐢𝐨𝐧: {bot_version}\n" \
                 f" - 👨‍💻𝐂𝐫𝐞𝐚𝐝𝐨𝐫: {bot_creator}\n" \
                 f" - 📅𝐅𝐞𝐜𝐡𝐚 𝐝𝐞 𝐃𝐞𝐬𝐚𝐫𝐫𝐨𝐥𝐥𝐨: {bot_creation_date}\n" \
                 f" - 🔆𝐅𝐮𝐧𝐜𝐢𝐨𝐧𝐞𝐬: 𝐂𝐨𝐧𝐯𝐞𝐫𝐭𝐢𝐫 𝐯𝐢𝐝𝐞𝐨𝐬.\n\n" \
                 f"¡𝐄𝐬𝐩𝐞𝐫𝐨 𝐭𝐞 𝐠𝐮𝐬𝐭𝐞! 🤗"

    await message.reply_text(about_text)

app.run()
