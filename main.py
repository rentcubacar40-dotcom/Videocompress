#!/usr/bin/env python3
"""
Bot de Compresión de Videos para Telegram
Autor: @tu_usuario
Requerimientos:
- pyrogram==2.0.106
- ffmpeg-python==0.2.0
- async-timeout==4.0.3
- python-dotenv==1.0.0
- tgcrypto==1.2.5
"""

import os
import asyncio
import shutil
import subprocess
import time
from datetime import datetime
from typing import Tuple, Dict, Optional
from dotenv import load_dotenv

import ffmpeg
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    CallbackQuery
)
from pyrogram.enums import ParseMode, MessageMediaType

# Cargar variables de entorno
load_dotenv()

# ==================== CONFIGURACIÓN ====================
class Config:
    # Credenciales de la API de Telegram
    API_ID = int(os.getenv("API_ID", 123456))
    API_HASH = os.getenv("API_HASH", "tu_api_hash")
    BOT_TOKEN = os.getenv("BOT_TOKEN", "tu_bot_token")
    
    # Configuración de compresión
    COMPRESSION_SETTINGS = {
        'crf': 28,                    # Calidad (18-28 recomendado)
        'preset': 'medium',           # Velocidad de compresión
        'audio_bitrate': '128k',      # Bitrate de audio
        'video_bitrate': '1000k',     # Bitrate de video
        'max_size_mb': 50,            # Tamaño máximo en MB
        'output_format': 'mp4'        # Formato de salida
    }
    
    # Directorios
    DOWNLOAD_DIR = "downloads"
    UPLOAD_DIR = "uploads"
    TEMP_DIR = "temp"
    
    # Configuración del bot
    MAX_CONCURRENT_JOBS = 3           # Máximo de compresiones simultáneas
    ALLOWED_USERS = []                # Lista de IDs permitidos (vacío = todos)
    
    # Tiempos de espera
    DOWNLOAD_TIMEOUT = 300            # 5 minutos para descarga
    COMPRESSION_TIMEOUT = 1800        # 30 minutos para compresión

# Crear directorios necesarios
for directory in [Config.DOWNLOAD_DIR, Config.UPLOAD_DIR, Config.TEMP_DIR]:
    os.makedirs(directory, exist_ok=True)

