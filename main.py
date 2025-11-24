import os
import asyncio
import logging
import tempfile
import time
import subprocess
import sys
from dotenv import load_dotenv

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

# Importar telethon
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
        self.pending_videos = {}  # Almacenar videos pendientes de procesar
        
        # OPCIONES DE COMPRESIÓN INTELIGENTES
        self.compression_presets = {
            'ultra_turbo': {
                'name': '🚀 ULTRA TURBO',
                'crf': '35',
                'preset': 'veryfast',
                'scale': '854:480',
                'audio_bitrate': '64k',
                'description': 'Máxima compresión - Para compartir rápido',
                'quality': 'Baja',
                'speed': 'Muy Rápido'
            },
            'turbo': {
                'name': '⚡ TURBO', 
                'crf': '32',
                'preset': 'veryfast',
                'scale': '1280:720',
                'audio_bitrate': '96k',
                'description': 'Alta compresión - Buen balance',
                'quality': 'Media-Baja',
                'speed': 'Muy Rápido'
            },
            'balanced': {
                'name': '⚖️ BALANCEADO',
                'crf': '28', 
                'preset': 'medium',
                'scale': '1920:1080',
                'audio_bitrate': '128k',
                'description': 'Calidad equilibrada - Recomendado',
                'quality': 'Buena', 
                'speed': 'Rápido'
            },
            'quality': {
                'name': '🎨 CALIDAD',
                'crf': '23',
                'preset': 'slow', 
                'scale': '1920:1080',
                'audio_bitrate': '160k',
                'description': 'Alta calidad - Poca compresión',
                'quality': 'Muy Buena',
                'speed': 'Medio'
            },
            'max_quality': {
                'name': '👑 MÁXIMA CALIDAD',
                'crf': '18',
                'preset': 'veryslow',
                'scale': 'original',
                'audio_bitrate': '192k', 
                'description': 'Máxima calidad - Compresión mínima',
                'quality': 'Excelente',
                'speed': 'Lento'
            },
            'audio_only': {
                'name': '🎵 SOLO AUDIO', 
                'crf': 'N/A',
                'preset': 'fast',
                'scale': 'no_video',
                'audio_bitrate': '128k',
                'description': 'Extrae solo el audio (MP3)',
                'quality': 'Solo Audio',
                'speed': 'Rápido'
            }
        }
        
    async def initialize(self):
        """Inicializar el cliente de Telethon"""
        self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        logger.info("✅ Bot iniciado correctamente - Modo inteligente activo")
        
    def calculate_estimated_size(self, original_size, preset_key):
        """Calcular tamaño estimado basado en el preset"""
        reduction_ratios = {
            'ultra_turbo': 0.10,  # 90% reducción
            'turbo': 0.20,        # 80% reducción  
            'balanced': 0.35,     # 65% reducción
            'quality': 0.55,      # 45% reducción
            'max_quality': 0.75,  # 25% reducción
            'audio_only': 0.05    # 95% reducción (solo audio)
        }
        
        ratio = reduction_ratios.get(preset_key, 0.35)
        estimated_size = original_size * ratio
        return estimated_size
    
    def get_recommended_presets(self, file_size):
        """Obtener presets recomendados basados en el tamaño"""
        recommendations = []
        
        if file_size > 500 * 1024 * 1024:  # >500MB
            recommendations = ['ultra_turbo', 'turbo', 'balanced', 'audio_only']
        elif file_size > 100 * 1024 * 1024:  # >100MB
            recommendations = ['turbo', 'balanced', 'quality', 'audio_only'] 
        elif file_size > 50 * 1024 * 1024:   # >50MB
            recommendations = ['balanced', 'quality', 'max_quality', 'audio_only']
        else:  # <50MB
            recommendations = ['quality', 'max_quality', 'balanced', 'audio_only']
            
        return recommendations
    
    async def show_compression_options(self, message, file_size, file_path=None):
        """Mostrar opciones de compresión inteligentes"""
        try:
            recommended_presets = self.get_recommended_presets(file_size)
            
            # Crear botones para presets recomendados
            buttons = []
            row = []
            
            for i, preset_key in enumerate(recommended_presets):
                preset = self.compression_presets[preset_key]
                estimated_size = self.calculate_estimated_size(file_size, preset_key)
                
                button_text = f"{preset['name']} (~{self.get_file_size(estimated_size)})"
                button = Button.inline(button_text, f"compress_{preset_key}".encode())
                row.append(button)
                
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            
            # Agregar fila final
            if row:
                buttons.append(row)
            buttons.append([Button.inline("📊 VER TODAS LAS OPCIONES", b"show_all")])
            buttons.append([Button.inline("❌ CANCELAR", b"cancel")])
            
            # Texto informativo
            original_size_str = self.get_file_size(file_size)
            
            menu_text = f"""
🎬 **VIDEO RECIBIDO: {original_size_str}**

📊 **OPCIONES RECOMENDADAS** (basadas en el tamaño):

"""
            
            # Agregar detalles de cada preset recomendado
            for preset_key in recommended_presets:
                preset = self.compression_presets[preset_key]
                estimated_size = self.calculate_estimated_size(file_size, preset_key)
                estimated_size_str = self.get_file_size(estimated_size)
                reduction = (1 - (estimated_size / file_size)) * 100
                
                menu_text += f"""
**{preset['name']}**
├ Tamaño estimado: **{estimated_size_str}**
├ Reducción: **{reduction:.1f}%**
├ Calidad: {preset['quality']}
└ Velocidad: {preset['speed']}
"""
            
            menu_text += "\n_Selecciona una opción:_"
            
            # Guardar información del video pendiente
            self.pending_videos[message.sender_id] = {
                'file_size': file_size,
                'file_path': file_path,
                'message': message
            }
            
            await message.reply(menu_text, buttons=buttons)
            
        except Exception as e:
            logger.error(f"Error mostrando opciones: {e}")
            await message.reply("❌ Error al mostrar opciones de compresión")
    
    async def show_all_options(self, message, file_size):
        """Mostrar todas las opciones disponibles"""
        try:
            buttons = []
            
            for preset_key, preset in self.compression_presets.items():
                estimated_size = self.calculate_estimated_size(file_size, preset_key)
                button_text = f"{preset['name']} (~{self.get_file_size(estimated_size)})"
                button = Button.inline(button_text, f"compress_{preset_key}".encode())
                buttons.append([button])
            
            buttons.append([Button.inline("⬅️ VOLVER", b"back_to_recommended")])
            
            all_options_text = f"""
📋 **TODAS LAS OPCIONES DISPONIBLES**

Tamaño original: **{self.get_file_size(file_size)}**

"""
            for preset_key, preset in self.compression_presets.items():
                estimated_size = self.calculate_estimated_size(file_size, preset_key)
                reduction = (1 - (estimated_size / file_size)) * 100
                
                all_options_text += f"""
**{preset['name']}**
• Tamaño estimado: **{self.get_file_size(estimated_size)}**
• Reducción: **{reduction:.1f}%**  
• Calidad: {preset['quality']}
• Velocidad: {preset['speed']}
"""
            
            await message.edit(all_options_text, buttons=buttons)
            
        except Exception as e:
            logger.error(f"Error mostrando todas las opciones: {e}")
    
    async def handle_button_callback(self, event):
        """Manejar selección de botones"""
        try:
            data = event.data.decode()
            user_id = event.sender_id
            
            if data.startswith("compress_"):
                preset_key = data.replace("compress_", "")
                
                if user_id not in self.pending_videos:
                    await event.answer("❌ No hay video pendiente", alert=True)
                    return
                
                video_info = self.pending_videos[user_id]
                file_size = video_info['file_size']
                
                if preset_key in self.compression_presets:
                    preset = self.compression_presets[preset_key]
                    estimated_size = self.calculate_estimated_size(file_size, preset_key)
                    reduction = (1 - (estimated_size / file_size)) * 100
                    
                    confirm_text = f"""
✅ **CONFIRMACIÓN DE COMPRESIÓN**

🎬 **Video original:** {self.get_file_size(file_size)}
🎛️ **Preset seleccionado:** {preset['name']}

📊 **Resultado estimado:**
• Tamaño final: **{self.get_file_size(estimated_size)}**
• Reducción: **{reduction:.1f}%**
• Calidad: {preset['quality']}
• Velocidad: {preset['speed']}

📝 _{preset['description']}_

⏳ **Tiempo estimado:** {self.estimate_processing_time(file_size, preset_key)}

¿Proceder con la compresión?
                    """
                    
                    buttons = [
                        [Button.inline("✅ SI, COMPRIMIR", f"confirm_{preset_key}".encode())],
                        [Button.inline("❌ NO, CAMBIAR OPCIÓN", b"change_option")]
                    ]
                    
                    await event.edit(confirm_text, buttons=buttons)
                    
                else:
                    await event.answer("❌ Opción no válida", alert=True)
                    
            elif data.startswith("confirm_"):
                preset_key = data.replace("confirm_", "")
                await self.process_video_with_preset(event, preset_key)
                
            elif data == "show_all":
                if user_id in self.pending_videos:
                    file_size = self.pending_videos[user_id]['file_size']
                    await self.show_all_options(await event.get_message(), file_size)
                    
            elif data == "back_to_recommended":
                if user_id in self.pending_videos:
                    file_size = self.pending_videos[user_id]['file_size']
                    message = self.pending_videos[user_id]['message']
                    await self.show_compression_options(message, file_size)
                    
            elif data == "change_option":
                if user_id in self.pending_videos:
                    file_size = self.pending_videos[user_id]['file_size']
                    message = self.pending_videos[user_id]['message']
                    await self.show_compression_options(message, file_size)
                    
            elif data == "cancel":
                if user_id in self.pending_videos:
                    del self.pending_videos[user_id]
                    await event.edit("❌ **Compresión cancelada**\nPuedes enviar otro video cuando quieras.")
                
        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await event.answer("❌ Error procesando selección", alert=True)
    
    def estimate_processing_time(self, file_size, preset_key):
        """Estimar tiempo de procesamiento"""
        base_time = file_size / (10 * 1024 * 1024)  # 10MB por segundo base
        
        speed_factors = {
            'ultra_turbo': 0.5,
            'turbo': 0.7,
            'balanced': 1.0,
            'quality': 1.5, 
            'max_quality': 2.5,
            'audio_only': 0.8
        }
        
        factor = speed_factors.get(preset_key, 1.0)
        estimated_seconds = base_time * factor
        
        if estimated_seconds < 60:
            return f"{estimated_seconds:.0f} segundos"
        else:
            return f"{estimated_seconds/60:.1f} minutos"
    
    async def process_video_with_preset(self, event, preset_key):
        """Procesar video con el preset seleccionado"""
        try:
            user_id = event.sender_id
            
            if user_id not in self.pending_videos:
                await event.answer("❌ No hay video pendiente", alert=True)
                return
            
            video_info = self.pending_videos[user_id]
            file_size = video_info['file_size']
            original_message = video_info['message']
            
            await event.edit("📥 **Descargando video...**")
            
            # Descargar el video
            if not video_info.get('file_path'):
                file_path = await self.download_file(original_message)
                if not file_path:
                    await event.edit("❌ Error al descargar el video")
                    return
                video_info['file_path'] = file_path
            
            file_path = video_info['file_path']
            
            # Comprimir con el preset seleccionado
            await event.edit("⚙️ **Comprimiendo video...**")
            output_path = await self.compress_video_with_preset(file_path, original_message, preset_key)
            
            if not output_path:
                await event.edit("❌ Error en la compresión")
                self.cleanup_files(file_path)
                return
            
            # Subir resultado
            await event.edit("📤 **Subiendo resultado...**")
            success = await self.upload_file(original_message, output_path, preset_key)
            
            # Limpiar
            self.cleanup_files(file_path, output_path)
            if user_id in self.pending_videos:
                del self.pending_videos[user_id]
            
            if success:
                await event.edit("🎉 **¡Proceso completado exitosamente!**")
            else:
                await event.edit("❌ Error al subir el resultado")
                
        except Exception as e:
            logger.error(f"Error procesando video: {e}")
            await event.edit("❌ Error inesperado en el procesamiento")
    
    async def download_file(self, message):
        """Descargar archivo"""
        try:
            temp_dir = tempfile.gettempdir()
            file_name = f"input_{message.id}.mp4"
            file_path = os.path.join(temp_dir, file_name)
            
            await message.download_media(file=file_path)
            return file_path
            
        except Exception as e:
            logger.error(f"Error descargando: {e}")
            return None
    
    async def compress_video_with_preset(self, input_path, message, preset_key):
        """Comprimir video usando el preset seleccionado"""
        try:
            preset = self.compression_presets[preset_key]
            
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, f"compressed_{message.id}.mp4")
            
            input_size = os.path.getsize(input_path)
            
            # Construir comando FFmpeg
            cmd = ['ffmpeg', '-i', input_path]
            
            if preset_key == 'audio_only':
                output_path = output_path.replace('.mp4', '.mp3')
                cmd.extend([
                    '-vn',
                    '-c:a', 'libmp3lame',
                    '-b:a', preset['audio_bitrate'],
                    '-y'
                ])
            else:
                cmd.extend([
                    '-c:v', 'libx264',
                    '-crf', preset['crf'],
                    '-preset', preset['preset'],
                    '-c:a', 'aac',
                    '-b:a', preset['audio_bitrate'],
                    '-movflags', '+faststart',
                ])
                
                if preset['scale'] != 'original':
                    cmd.extend(['-vf', f'scale={preset["scale"]}'])
                
                cmd.append('-y')
            
            cmd.append(output_path)
            
            # Ejecutar FFmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(output_path):
                output_size = os.path.getsize(output_path)
                actual_reduction = (1 - output_size / input_size) * 100
                
                logger.info(f"Compresión exitosa: {input_size} -> {output_size} ({actual_reduction:.1f}%)")
                return output_path
            else:
                logger.error(f"FFmpeg error: {stderr.decode() if stderr else 'Unknown'}")
                return None
                
        except Exception as e:
            logger.error(f"Error comprimiendo: {e}")
            return None
    
    async def upload_file(self, message, file_path, preset_key):
        """Subir archivo comprimido"""
        try:
            preset = self.compression_presets[preset_key]
            file_ext = '.mp3' if preset_key == 'audio_only' else '.mp4'
            file_name = f"compressed_{preset_key}{file_ext}"
            
            if preset_key == 'audio_only':
                await self.client.send_file(
                    message.chat_id,
                    file_path,
                    caption=f"🎵 **Audio Extraído**\nPreset: {preset['name']}",
                    attributes=[DocumentAttributeFilename(file_name=file_name)]
                )
            else:
                await self.client.send_file(
                    message.chat_id,
                    file_path,
                    caption=f"🎥 **Video Comprimido**\nPreset: {preset['name']}",
                    attributes=[
                        DocumentAttributeVideo(
                            duration=0, w=0, h=0,
                            round_message=False, supports_streaming=True
                        ),
                        DocumentAttributeFilename(file_name=file_name)
                    ],
                    force_document=False
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error subiendo: {e}")
            return False
    
    def get_file_size(self, size_bytes):
        """Formatear tamaño de archivo"""
        if size_bytes == 0:
            return "0B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
            
        return f"{size_bytes:.2f} {size_names[i]}"
    
    def cleanup_files(self, *files):
        """Limpiar archivos temporales"""
        for file_path in files:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"Error limpiando {file_path}: {e}")
    
    async def handle_video(self, event):
        """Manejar envío de video"""
        try:
            message = event.message
            
            # Verificar si es video
            if not (message.video or 
                   (message.document and message.document.mime_type and 
                    'video' in message.document.mime_type)):
                return
            
            file_size = message.file.size
            
            # Verificar tamaño
            if file_size > self.max_size:
                await message.reply(f"❌ Archivo muy grande ({self.get_file_size(file_size)})")
                return
            
            # Mostrar opciones de compresión
            await self.show_compression_options(message, file_size)
                
        except Exception as e:
            logger.error(f"Error en handle_video: {e}")
            await event.message.reply("❌ Error inesperado")
    
    async def handle_start(self, event):
        """Manejar comando /start"""
        start_text = """
🎬 **BOT COMPRESOR INTELIGENTE**

¡Hola! Soy un bot que analiza tus videos y te sugiere **la mejor compresión**.

🎯 **Cómo funciona:**
1. **Envías un video** (hasta 2GB)
2. **Yo analizo** el tamaño y te muestro opciones
3. **Ves estimaciones exactas** de tamaño final
4. **Eliges** la compresión que prefieras
5. **Recibes** el resultado optimizado

🚀 **Características:**
• Estimaciones de tamaño **exactas**
• Tiempos de procesamiento **reales**
• Opciones **recomendadas** inteligentemente
• 6 modos de compresión diferentes

📤 **¡Envía un video para comenzar!**
        """
        await event.message.reply(start_text)

    async def run(self):
        """Ejecutar el bot"""
        await self.initialize()
        
        # Registrar manejadores
        self.client.add_event_handler(self.handle_start, events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.handle_button_callback, events.CallbackQuery())
        self.client.add_event_handler(self.handle_video, events.NewMessage(
            func=lambda e: e.message.video or 
            (e.message.document and e.message.document.mime_type and 
             'video' in e.message.document.mime_type))
        )
        
        logger.info("🤖 Bot inteligente iniciado - Análisis por tamaño activo")
        await self.client.run_until_disconnected()

async def main():
    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Variables faltantes: {missing_vars}")
        return
    
    bot = VideoCompressorBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
