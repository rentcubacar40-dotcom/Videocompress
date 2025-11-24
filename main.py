#!/usr/bin/env python3
"""
Video Compressor Bot - Professional Edition
Optimized for Render 4GB RAM - High Performance Telegram Bot
"""

import os
import asyncio
import logging
import tempfile
import time
import subprocess
import sys
import psutil
import aiofiles
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import re
import json

# ==================== SOLUCIÓN PARA IMGHDR ====================
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
# ==================== FIN SOLUCIÓN IMGHDR ====================

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Configure professional logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('compression_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("VideoCompressor")

# Import Telethon
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename, DocumentAttributeAudio

class CompressionPreset(Enum):
    ULTRA_TURBO = "ultra_turbo"
    TURBO = "turbo"
    BALANCED = "balanced"
    QUALITY = "quality"
    MAX_QUALITY = "max_quality"
    AUDIO_ONLY = "audio_only"

class ProcessingStage(Enum):
    DOWNLOADING = "📥 DESCARGANDO"
    ANALYZING = "🔍 ANALIZANDO"
    COMPRESSING = "🎬 COMPRIMIENDO"
    UPLOADING = "📤 SUBIENDO"

@dataclass
class CompressionConfig:
    name: str
    crf: str
    preset: str
    audio_bitrate: str
    description: str
    quality: str
    speed: str
    size_ratio: float
    resolutions: List[str]

@dataclass
class ProgressData:
    stage: ProcessingStage
    percentage: int
    downloaded_bytes: int
    total_bytes: int
    speed: float
    eta: str
    start_time: datetime

class ProfessionalVideoCompressor:
    """
    High-performance video compression bot optimized for Render 4GB RAM
    """
    
    def __init__(self):
        # Validate environment variables
        self.api_id = int(os.getenv('API_ID', 0))
        self.api_hash = os.getenv('API_HASH', '')
        self.bot_token = os.getenv('BOT_TOKEN', '')
        
        if not all([self.api_id, self.api_hash, self.bot_token]):
            raise ValueError("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN")
        
        # Performance configuration
        self.max_file_size = 2 * 1024 * 1024 * 1024  # 2GB
        self.max_concurrent_jobs = 3
        self.chunk_size = 256 * 1024  # 256KB chunks for better performance
        
        # State management
        self.active_jobs: Dict[int, Dict] = {}
        self.user_sessions: Dict[int, Dict] = {}
        self.progress_trackers: Dict[int, ProgressData] = {}
        self.progress_messages: Dict[int, any] = {}  # Para almacenar mensajes de progreso
        
        # System statistics
        self.stats = {
            'total_jobs': 0,
            'successful_jobs': 0,
            'failed_jobs': 0,
            'total_compression_time': 0,
            'start_time': datetime.now()
        }
        
        # Initialize compression presets
        self.presets = self._initialize_presets()
        
        # Telegram client
        self.client = None
        
        logger.info("Professional Video Compressor initialized")

    def _initialize_presets(self) -> Dict[CompressionPreset, CompressionConfig]:
        """Initialize optimized compression presets"""
        return {
            CompressionPreset.ULTRA_TURBO: CompressionConfig(
                name="🚀 ULTRA TURBO",
                crf="35",
                preset="ultrafast",
                audio_bitrate="64k",
                description="Compresión máxima - Velocidad extrema",
                quality="Baja",
                speed="Máxima",
                size_ratio=0.07,
                resolutions=["240p", "360p", "480p"]
            ),
            CompressionPreset.TURBO: CompressionConfig(
                name="⚡ TURBO",
                crf="32",
                preset="superfast",
                audio_bitrate="96k",
                description="Alta compresión - Balance perfecto",
                quality="Media-Baja",
                speed="Muy Rápida",
                size_ratio=0.15,
                resolutions=["360p", "480p", "720p"]
            ),
            CompressionPreset.BALANCED: CompressionConfig(
                name="⚖️ BALANCEADO",
                crf="28",
                preset="fast",
                audio_bitrate="128k",
                description="Calidad equilibrada - Recomendado",
                quality="Buena",
                speed="Rápida",
                size_ratio=0.25,
                resolutions=["480p", "720p", "1080p"]
            ),
            CompressionPreset.QUALITY: CompressionConfig(
                name="🎨 CALIDAD",
                crf="23",
                preset="medium",
                audio_bitrate="160k",
                description="Alta calidad - Para redes sociales",
                quality="Muy Buena",
                speed="Media",
                size_ratio=0.40,
                resolutions=["720p", "1080p"]
            ),
            CompressionPreset.MAX_QUALITY: CompressionConfig(
                name="👑 MÁXIMA CALIDAD",
                crf="18",
                preset="slow",
                audio_bitrate="192k",
                description="Calidad profesional - Compresión mínima",
                quality="Excelente",
                speed="Lenta",
                size_ratio=0.60,
                resolutions=["1080p", "1440p", "2160p"]
            ),
            CompressionPreset.AUDIO_ONLY: CompressionConfig(
                name="🎵 SOLO AUDIO",
                crf="N/A",
                preset="fast",
                audio_bitrate="128k",
                description="Extrae solo audio en formato MP3",
                quality="Audio",
                speed="Rápida",
                size_ratio=0.03,
                resolutions=["audio"]
            )
        }

    async def initialize_client(self):
        """Initialize Telegram client with optimized settings"""
        self.client = TelegramClient(
            'compressor_session',
            self.api_id,
            self.api_hash,
            connection_retries=5,
            timeout=60,
            request_retries=3
        )
        
        await self.client.start(bot_token=self.bot_token)
        self._setup_handlers()
        
        logger.info("Telegram client initialized successfully")
        await self._notify_admin("Bot started successfully")

    def _setup_handlers(self):
        """Setup all event handlers"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await self._handle_start_command(event)

        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            await self._handle_help_command(event)

        @self.client.on(events.NewMessage(pattern='/stats'))
        async def stats_handler(event):
            await self._handle_stats_command(event)

        @self.client.on(events.NewMessage(pattern='/cancel'))
        async def cancel_handler(event):
            await self._handle_cancel_command(event)

        @self.client.on(events.NewMessage(pattern='/myid'))
        async def myid_handler(event):
            await self._handle_myid_command(event)

        @self.client.on(events.NewMessage(
            func=lambda e: e.message.video or (
                e.message.document and 
                e.message.document.mime_type and 
                'video' in e.message.document.mime_type
            )
        ))
        async def video_handler(event):
            await self._handle_video_message(event)

        @self.client.on(events.CallbackQuery())
        async def callback_handler(event):
            await self._handle_callback_query(event)

    async def _notify_admin(self, message: str):
        """Send notification to admin"""
        try:
            admin_id = os.getenv('ADMIN_ID')
            if admin_id:
                await self.client.send_message(
                    int(admin_id),
                    f"🤖 **System Notification**\n{message}"
                )
        except Exception as e:
            logger.warning(f"Could not send admin notification: {e}")

    async def _handle_start_command(self, event):
        """Handle /start command"""
        welcome_message = """
🤖 **Compresor de Videos Profesional**

Bienvenido al servicio de compresión de videos de alto rendimiento.

**Características:**
• Múltiples presets de compresión
• Seguimiento de progreso en tiempo real
• Soporte para archivos hasta 2GB
• Optimizado para velocidad y calidad

**Comandos:**
/start - Mostrar este mensaje
/help - Instrucciones detalladas
/stats - Estadísticas del sistema
/cancel - Cancelar operación actual
/myid - Obtener tu ID de usuario

**Cómo usar:**
1. Envíame un archivo de video
2. Elige el preset de compresión
3. Monitorea el progreso en tiempo real
4. Descarga el archivo comprimido

Envía un video para comenzar.
        """
        await event.reply(welcome_message)

    async def _handle_help_command(self, event):
        """Handle /help command"""
        help_text = """
📖 **Guía de Usuario - Compresor de Videos**

**Presets de Compresión:**

**🚀 ULTRA TURBO**
- Compresión máxima, tamaño mínimo
- Ideal para compartir rápido
- Calidad: Baja | Velocidad: Máxima

**⚡ TURBO**
- Buen balance compresión/calidad
- Recomendado para la mayoría de usos
- Calidad: Media | Velocidad: Muy Rápida

**⚖️ BALANCEADO**
- Equilibrio perfecto calidad/tamaño
- Recomendación por defecto
- Calidad: Buena | Velocidad: Rápida

**🎨 CALIDAD**
- Alta calidad visual
- Perfecto para redes sociales
- Calidad: Muy Buena | Velocidad: Media

**👑 MÁXIMA CALIDAD**
- Calidad profesional
- Compresión mínima
- Calidad: Excelente | Velocidad: Lenta

**🎵 SOLO AUDIO**
- Extrae solo el audio
- Formato MP3 de alta calidad

**Notas Técnicas:**
- Tamaño máximo: 2GB
- Formatos soportados: MP4, MOV, AVI, MKV
- Formato de salida: MP4 o MP3
- Actualizaciones de progreso en tiempo real
        """
        await event.reply(help_text)

    async def _handle_stats_command(self, event):
        """Handle /stats command"""
        uptime = datetime.now() - self.stats['start_time']
        memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        stats_text = f"""
📊 **Estadísticas del Sistema**

**Rendimiento:**
• Tiempo activo: {str(uptime).split('.')[0]}
• Trabajos totales: {self.stats['total_jobs']}
• Exitosos: {self.stats['successful_jobs']}
• Fallidos: {self.stats['failed_jobs']}
• Trabajos activos: {len(self.active_jobs)}

**Sistema:**
• Uso de memoria: {memory:.1f} MB
• Uso de CPU: {psutil.cpu_percent()}%
• Uso de disco: {psutil.disk_usage('/').percent}%

**Configuración:**
• Tamaño máximo: {self._format_size(self.max_file_size)}
• Trabajos concurrentes: {self.max_concurrent_jobs}
        """
        await event.reply(stats_text)

    async def _handle_myid_command(self, event):
        """Handle /myid command - Get user ID"""
        user_id = event.sender_id
        await event.reply(f"**Tu ID de Telegram es:** `{user_id}`")

    async def _handle_cancel_command(self, event):
        """Handle /cancel command"""
        user_id = event.sender_id
        
        if user_id in self.active_jobs:
            # Cancel active job
            del self.active_jobs[user_id]
            if user_id in self.progress_trackers:
                del self.progress_trackers[user_id]
            if user_id in self.progress_messages:
                del self.progress_messages[user_id]
            await event.reply("Operación cancelada exitosamente.")
        else:
            await event.reply("No hay operación activa para cancelar.")

    async def _handle_video_message(self, event):
        """Handle incoming video files"""
        user_id = event.sender_id
        
        # Check if user has active job
        if user_id in self.active_jobs:
            await event.reply("Por favor espera a que tu operación actual termine o usa /cancel")
            return

        message = event.message
        file_size = message.file.size
        
        # Validate file size
        if file_size > self.max_file_size:
            await message.reply(
                f"Archivo muy grande: {self._format_size(file_size)}\n"
                f"Máximo permitido: {self._format_size(self.max_file_size)}"
            )
            return

        # Store video information
        self.user_sessions[user_id] = {
            'file_size': file_size,
            'message': message,
            'received_time': datetime.now()
        }

        # Show compression options
        await self._show_compression_menu(event, file_size)

    async def _show_compression_menu(self, event, file_size: int):
        """Display compression preset selection menu - CORREGIDO"""
        buttons = []
        
        # Create preset buttons - SOLO UN BOTÓN POR PRESET
        for preset in CompressionPreset:
            config = self.presets[preset]
            
            if preset == CompressionPreset.AUDIO_ONLY:
                estimated_size = int(file_size * config.size_ratio)
                label = f"{config.name} (~{self._format_size(estimated_size)})"
                callback_data = f"preset:{preset.value}"
            else:
                # Para video, mostrar solo el preset principal
                estimated_size = int(file_size * config.size_ratio)
                label = f"{config.name} (~{self._format_size(estimated_size)})"
                callback_data = f"preset:{preset.value}"
            
            buttons.append([Button.inline(label, callback_data.encode())])
        
        # Add cancel button
        buttons.append([Button.inline("❌ Cancelar Operación", b"cancel")])
        
        menu_text = f"""
📹 **Opciones de Compresión de Video**

**Tamaño Original:** {self._format_size(file_size)}
**Tiempo Estimado de Procesamiento:** {self._estimate_processing_time(file_size)}

Selecciona el preset de compresión:
        """
        
        await event.reply(menu_text, buttons=buttons)

    async def _handle_callback_query(self, event):
        """Handle button callbacks - CORREGIDO"""
        user_id = event.sender_id
        data = event.data.decode()
        
        try:
            await event.answer()  # Responde la callback inmediatamente
            
            if data == "cancel":
                if user_id in self.active_jobs:
                    del self.active_jobs[user_id]
                await event.edit("Operación cancelada.")
                return
                
            elif data.startswith("preset:"):
                preset_key = data.split(":")[1]
                
                video_info = self.user_sessions.get(user_id)
                if not video_info:
                    await event.edit("❌ Sesión expirada. Por favor envía el video nuevamente.")
                    return
                
                # Start processing immediately
                await self._start_compression_job(event, video_info, preset_key)
                
        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await event.answer("Error procesando la solicitud", alert=True)

    async def _start_compression_job(self, event, video_info, preset_key: str):
        """Start video compression job - CORREGIDO"""
        user_id = event.sender_id
        
        try:
            # Mark job as active
            self.active_jobs[user_id] = {
                'start_time': datetime.now(),
                'preset': preset_key,
                'event_message': event  # Guardar referencia al evento
            }
            
            self.stats['total_jobs'] += 1
            
            # Initialize progress tracker
            self.progress_trackers[user_id] = ProgressData(
                stage=ProcessingStage.DOWNLOADING,
                percentage=0,
                downloaded_bytes=0,
                total_bytes=video_info['file_size'],
                speed=0,
                eta="Calculando...",
                start_time=datetime.now()
            )
            
            # Crear mensaje de progreso inicial
            progress_msg = await event.edit("📥 **Iniciando descarga...**")
            self.progress_messages[user_id] = progress_msg
            
            await self._process_video_pipeline(event, video_info, preset_key)
            
        except Exception as e:
            logger.error(f"Error en trabajo de compresión: {e}")
            await event.edit(f"❌ **Procesamiento falló:** {str(e)}")
            self.stats['failed_jobs'] += 1
            
            # Cleanup on failure
            if user_id in self.active_jobs:
                del self.active_jobs[user_id]
            if user_id in self.progress_trackers:
                del self.progress_trackers[user_id]
            if user_id in self.progress_messages:
                del self.progress_messages[user_id]

    async def _process_video_pipeline(self, event, video_info, preset_key: str):
        """Complete video processing pipeline - CORREGIDO"""
        user_id = event.sender_id
        message = video_info['message']
        
        # Generate unique file names
        input_path = os.path.join(tempfile.gettempdir(), f"input_{user_id}_{int(time.time())}.mp4")
        output_path = os.path.join(tempfile.gettempdir(), f"output_{user_id}_{int(time.time())}.mp4")
        
        try:
            # Stage 1: Download
            await self._update_progress_message(user_id, "📥 **Descargando video...**\n0%")
            await self._download_video(message, input_path, user_id)
            
            # Stage 2: Analyze
            await self._update_progress_message(user_id, "🔍 **Analizando video...**")
            video_duration = await self._get_video_duration(input_path)
            
            # Stage 3: Compress
            await self._update_progress_message(user_id, "🎬 **Comprimiendo video...**\n0%")
            await self._compress_video(input_path, output_path, preset_key, user_id, video_duration)
            
            # Stage 4: Upload
            await self._update_progress_message(user_id, "📤 **Subiendo resultado...**\n0%")
            await self._upload_result(event, output_path, preset_key)
            
            # Success
            self.stats['successful_jobs'] += 1
            job_time = (datetime.now() - self.active_jobs[user_id]['start_time']).total_seconds()
            self.stats['total_compression_time'] += job_time
            
            await self._update_progress_message(user_id, "✅ **¡Compresión completada exitosamente!**")
            
        except Exception as e:
            logger.error(f"Error en pipeline: {e}")
            await self._update_progress_message(user_id, f"❌ **Error en procesamiento:** {str(e)}")
            raise
        finally:
            # Cleanup temporary files
            await self._cleanup_files([input_path, output_path])
            
            # Cleanup user state
            if user_id in self.active_jobs:
                del self.active_jobs[user_id]
            if user_id in self.progress_trackers:
                del self.progress_trackers[user_id]
            if user_id in self.progress_messages:
                del self.progress_messages[user_id]
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]

    async def _download_video(self, message, input_path: str, user_id: int):
        """Download video with progress tracking"""
        last_update = time.time()
        
        def progress_callback(current, total):
            nonlocal last_update
            if time.time() - last_update > 1.0:  # Update every 1 second
                percentage = (current / total) * 100
                asyncio.create_task(self._update_progress_message(
                    user_id, 
                    f"📥 **Descargando video...**\n{percentage:.1f}%"
                ))
                last_update = time.time()
        
        await message.download_media(
            file=input_path,
            progress_callback=progress_callback
        )

    async def _compress_video(self, input_path: str, output_path: str, preset_key: str, 
                            user_id: int, duration: float):
        """Compress video using FFmpeg with real-time progress"""
        preset = self.presets[CompressionPreset(preset_key)]
        
        # Build FFmpeg command
        if preset_key == "audio_only":
            cmd = [
                'ffmpeg', '-i', input_path, '-vn',
                '-c:a', 'libmp3lame', '-b:a', preset.audio_bitrate,
                '-y', output_path
            ]
        else:
            cmd = [
                'ffmpeg', '-i', input_path,
                '-c:v', 'libx264', '-crf', preset.crf,
                '-preset', preset.preset,
                '-c:a', 'aac', '-b:a', preset.audio_bitrate,
                '-movflags', '+faststart',
                '-progress', 'pipe:1', '-loglevel', 'error',
                '-y', output_path
            ]
        
        # Execute with progress tracking
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Monitor progress
        async for line in process.stdout:
            line = line.decode().strip()
            if line.startswith('out_time='):
                current_time = self._parse_time_string(line.split('=')[1])
                if duration > 0:
                    percentage = (current_time / duration) * 100
                    await self._update_progress_message(
                        user_id,
                        f"🎬 **Comprimiendo video...**\n{percentage:.1f}%"
                    )
        
        await process.wait()

    async def _upload_result(self, event, output_path: str, preset_key: str):
        """Upload compressed file with progress"""
        user_id = event.sender_id
        
        if not os.path.exists(output_path):
            raise FileNotFoundError("Archivo comprimido no encontrado")
            
        file_size = os.path.getsize(output_path)
        preset = self.presets[CompressionPreset(preset_key)]
        
        caption = (
            f"**Video Comprimido**\n"
            f"• Preset: {preset.name}\n"
            f"• Tamaño: {self._format_size(file_size)}"
        )
        
        last_update = time.time()
        
        def upload_progress_callback(current, total):
            nonlocal last_update
            if time.time() - last_update > 1.0:
                percentage = (current / total) * 100
                asyncio.create_task(self._update_progress_message(
                    user_id,
                    f"📤 **Subiendo resultado...**\n{percentage:.1f}%"
                ))
                last_update = time.time()
        
        # Send file
        await self.client.send_file(
            event.chat_id,
            output_path,
            caption=caption,
            progress_callback=upload_progress_callback,
            attributes=[
                DocumentAttributeVideo(
                    duration=0,
                    w=0,
                    h=0,
                )
            ] if preset_key != "audio_only" else [
                DocumentAttributeAudio(
                    duration=0,
                    title=f"Audio Extraído - {preset.name}"
                )
            ]
        )

    async def _update_progress_message(self, user_id: int, message: str):
        """Update progress message efficiently"""
        try:
            if user_id in self.progress_messages:
                await self.progress_messages[user_id].edit(message)
        except Exception as e:
            logger.debug(f"Error actualizando progreso: {e}")

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes == 0:
            return "0B"
        
        units = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024.0
            i += 1
            
        return f"{size_bytes:.2f} {units[i]}"

    def _estimate_processing_time(self, file_size: int) -> str:
        """Estimate processing time based on file size"""
        if file_size < 100 * 1024 * 1024:  # < 100MB
            return "1-2 minutos"
        elif file_size < 500 * 1024 * 1024:  # < 500MB
            return "3-5 minutos"
        elif file_size < 1024 * 1024 * 1024:  # < 1GB
            return "5-10 minutos"
        else:  # 1GB+
            return "10-15 minutos"

    def _parse_time_string(self, time_str: str) -> float:
        """Parse FFmpeg time string to seconds"""
        try:
            if ':' in time_str:
                parts = time_str.split(':')
                if len(parts) == 3:
                    h, m, s = parts
                    return float(h) * 3600 + float(m) * 60 + float(s)
                elif len(parts) == 2:
                    m, s = parts
                    return float(m) * 60 + float(s)
            return float(time_str)
        except:
            return 0.0

    async def _get_video_duration(self, input_path: str) -> float:
        """Get video duration using FFprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                input_path
            ]
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await result.communicate()
            return float(stdout.decode().strip())
        except Exception as e:
            logger.warning(f"No se pudo obtener la duración del video: {e}")
            return 0.0

    async def _cleanup_files(self, file_paths: List[str]):
        """Clean up temporary files"""
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.debug(f"No se pudo eliminar {path}: {e}")

    async def run(self):
        """Main bot execution loop"""
        try:
            await self.initialize_client()
            logger.info("Bot is now running...")
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            raise
        finally:
            logger.info("Bot stopped")

async def main():
    """Application entry point"""
    try:
        # Validate FFmpeg availability
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("FFmpeg no encontrado. Por favor instala FFmpeg.")
            return
        
        # Create and run bot
        bot = ProfessionalVideoCompressor()
        await bot.run()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        sys.exit(1)

if __name__ == '__main__':
    # Set event loop policy for better performance
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Run the application
    asyncio.run(main())