# ==================== COMPRESOR DE VIDEOS ====================
class VideoCompressor:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self.is_cancelled = False
        self.current_progress = 0.0
        
    async def compress_video(
        self,
        input_path: str,
        output_path: str,
        crf: int = 28,
        preset: str = 'medium',
        audio_bitrate: str = '128k',
        video_bitrate: str = '1000k',
        max_size_mb: int = 50
    ) -> Tuple[bool, str, float]:
        """
        Comprime un video usando FFmpeg con monitoreo de progreso
        """
        try:
            # Obtener información del video original
            try:
                probe = ffmpeg.probe(input_path)
                video_info = next(
                    (stream for stream in probe['streams'] if stream['codec_type'] == 'video'), 
                    None
                )
            except Exception as e:
                return False, f"Error al analizar video: {str(e)}", 0.0
            
            if not video_info:
                return False, "No se encontró stream de video en el archivo", 0.0
            
            # Calcular duración y tamaño original
            duration = float(probe['format']['duration'])
            original_size_mb = os.path.getsize(input_path) / (1024 * 1024)
            
            # Si el video ya es más pequeño que el límite, copiarlo sin comprimir
            if original_size_mb <= max_size_mb:
                shutil.copy2(input_path, output_path)
                return True, f"Video ya estaba dentro del límite ({original_size_mb:.1f}MB)", 0.0
            
            # Calcular bitrate objetivo para alcanzar el tamaño máximo
            target_size_bits = max_size_mb * 8 * 1024 * 1024  # Convertir MB a bits
            target_video_bitrate = (target_size_bits / duration) - (int(audio_bitrate.replace('k', '')) * 1024)
            target_video_bitrate = max(target_video_bitrate, 300 * 1024)  # Mínimo 300kbps
            
            # Configurar parámetros de FFmpeg
            ffmpeg_args = [
                'ffmpeg',
                '-i', input_path,
                '-vcodec', 'libx264',
                '-crf', str(crf),
                '-preset', preset,
                '-b:v', f'{int(target_video_bitrate / 1024)}k',
                '-maxrate', f'{int(target_video_bitrate / 1024)}k',
                '-bufsize', f'{int(target_video_bitrate / 512)}k',
                '-acodec', 'aac',
                '-b:a', audio_bitrate,
                '-movflags', '+faststart',
                '-threads', str(os.cpu_count() // 2 or 1),
                '-y',  # Sobrescribir archivo existente
                output_path
            ]
            
            # Ejecutar FFmpeg
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitorear progreso
            start_time = time.time()
            last_update = start_time
            
            while True:
                if self.is_cancelled:
                    process.terminate()
                    await process.wait()
                    return False, "Compresión cancelada por el usuario", 0.0
                
                # Verificar si el proceso ha terminado
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.5)
                    break
                except asyncio.TimeoutError:
                    pass
                
                # Actualizar progreso basado en el archivo de salida
                if os.path.exists(output_path):
                    current_size = os.path.getsize(output_path)
                    estimated_total = max_size_mb * 1024 * 1024
                    progress = min(current_size / estimated_total, 0.99)
                    
                    # Actualizar cada 2 segundos
                    if time.time() - last_update > 2:
                        self.current_progress = progress
                        if self.progress_callback:
                            await self.progress_callback(progress)
                        last_update = time.time()
            
            # Verificar resultado
            if process.returncode != 0:
                stderr = (await process.stderr.read()).decode('utf-8', errors='ignore')
                error_msg = stderr[-500:] if len(stderr) > 500 else stderr
                return False, f"Error FFmpeg: {error_msg}", 0.0
            
            # Calcular ratio de compresión
            compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            compression_ratio = ((original_size_mb - compressed_size_mb) / original_size_mb) * 100
            
            return True, f"Compresión exitosa: {compressed_size_mb:.1f}MB ({compression_ratio:.1f}% reducción)", compression_ratio
            
        except Exception as e:
            return False, f"Error inesperado: {str(e)}", 0.0
    
    def cancel(self):
        """Cancelar la compresión en curso"""
        self.is_cancelled = True
    
    @staticmethod
    def get_video_info(file_path: str) -> Dict:
        """Obtener información detallada del video"""
        try:
            probe = ffmpeg.probe(file_path)
            
            video_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
            audio_stream = next((s for s in probe['streams'] if s['codec_type'] == 'audio'), None)
            
            info = {
                'duration_seconds': float(probe['format']['duration']),
                'size_mb': os.path.getsize(file_path) / (1024 * 1024),
                'format': probe['format']['format_name'].upper(),
                'bitrate_kbps': int(probe['format']['bit_rate']) // 1000 if 'bit_rate' in probe['format'] else 0,
            }
            
            if video_stream:
                info.update({
                    'resolution': f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
                    'video_codec': video_stream.get('codec_name', 'Desconocido').upper(),
                    'fps': eval(video_stream.get('avg_frame_rate', '0/1')) if '/' in video_stream.get('avg_frame_rate', '0/1') else 0,
                })
            
            if audio_stream:
                info.update({
                    'audio_codec': audio_stream.get('codec_name', 'Desconocido').upper(),
                    'audio_channels': audio_stream.get('channels', 0),
                    'sample_rate': f"{int(audio_stream.get('sample_rate', 0)) // 1000}kHz",
                })
            
            # Formatear duración
            minutes, seconds = divmod(int(info['duration_seconds']), 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                info['duration'] = f"{hours}h {minutes}m {seconds}s"
            else:
                info['duration'] = f"{minutes}m {seconds}s"
            
            return info
            
        except Exception as e:
            return {'error': str(e)}

# ==================== MANEJADOR DE PROGRESO ====================
class ProgressHandler:
    def __init__(self, client: Client, chat_id: int, message_id: int):
        self.client = client
        self.chat_id = chat_id
        self.message_id = message_id
        self.last_update_time = 0
        self.update_interval = 3  # Segundos entre actualizaciones
    
    async def update(self, progress: float, status_text: str = ""):
        """Actualizar el mensaje de progreso"""
        current_time = time.time()
        
        # Solo actualizar cada 'update_interval' segundos
        if current_time - self.last_update_time < self.update_interval and progress < 0.99:
            return
        
        self.last_update_time = current_time
        
        # Crear barra de progreso
        bar_length = 15
        filled_length = int(bar_length * progress)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        percentage = progress * 100
        
        # Crear mensaje
        if progress >= 0.99:
            message = f"**✅ Finalizando...**\n`[{bar}] {percentage:.1f}%`\n{status_text}"
        else:
            message = f"**🔄 Comprimiendo...**\n`[{bar}] {percentage:.1f}%`\n{status_text}"
        
        try:
            await self.client.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=message
            )
        except Exception:
            pass  # Ignorar errores de edición
    
    async def final_update(self, success: bool, message: str):
        """Actualización final del mensaje"""
        if success:
            icon = "✅"
            title = "COMPRESIÓN COMPLETADA"
        else:
            icon = "❌"
            title = "COMPRESIÓN FALLIDA"
        
        final_message = f"**{icon} {title}**\n\n{message}"
        
        try:
            await self.client.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=final_message,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Nuevo Video", callback_data="new_video")
                ]]) if success else None
            )
        except Exception:
            pass

# ==================== BOT PRINCIPAL ====================
class VideoCompressionBot:
    def __init__(self):
        self.app = Client(
            "video_compression_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            sleep_threshold=30
        )
        self.active_jobs = {}  # user_id -> job_info
        self.setup_handlers()
    
    def _check_user_allowed(self, user_id: int) -> bool:
        """Verificar si el usuario está autorizado"""
        if not Config.ALLOWED_USERS:
            return True
        return user_id in Config.ALLOWED_USERS
    
    def _cleanup_files(self, *file_paths):
        """Eliminar archivos temporales"""
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
    
    def _get_user_dir(self, user_id: int) -> str:
        """Obtener directorio del usuario"""
        user_dir = os.path.join(Config.DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        return user_dir
    
    async def _download_video(self, message: Message, user_id: int) -> Optional[str]:
        """Descargar video de Telegram"""
        user_dir = self._get_user_dir(user_id)
        
        if message.video:
            file = message.video
        elif message.document:
            # Verificar si es un video por extensión del archivo
            if hasattr(message.document, 'file_name'):
                file_ext = os.path.splitext(message.document.file_name.lower())[1]
                video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
                if file_ext in video_extensions:
                    file = message.document
                else:
                    return None
            else:
                return None
        else:
            return None
        
        # Generar nombre de archivo único
        timestamp = int(time.time())
        file_ext = os.path.splitext(file.file_name)[1] if hasattr(file, 'file_name') else '.mp4'
        download_path = os.path.join(user_dir, f"{timestamp}{file_ext}")
        
        try:
            # Mostrar mensaje de descarga
            status_msg = await message.reply_text("📥 **Descargando video...**\nPor favor espera...")
            
            # Descargar el archivo
            download_task = self.app.download_media(
                message,
                file_name=download_path,
                progress=self._download_progress,
                progress_args=(status_msg,)
            )
            
            # Esperar con timeout
            try:
                await asyncio.wait_for(download_task, timeout=Config.DOWNLOAD_TIMEOUT)
            except asyncio.TimeoutError:
                await status_msg.edit_text("❌ **Timeout:** La descarga tomó demasiado tiempo")
                return None
            
            await status_msg.delete()
            return download_path
            
        except Exception as e:
            await message.reply_text(f"❌ **Error al descargar:** {str(e)}")
            return None
    
    async def _download_progress(self, current, total, status_msg):
        """Mostrar progreso de descarga"""
        if total == 0:
            return
        
        progress = current / total
        bar_length = 15
        filled_length = int(bar_length * progress)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        percentage = progress * 100
        
        # Convertir bytes a MB
        current_mb = current / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        
        try:
            await status_msg.edit_text(
                f"📥 **Descargando...**\n"
                f"`[{bar}] {percentage:.1f}%`\n"
                f"**Tamaño:** {current_mb:.1f}MB / {total_mb:.1f}MB"
            )
        except Exception:
            pass
    
    async def _compress_and_send(self, message: Message, video_path: str):
        """Comprimir video y enviarlo"""
        user_id = message.from_user.id
        
        # Verificar límite de trabajos simultáneos
        active_count = sum(1 for job in self.active_jobs.values() if job.get('active', False))
        if active_count >= Config.MAX_CONCURRENT_JOBS:
            await message.reply_text(
                f"⚠️ **Bot ocupado:** Hay {active_count}/{Config.MAX_CONCURRENT_JOBS} compresiones activas.\n"
                f"Intenta de nuevo en unos minutos."
            )
            return
        
        # Crear mensaje de estado
        status_msg = await message.reply_text("⏳ **Iniciando compresión...**")
        
        # Generar ruta de salida
        user_dir = self._get_user_dir(user_id)
        timestamp = int(time.time())
        output_path = os.path.join(user_dir, f"compressed_{timestamp}.mp4")
        
        # Crear handler de progreso
        progress_handler = ProgressHandler(self.app, message.chat.id, status_msg.id)
        
        # Crear compresor
        compressor = VideoCompressor(progress_callback=progress_handler.update)
        
        # Registrar trabajo activo
        self.active_jobs[user_id] = {
            'active': True,
            'compressor': compressor,
            'start_time': time.time(),
            'input_path': video_path,
            'output_path': output_path
        }
        
        try:
            # Obtener información del video original
            video_info = VideoCompressor.get_video_info(video_path)
            
            if 'error' in video_info:
                await status_msg.edit_text(f"❌ **Error:** No se pudo analizar el video")
                self._cleanup_files(video_path, output_path)
                del self.active_jobs[user_id]
                return
            
            # Mostrar información inicial
            info_text = (
                f"📊 **Información del Video**\n\n"
                f"• **Resolución:** {video_info.get('resolution', 'N/A')}\n"
                f"• **Duración:** {video_info.get('duration', 'N/A')}\n"
                f"• **Tamaño:** {video_info['size_mb']:.1f}MB\n"
                f"• **Formato:** {video_info.get('format', 'N/A')}\n"
                f"• **Codec Video:** {video_info.get('video_codec', 'N/A')}\n\n"
                f"⚙️ **Comprimiendo...**"
            )
            
            await status_msg.edit_text(info_text)
            await asyncio.sleep(2)  # Pequeña pausa para que el usuario vea la info
            
            # Configuración de compresión
            settings = Config.COMPRESSION_SETTINGS
            
            # Comprimir video
            await status_msg.edit_text("🔄 **Iniciando compresión...**\nEsto puede tomar varios minutos...")
            
            success, result_message, compression_ratio = await compressor.compress_video(
                input_path=video_path,
                output_path=output_path,
                crf=settings['crf'],
                preset=settings['preset'],
                audio_bitrate=settings['audio_bitrate'],
                video_bitrate=settings['video_bitrate'],
                max_size_mb=settings['max_size_mb']
            )
            
            # Actualizar mensaje final
            await progress_handler.final_update(success, result_message)
            
            if success and os.path.exists(output_path):
                # Obtener información del video comprimido
                compressed_info = VideoCompressor.get_video_info(output_path)
                
                # Enviar video comprimido
                await message.reply_text("📤 **Enviando video comprimido...**")
                
                # Calcular tiempo transcurrido
                elapsed_time = time.time() - self.active_jobs[user_id]['start_time']
                minutes, seconds = divmod(int(elapsed_time), 60)
                
                caption = (
                    f"✅ **Video Comprimido**\n\n"
                    f"📊 **Antes:** {video_info['size_mb']:.1f}MB\n"
                    f"📉 **Después:** {compressed_info.get('size_mb', 0):.1f}MB\n"
                    f"🎯 **Reducción:** {compression_ratio:.1f}%\n"
                    f"⏱️ **Tiempo:** {minutes}m {seconds}s\n\n"
                    f"⚙️ **Configuración usada:**\n"
                    f"• CRF: {settings['crf']}\n"
                    f"• Preset: {settings['preset']}\n"
                    f"• Audio: {settings['audio_bitrate']}\n"
                    f"• Máximo: {settings['max_size_mb']}MB"
                )
                
                # Enviar video
                await self.app.send_video(
                    chat_id=message.chat.id,
                    video=output_path,
                    caption=caption,
                    thumb=self._generate_thumbnail(output_path) if os.path.exists(output_path) else None,
                    supports_streaming=True,
                    reply_to_message_id=message.id
                )
            
        except asyncio.CancelledError:
            await status_msg.edit_text("❌ **Compresión cancelada**")
        except Exception as e:
            await status_msg.edit_text(f"❌ **Error durante la compresión:** {str(e)}")
        finally:
            # Limpiar
            self._cleanup_files(video_path, output_path)
            if user_id in self.active_jobs:
                del self.active_jobs[user_id]
    
    def _generate_thumbnail(self, video_path: str) -> Optional[str]:
        """Generar miniatura del video"""
        try:
            thumbnail_path = os.path.join(Config.TEMP_DIR, f"thumb_{int(time.time())}.jpg")
            
            # Extraer frame en el segundo 1
            (
                ffmpeg
                .input(video_path, ss=1)
                .output(thumbnail_path, vframes=1, vcodec='mjpeg')
                .run(quiet=True, overwrite_output=True)
            )
            
            return thumbnail_path if os.path.exists(thumbnail_path) else None
        except Exception:
            return None
    
    def setup_handlers(self):
        """Configurar manejadores de comandos del bot"""
        
        @self.app.on_message(filters.command("start"))
        async def start_command(client: Client, message: Message):
            user_id = message.from_user.id
            
            if not self._check_user_allowed(user_id):
                await message.reply_text("❌ No estás autorizado para usar este bot.")
                return
            
            welcome_text = (
                "🤖 **Bienvenido al Bot Compresor de Videos**\n\n"
                "**Funcionalidades:**\n"
                "• Comprimir videos automáticamente\n"
                "• Reducir tamaño manteniendo calidad\n"
                "• Barra de progreso en tiempo real\n"
                "• Información detallada de videos\n\n"
                "**Comandos disponibles:**\n"
                "▶️ **/start** - Mostrar este mensaje\n"
                "⚡ **/compress** - Comprimir video (responder a video)\n"
                "📊 **/info** - Ver información del video\n"
                "⚙️ **/settings** - Ver configuración actual\n"
                "📈 **/status** - Estado del bot\n"
                "❌ **/cancel** - Cancelar compresión actual\n\n"
                "**Modo de uso:**\n"
                "1. Envía un video o responde a uno con /compress\n"
                "2. Espera a que se procese\n"
                "3. Recibe el video comprimido\n\n"
                "⚠️ **Formatos soportados:** MP4, AVI, MKV, MOV, WMV, FLV"
            )
            
            await message.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📤 Comprimir Video", callback_data="compress_new"),
                    InlineKeyboardButton("⚙️ Configuración", callback_data="show_settings")
                ]])
            )
        
        @self.app.on_message(filters.command("compress"))
        async def compress_command(client: Client, message: Message):
            user_id = message.from_user.id
            
            if not self._check_user_allowed(user_id):
                await message.reply_text("❌ No estás autorizado para usar este bot.")
                return
            
            # Verificar si es respuesta a un mensaje con video
            if message.reply_to_message:
                if message.reply_to_message.video:
                    target_msg = message.reply_to_message
                elif message.reply_to_message.document:
                    # Verificar por extensión del archivo
                    if hasattr(message.reply_to_message.document, 'file_name'):
                        file_ext = os.path.splitext(message.reply_to_message.document.file_name.lower())[1]
                        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
                        if file_ext in video_extensions:
                            target_msg = message.reply_to_message
                        else:
                            await message.reply_text("❌ El archivo adjunto no parece ser un video soportado")
                            return
                    else:
                        await message.reply_text("❌ No se puede determinar el tipo de archivo")
                        return
                else:
                    await message.reply_text("❌ Responde a un video para comprimirlo")
                    return
            elif message.video:
                target_msg = message
            elif message.document:
                # Verificar por extensión del archivo
                if hasattr(message.document, 'file_name'):
                    file_ext = os.path.splitext(message.document.file_name.lower())[1]
                    video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
                    if file_ext in video_extensions:
                        target_msg = message
                    else:
                        await message.reply_text("❌ El archivo adjunto no parece ser un video soportado")
                        return
                else:
                    await message.reply_text("❌ No se puede determinar el tipo de archivo")
                    return
            else:
                await message.reply_text(
                    "📤 **Envía un video para comprimir**\n\n"
                    "Puedes:\n"
                    "1. Enviar un video directamente\n"
                    "2. Responder a un video con /compress\n\n"
                    "O usa los botones:",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Cancelar", callback_data="cancel_operation")
                    ]])
                )
                return
            
            # Descargar y comprimir video
            video_path = await self._download_video(target_msg, user_id)
            if video_path:
                asyncio.create_task(self._compress_and_send(message, video_path))
            else:
                await message.reply_text("❌ No se pudo descargar el video")
        
        @self.app.on_message(filters.command("info"))
        async def info_command(client: Client, message: Message):
            user_id = message.from_user.id
            
            if not self._check_user_allowed(user_id):
                return
            
            target_message = message.reply_to_message if message.reply_to_message else message
            
            # Verificar si es un video
            is_video = False
            if target_message.video:
                is_video = True
            elif target_message.document:
                if hasattr(target_message.document, 'file_name'):
                    file_ext = os.path.splitext(target_message.document.file_name.lower())[1]
                    video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
                    if file_ext in video_extensions:
                        is_video = True
            
            if is_video:
                # Descargar temporalmente para analizar
                video_path = await self._download_video(target_message, user_id)
                
                if video_path:
                    video_info = VideoCompressor.get_video_info(video_path)
                    
                    if 'error' not in video_info:
                        info_text = (
                            f"📊 **Información del Video**\n\n"
                            f"• **Resolución:** {video_info.get('resolution', 'N/A')}\n"
                            f"• **Duración:** {video_info.get('duration', 'N/A')}\n"
                            f"• **Tamaño:** {video_info['size_mb']:.1f}MB\n"
                            f"• **Formato:** {video_info.get('format', 'N/A')}\n"
                            f"• **Bitrate:** {video_info['bitrate_kbps']} kbps\n"
                            f"• **Codec Video:** {video_info.get('video_codec', 'N/A')}\n"
                            f"• **FPS:** {video_info.get('fps', 0):.2f}\n"
                            f"• **Codec Audio:** {video_info.get('audio_codec', 'N/A')}\n"
                            f"• **Canales:** {video_info.get('audio_channels', 0)}\n"
                            f"• **Sample Rate:** {video_info.get('sample_rate', 'N/A')}"
                        )
                        
                        await message.reply_text(
                            info_text,
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("⚡ Comprimir", callback_data=f"compress_{target_message.id}")
                            ]])
                        )
                    else:
                        await message.reply_text("❌ No se pudo obtener información del video")
                    
                    # Limpiar archivo temporal
                    self._cleanup_files(video_path)
                else:
                    await message.reply_text("❌ No se pudo descargar el video para análisis")
            else:
                await message.reply_text("❌ Responde a un video para ver su información")
        
        @self.app.on_message(filters.command("settings"))
        async def settings_command(client: Client, message: Message):
            if not self._check_user_allowed(message.from_user.id):
                return
            
            settings = Config.COMPRESSION_SETTINGS
            
            settings_text = (
                f"⚙️ **Configuración Actual**\n\n"
                f"**Calidad:**\n"
                f"• **CRF:** `{settings['crf']}` (18-28, menor = mejor calidad)\n\n"
                f"**Velocidad:**\n"
                f"• **Preset:** `{settings['preset']}`\n"
                f"  (ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow)\n\n"
                f"**Audio:**\n"
                f"• **Bitrate:** `{settings['audio_bitrate']}`\n\n"
                f"**Video:**\n"
                f"• **Bitrate:** `{settings['video_bitrate']}`\n\n"
                f"**Límites:**\n"
                f"• **Tamaño máximo:** `{settings['max_size_mb']}MB`\n"
                f"• **Formato salida:** `{settings['output_format']}`\n\n"
                f"*Nota: Para cambiar configuración, edita el archivo .env*"
            )
            
            await message.reply_text(settings_text)
        
        @self.app.on_message(filters.command("status"))
        async def status_command(client: Client, message: Message):
            if not self._check_user_allowed(message.from_user.id):
                return
            
            # Calcular espacio libre
            total, used, free = shutil.disk_usage(".")
            free_gb = free // (2**30)
            
            # Contar trabajos activos
            active_count = sum(1 for job in self.active_jobs.values() if job.get('active', False))
            
            status_text = (
                f"📊 **Estado del Bot**\n\n"
                f"• **Trabajos activos:** {active_count}/{Config.MAX_CONCURRENT_JOBS}\n"
                f"• **Espacio libre:** {free_gb}GB\n"
                f"• **Usuarios en sesión:** {len(self.active_jobs)}\n"
                f"• **Directorios:**\n"
                f"  - Descargas: `{Config.DOWNLOAD_DIR}`\n"
                f"  - Uploads: `{Config.UPLOAD_DIR}`\n"
                f"  - Temporal: `{Config.TEMP_DIR}`\n\n"
                f"✅ **Bot operativo y listo**"
            )
            
            await message.reply_text(status_text)
        
        @self.app.on_message(filters.command("cancel"))
        async def cancel_command(client: Client, message: Message):
            user_id = message.from_user.id
            
            if not self._check_user_allowed(user_id):
                return
            
            if user_id in self.active_jobs:
                self.active_jobs[user_id]['compressor'].cancel()
                await message.reply_text("⏹️ **Compresión cancelada**")
            else:
                await message.reply_text("ℹ️ No tienes compresiones activas para cancelar")
        
        @self.app.on_message(filters.video | filters.document)
        async def handle_video_message(client: Client, message: Message):
            user_id = message.from_user.id
            
            if not self._check_user_allowed(user_id):
                return
            
            # Verificar si es un documento de video
            is_video_document = False
            if message.document and hasattr(message.document, 'file_name'):
                file_ext = os.path.splitext(message.document.file_name.lower())[1]
                video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
                if file_ext in video_extensions:
                    is_video_document = True
            
            # Solo procesar si es video o documento de video
            if not (message.video or is_video_document):
                return
            
            # No procesar automáticamente si hay muchos trabajos
            active_count = sum(1 for job in self.active_jobs.values() if job.get('active', False))
            if active_count >= Config.MAX_CONCURRENT_JOBS:
                return
            
            # Mostrar botones de opciones
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("⚡ Comprimir", callback_data=f"compress_{message.id}"),
                InlineKeyboardButton("📊 Info", callback_data=f"info_{message.id}")
            ], [
                InlineKeyboardButton("❌ Ignorar", callback_data="ignore_video")
            ]])
            
            await message.reply_text(
                "🎥 **Video detectado**\n\n"
                "¿Qué deseas hacer con este video?",
                reply_markup=keyboard,
                reply_to_message_id=message.id
            )
        
        @self.app.on_callback_query()
        async def handle_callback(client: Client, callback_query: CallbackQuery):
            data = callback_query.data
            user_id = callback_query.from_user.id
            
            if not self._check_user_allowed(user_id):
                await callback_query.answer("No autorizado", show_alert=True)
                return
            
            try:
                if data == "compress_new":
                    await callback_query.message.edit_text(
                        "📤 **Envía un video para comprimir**\n\n"
                        "Puedes enviar un video directamente o responder a uno existente."
                    )
                
                elif data.startswith("compress_"):
                    message_id = int(data.split("_")[1])
                    
                    try:
                        original_message = await client.get_messages(
                            callback_query.message.chat.id,
                            message_id
                        )
                        
                        # Verificar si es video
                        is_video = False
                        if original_message.video:
                            is_video = True
                        elif original_message.document:
                            if hasattr(original_message.document, 'file_name'):
                                file_ext = os.path.splitext(original_message.document.file_name.lower())[1]
                                video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
                                if file_ext in video_extensions:
                                    is_video = True
                        
                        if is_video:
                            await callback_query.answer("Descargando video...")
                            
                            video_path = await self._download_video(original_message, user_id)
                            if video_path:
                                asyncio.create_task(self._compress_and_send(callback_query.message, video_path))
                                await callback_query.message.edit_text("⏳ **Iniciando compresión...**")
                            else:
                                await callback_query.message.edit_text("❌ Error al descargar el video")
                        else:
                            await callback_query.message.edit_text("❌ El mensaje no contiene un video")
                    
                    except Exception as e:
                        await callback_query.message.edit_text(f"❌ Error: {str(e)}")
                
                elif data.startswith("info_"):
                    message_id = int(data.split("_")[1])
                    
                    try:
                        original_message = await client.get_messages(
                            callback_query.message.chat.id,
                            message_id
                        )
                        
                        # Verificar si es video
                        is_video = False
                        if original_message.video:
                            is_video = True
                        elif original_message.document:
                            if hasattr(original_message.document, 'file_name'):
                                file_ext = os.path.splitext(original_message.document.file_name.lower())[1]
                                video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
                                if file_ext in video_extensions:
                                    is_video = True
                        
                        if is_video:
                            video_path = await self._download_video(original_message, user_id)
                            
                            if video_path:
                                video_info = VideoCompressor.get_video_info(video_path)
                                
                                if 'error' not in video_info:
                                    info_text = (
                                        f"📊 **Información del Video**\n\n"
                                        f"• **Resolución:** {video_info.get('resolution', 'N/A')}\n"
                                        f"• **Duración:** {video_info.get('duration', 'N/A')}\n"
                                        f"• **Tamaño:** {video_info['size_mb']:.1f}MB\n"
                                        f"• **Formato:** {video_info.get('format', 'N/A')}\n"
                                        f"• **Codec Video:** {video_info.get('video_codec', 'N/A')}"
                                    )
                                    
                                    await callback_query.message.edit_text(
                                        info_text,
                                        reply_markup=InlineKeyboardMarkup([[
                                            InlineKeyboardButton("⚡ Comprimir", callback_data=f"compress_{message_id}")
                                        ]])
                                    )
                                else:
                                    await callback_query.message.edit_text("❌ No se pudo obtener información")
                                
                                self._cleanup_files(video_path)
                            else:
                                await callback_query.message.edit_text("❌ Error al descargar")
                        else:
                            await callback_query.message.edit_text("❌ No es un video")
                    
                    except Exception as e:
                        await callback_query.message.edit_text(f"❌ Error: {str(e)}")
                
                elif data == "show_settings":
                    settings = Config.COMPRESSION_SETTINGS
                    settings_text = (
                        f"⚙️ **Configuración**\n\n"
                        f"• CRF: {settings['crf']}\n"
                        f"• Preset: {settings['preset']}\n"
                        f"• Audio: {settings['audio_bitrate']}\n"
                        f"• Video: {settings['video_bitrate']}\n"
                        f"• Máximo: {settings['max_size_mb']}MB"
                    )
                    
                    await callback_query.message.edit_text(
                        settings_text,
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔄 Actualizar", callback_data="refresh_settings"),
                            InlineKeyboardButton("⬅️ Volver", callback_data="back_to_start")
                        ]])
                    )
                
                elif data == "new_video":
                    await callback_query.message.edit_text(
                        "📤 **Envía un nuevo video para comprimir**\n\n"
                        "Puedes enviar un video o responder a uno con /compress",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_operation")
                        ]])
                    )
                
                elif data in ["cancel_operation", "ignore_video"]:
                    await callback_query.message.delete()
                
                elif data == "back_to_start":
                    await callback_query.message.edit_text(
                        "🤖 **Bot Compresor de Videos**\n\n"
                        "Selecciona una opción:",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📤 Comprimir Video", callback_data="compress_new"),
                            InlineKeyboardButton("⚙️ Configuración", callback_data="show_settings")
                        ]])
                    )
                
                elif data == "refresh_settings":
                    settings = Config.COMPRESSION_SETTINGS
                    settings_text = f"⚙️ Configuración actualizada\nCRF: {settings['crf']}, Preset: {settings['preset']}"
                    await callback_query.answer(settings_text, show_alert=True)
                
            except Exception as e:
                await callback_query.answer(f"Error: {str(e)}", show_alert=True)
            
            await callback_query.answer()
    
    async def run(self):
        """Ejecutar el bot"""
        print("🤖 Iniciando Bot de Compresión de Videos...")
        print(f"📁 Directorios creados: downloads/, uploads/, temp/")
        
        await self.app.start()
        
        # Obtener información del bot
        me = await self.app.get_me()
        print(f"✅ Bot iniciado como: @{me.username}")
        print(f"🆔 ID del Bot: {me.id}")
        print(f"👥 Usuarios permitidos: {'Todos' if not Config.ALLOWED_USERS else Config.ALLOWED_USERS}")
        print(f"⚙️ Configuración: CRF={Config.COMPRESSION_SETTINGS['crf']}, "
              f"Preset={Config.COMPRESSION_SETTINGS['preset']}, "
              f"Máximo={Config.COMPRESSION_SETTINGS['max_size_mb']}MB")
        print("\n📝 Comandos disponibles:")
        print("  /start - Mostrar ayuda")
        print("  /compress - Comprimir video")
        print("  /info - Ver información del video")
        print("  /settings - Ver configuración")
        print("  /status - Estado del bot")
        print("  /cancel - Cancelar compresión")
        print("\n⏳ Bot en ejecución. Presiona Ctrl+C para detener.")
        
        # Mantener el bot activo
        await idle()
        
        await self.app.stop()
        print("\n👋 Bot detenido")

# ==================== EJECUCIÓN PRINCIPAL ====================
if __name__ == "__main__":
    # Verificar que FFmpeg esté instalado
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ ERROR: FFmpeg no está instalado o no está en el PATH")
        print("Por favor instala FFmpeg:")
        print("  Ubuntu/Debian: sudo apt install ffmpeg")
        print("  macOS: brew install ffmpeg")
        print("  Windows: Descarga desde https://ffmpeg.org/")
        exit(1)
    
    # Crear archivo .env de ejemplo si no existe
    if not os.path.exists('.env'):
        with open('.env.example', 'w') as f:
            f.write("""# Configuración del Bot de Compresión de Videos
API_ID=123456
API_HASH=tu_api_hash_aqui
BOT_TOKEN=tu_bot_token_aqui

# Configuración opcional
# ALLOWED_USERS=123456789,987654321
# MAX_CONCURRENT_JOBS=3
""")
        print("📝 Archivo .env.example creado. Renómbralo a .env y completa tus credenciales")
    
    # Verificar credenciales
    if Config.API_ID == 123456 or Config.API_HASH == "tu_api_hash" or Config.BOT_TOKEN == "tu_bot_token":
        print("❌ ERROR: Configura tus credenciales en el archivo .env")
        print("  1. Renombra .env.example a .env")
        print("  2. Edita .env con tus credenciales de Telegram")
        print("  3. Obtén tus credenciales en: https://my.telegram.org")
        exit(1)
    
    # Crear y ejecutar el bot
    bot = VideoCompressionBot()
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n👋 Bot interrumpido por el usuario")
    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        # Limpiar directorios temporales
        print("🧹 Limpiando archivos temporales...")
        shutil.rmtree(Config.TEMP_DIR, ignore_errors=True)
        print("✅ Limpieza completada")
