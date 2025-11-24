#!/usr/bin/env python3
"""
Bot Compresor de Videos - Edición Profesional
Optimizado para Render 4GB RAM - Compresión inteligente
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

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv()

# Configurar logging profesional
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('compression_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("CompresorVideo")

# Importar Telethon
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeFilename, DocumentAttributeAudio

class PresetCompresion(Enum):
    COMPRESION_MAXIMA = "maxima"
    BALANCEADO = "balanceado" 
    CALIDAD_OPTIMA = "calidad"
    SOLO_AUDIO = "audio"

class EtapaProcesamiento(Enum):
    DESCARGANDO = "📥 DESCARGANDO"
    ANALIZANDO = "🔍 ANALIZANDO"
    COMPRIMIENDO = "🎬 COMPRIMIENDO"
    SUBIENDO = "📤 SUBIENDO"

@dataclass
class ConfiguracionCompresion:
    nombre: str
    crf: str
    preset: str
    bitrate_audio: str
    descripcion: str
    calidad: str
    velocidad: str

class CompresorVideoProfesional:
    """
    Bot de compresión de videos de alto rendimiento
    """
    
    def __init__(self):
        # Validar variables de entorno
        self.api_id = int(os.getenv('API_ID', 0))
        self.api_hash = os.getenv('API_HASH', '')
        self.bot_token = os.getenv('BOT_TOKEN', '')
        
        if not all([self.api_id, self.api_hash, self.bot_token]):
            raise ValueError("Faltan variables de entorno: API_ID, API_HASH, BOT_TOKEN")
        
        # Configuración de rendimiento
        self.tamaño_maximo = 2 * 1024 * 1024 * 1024  # 2GB
        self.trabajos_concurrentes = 2
        
        # Gestión de estado
        self.trabajos_activos: Dict[int, Dict] = {}
        self.sesiones_usuario: Dict[int, Dict] = {}
        
        # Estadísticas del sistema
        self.estadisticas = {
            'trabajos_totales': 0,
            'trabajos_exitosos': 0,
            'trabajos_fallidos': 0,
            'hora_inicio': datetime.now()
        }
        
        # Inicializar presets de compresión
        self.presets = self._inicializar_presets()
        
        # Cliente de Telegram
        self.client = None
        
        logger.info("Compresor de Video Profesional inicializado")

    def _inicializar_presets(self) -> Dict[PresetCompresion, ConfiguracionCompresion]:
        """Inicializar presets de compresión"""
        return {
            PresetCompresion.COMPRESION_MAXIMA: ConfiguracionCompresion(
                nombre="🔥 COMPRESIÓN MÁXIMA",
                crf="38",
                preset="ultrafast", 
                bitrate_audio="64k",
                descripcion="Tamaño mínimo posible",
                calidad="360p",
                velocidad="Muy Rápida"
            ),
            PresetCompresion.BALANCEADO: ConfiguracionCompresion(
                nombre="⚖️ BALANCEADO",
                crf="32",
                preset="superfast",
                bitrate_audio="96k",
                descripcion="Balance tamaño/calidad",
                calidad="480p", 
                velocidad="Rápida"
            ),
            PresetCompresion.CALIDAD_OPTIMA: ConfiguracionCompresion(
                nombre="🎨 CALIDAD ÓPTIMA",
                crf="28",
                preset="fast",
                bitrate_audio="128k",
                descripcion="Buena calidad visual",
                calidad="720p",
                velocidad="Media"
            ),
            PresetCompresion.SOLO_AUDIO: ConfiguracionCompresion(
                nombre="🎵 SOLO AUDIO",
                crf="0",
                preset="fast",
                bitrate_audio="128k",
                descripcion="Extrae solo audio MP3",
                calidad="Audio",
                velocidad="Rápida"
            )
        }

    def _calcular_tamaño_estimado(self, tamaño_original: int, preset: PresetCompresion) -> int:
        """Calcular tamaño estimado basado en el preset"""
        ratios = {
            PresetCompresion.COMPRESION_MAXIMA: 0.15,  # 15% del original
            PresetCompresion.BALANCEADO: 0.25,         # 25% del original  
            PresetCompresion.CALIDAD_OPTIMA: 0.40,     # 40% del original
            PresetCompresion.SOLO_AUDIO: 0.05          # 5% del original
        }
        return int(tamaño_original * ratios[preset])

    async def inicializar_cliente(self):
        """Inicializar cliente de Telegram"""
        self.client = TelegramClient(
            'sesion_compresor',
            self.api_id,
            self.api_hash
        )
        
        await self.client.start(bot_token=self.bot_token)
        self._configurar_manejadores()
        
        logger.info("Cliente de Telegram inicializado exitosamente")

    def _configurar_manejadores(self):
        """Configurar todos los manejadores de eventos"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def manejador_inicio(event):
            await self._manejar_comando_inicio(event)

        @self.client.on(events.NewMessage(pattern='/help'))
        async def manejador_ayuda(event):
            await self._manejar_comando_ayuda(event)

        @self.client.on(events.NewMessage(pattern='/stats'))
        async def manejador_estadisticas(event):
            await self._manejar_comando_estadisticas(event)

        @self.client.on(events.NewMessage(pattern='/cancel'))
        async def manejador_cancelar(event):
            await self._manejar_comando_cancelar(event)

        @self.client.on(events.NewMessage(
            func=lambda e: e.message.video or (
                e.message.document and 
                e.message.document.mime_type and 
                'video' in e.message.document.mime_type
            )
        ))
        async def manejador_video(event):
            await self._manejar_mensaje_video(event)

        @self.client.on(events.CallbackQuery())
        async def manejador_callback(event):
            await self._manejar_consulta_callback(event)

    async def _manejar_comando_inicio(self, event):
        """Manejar comando /start"""
        mensaje_bienvenida = """
🤖 **Compresor de Videos Profesional**

¡Bienvenido! Envíame un video y lo comprimiré para que ocupe menos espacio.

**🚀 Características:**
• Compresión inteligente
• Múltiples opciones de calidad
• Progreso en tiempo real
• Soporte para videos hasta 2GB

**📋 Comandos:**
/start - Mostrar este mensaje
/help - Guía de uso
/stats - Estadísticas
/cancel - Cancelar operación

¡Envía un video para comenzar!
        """
        await event.reply(mensaje_bienvenida)

    async def _manejar_comando_ayuda(self, event):
        """Manejar comando /help"""
        texto_ayuda = """
📖 **Guía de Usuario**

**🎛️ Opciones de Compresión:**

**🔥 COMPRESIÓN MÁXIMA**
- Tamaño más pequeño posible
- Calidad: 360p
- Ideal para ahorrar espacio

**⚖️ BALANCEADO** 
- Buen balance tamaño/calidad
- Calidad: 480p
- Recomendado para la mayoría

**🎨 CALIDAD ÓPTIMA**
- Buena calidad visual
- Calidad: 720p  
- Tamaño reducido

**🎵 SOLO AUDIO**
- Extrae solo el audio
- Formato MP3
- Perfecto para podcasts
        """
        await event.reply(texto_ayuda)

    async def _manejar_comando_estadisticas(self, event):
        """Manejar comando /stats"""
        tiempo_activo = datetime.now() - self.estadisticas['hora_inicio']
        
        texto_estadisticas = f"""
📊 **Estadísticas del Sistema**

**📈 Rendimiento:**
• Tiempo activo: {str(tiempo_activo).split('.')[0]}
• Trabajos totales: {self.estadisticas['trabajos_totales']}
• Exitosos: {self.estadisticas['trabajos_exitosos']}
• Fallidos: {self.estadisticas['trabajos_fallidos']}
• Trabajos activos: {len(self.trabajos_activos)}
        """
        await event.reply(texto_estadisticas)

    async def _manejar_comando_cancelar(self, event):
        """Manejar comando /cancel"""
        user_id = event.sender_id
        
        if user_id in self.trabajos_activos:
            del self.trabajos_activos[user_id]
            await event.reply("✅ Operación cancelada.")
        else:
            await event.reply("❌ No hay operación activa.")

    async def _manejar_mensaje_video(self, event):
        """Manejar mensajes con videos"""
        user_id = event.sender_id
        
        # Verificar si el usuario tiene trabajo activo
        if user_id in self.trabajos_activos:
            await event.reply("⏳ Ya tienes un proceso en curso. Espera a que termine.")
            return

        mensaje = event.message
        tamaño_archivo = mensaje.file.size
        
        # Validar tamaño del archivo
        if tamaño_archivo > self.tamaño_maximo:
            await mensaje.reply(
                f"❌ **Archivo demasiado grande**\n\n"
                f"Tamaño: {self._formatear_tamaño(tamaño_archivo)}\n"
                f"Límite: {self._formatear_tamaño(self.tamaño_maximo)}"
            )
            return

        # Almacenar información del video
        self.sesiones_usuario[user_id] = {
            'tamaño_archivo': tamaño_archivo,
            'mensaje': mensaje
        }

        # Mostrar opciones de compresión
        await self._mostrar_menu_compresion(event, tamaño_archivo)

    async def _mostrar_menu_compresion(self, event, tamaño_archivo: int):
        """Mostrar menú de selección de compresión"""
        botones = []
        
        # Crear botones de presets con tamaños estimados REALES
        for preset in PresetCompresion:
            config = self.presets[preset]
            tamaño_estimado = self._calcular_tamaño_estimado(tamaño_archivo, preset)
            
            etiqueta = f"{config.nombre} (~{self._formatear_tamaño(tamaño_estimado)})"
            datos_callback = f"preset:{preset.value}"
            botones.append([Button.inline(etiqueta, datos_callback.encode())])
        
        # Agregar botón de cancelar
        botones.append([Button.inline("❌ Cancelar", b"cancel")])
        
        texto_menu = f"""
🎬 **Opciones de Compresión**

**📁 Tamaño original:** {self._formatear_tamaño(tamaño_archivo)}

Selecciona el nivel de compresión:
        """
        
        await event.reply(texto_menu, buttons=botones)

    async def _manejar_consulta_callback(self, event):
        """Manejar consultas de callback de botones"""
        user_id = event.sender_id
        datos = event.data.decode()
        
        try:
            await event.answer()  # Responder callback inmediatamente
            
            if datos == "cancel":
                if user_id in self.trabajos_activos:
                    del self.trabajos_activos[user_id]
                await event.edit("❌ Operación cancelada.")
                return
                
            elif datos.startswith("preset:"):
                preset_clave = datos.split(":")[1]
                
                info_video = self.sesiones_usuario.get(user_id)
                if not info_video:
                    await event.edit("❌ Sesión expirada. Envía el video nuevamente.")
                    return
                
                # Iniciar procesamiento
                await self._iniciar_trabajo_compresion(event, info_video, preset_clave)
                
        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await event.answer("Error procesando la solicitud", alert=True)

    async def _iniciar_trabajo_compresion(self, event, info_video, preset_clave: str):
        """Iniciar trabajo de compresión de video"""
        user_id = event.sender_id
        
        try:
            # Marcar trabajo como activo
            self.trabajos_activos[user_id] = {
                'hora_inicio': datetime.now(),
                'preset': preset_clave
            }
            
            self.estadisticas['trabajos_totales'] += 1
            
            # Editar mensaje para mostrar que comenzó
            config = self.presets[PresetCompresion(preset_clave)]
            mensaje_progreso = await event.edit(
                f"⚙️ **Iniciando compresión...**\n\n"
                f"**Preset:** {config.nombre}\n"
                f"**Calidad:** {config.calidad}\n"
                f"**Descargando video...**"
            )
            
            await self._procesar_video(event, info_video, preset_clave, mensaje_progreso)
            
        except Exception as e:
            logger.error(f"Error en trabajo de compresión: {e}")
            await event.edit(f"❌ **Error:** {str(e)}")
            self.estadisticas['trabajos_fallidos'] += 1
            if user_id in self.trabajos_activos:
                del self.trabajos_activos[user_id]

    async def _procesar_video(self, event, info_video, preset_clave: str, mensaje_progreso):
        """Procesar video completo"""
        user_id = event.sender_id
        mensaje = info_video['mensaje']
        config = self.presets[PresetCompresion(preset_clave)]
        
        try:
            # Generar nombres de archivo únicos
            ruta_entrada = os.path.join(tempfile.gettempdir(), f"entrada_{user_id}_{int(time.time())}.mp4")
            ruta_salida = os.path.join(tempfile.gettempdir(), f"salida_{user_id}_{int(time.time())}.mp4")
            
            # Etapa 1: Descargar (CORREGIDO)
            await mensaje_progreso.edit("📥 **Descargando video...**\n0%")
            await self._descargar_video_simple(mensaje, ruta_entrada, mensaje_progreso)
            
            # Etapa 2: Comprimir
            await mensaje_progreso.edit("🎬 **Comprimiendo video...**\n0%")
            await self._comprimir_video(ruta_entrada, ruta_salida, preset_clave, mensaje_progreso)
            
            # Etapa 3: Subir
            await mensaje_progreso.edit("📤 **Subiendo resultado...**")
            await self._subir_resultado(event, ruta_salida, preset_clave)
            
            # Éxito
            self.estadisticas['trabajos_exitosos'] += 1
            tiempo_trabajo = (datetime.now() - self.trabajos_activos[user_id]['hora_inicio']).total_seconds()
            
            tamaño_final = os.path.getsize(ruta_salida) if os.path.exists(ruta_salida) else 0
            reduccion = ((info_video['tamaño_archivo'] - tamaño_final) / info_video['tamaño_archivo']) * 100
            
            await mensaje_progreso.edit(
                f"✅ **¡Compresión completada!**\n\n"
                f"**Reducción:** {reduccion:.1f}%\n"
                f"**Tiempo:** {tiempo_trabajo:.1f}s\n"
                f"**Calidad:** {config.calidad}"
            )
            
        except Exception as e:
            logger.error(f"Error en procesamiento: {e}")
            await mensaje_progreso.edit(f"❌ **Error en procesamiento:** {str(e)}")
            raise
        finally:
            # Limpiar archivos temporales
            await self._limpiar_archivos([ruta_entrada, ruta_salida])
            
            # Limpiar estado del usuario
            if user_id in self.trabajos_activos:
                del self.trabajos_activos[user_id]
            if user_id in self.sesiones_usuario:
                del self.sesiones_usuario[user_id]

    async def _descargar_video_simple(self, mensaje, ruta_entrada: str, mensaje_progreso):
        """Descargar video de forma simple y confiable"""
        try:
            # Descargar sin callback de progreso (más confiable)
            await mensaje.download_media(file=ruta_entrada)
            
            # Verificar que se descargó correctamente
            if os.path.exists(ruta_entrada) and os.path.getsize(ruta_entrada) > 0:
                await mensaje_progreso.edit("✅ **Video descargado correctamente**\n🎬 Comprimiendo...")
                return True
            else:
                raise Exception("El archivo no se descargó correctamente")
                
        except Exception as e:
            logger.error(f"Error en descarga: {e}")
            raise Exception(f"Error descargando el video: {str(e)}")

    async def _comprimir_video(self, ruta_entrada: str, ruta_salida: str, preset_clave: str, mensaje_progreso):
        """Comprimir video usando FFmpeg"""
        config = self.presets[PresetCompresion(preset_clave)]
        
        # Construir comando FFmpeg
        if preset_clave == "audio":
            comando = [
                'ffmpeg', '-i', ruta_entrada, '-vn',
                '-c:a', 'libmp3lame', '-b:a', config.bitrate_audio,
                '-y', ruta_salida
            ]
        else:
            # Determinar resolución basada en el preset
            if preset_clave == "maxima":
                resolucion = "360"
            elif preset_clave == "balanceado":
                resolucion = "480" 
            else:  # calidad
                resolucion = "720"
                
            comando = [
                'ffmpeg', '-i', ruta_entrada,
                '-c:v', 'libx264', '-crf', config.crf,
                '-preset', config.preset,
                '-c:a', 'aac', '-b:a', config.bitrate_audio,
                '-vf', f'scale=-2:{resolucion}',
                '-movflags', '+faststart',
                '-y', ruta_salida
            ]
        
        # Ejecutar compresión
        try:
            proceso = await asyncio.create_subprocess_exec(
                *comando,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await proceso.wait()
            
            if not os.path.exists(ruta_salida) or os.path.getsize(ruta_salida) == 0:
                raise Exception("La compresión falló - archivo de salida vacío")
                
        except Exception as e:
            logger.error(f"Error en compresión: {e}")
            raise Exception(f"Error comprimiendo el video: {str(e)}")

    async def _subir_resultado(self, event, ruta_salida: str, preset_clave: str):
        """Subir archivo comprimido"""
        if not os.path.exists(ruta_salida):
            raise FileNotFoundError("Archivo comprimido no encontrado")
            
        tamaño_archivo = os.path.getsize(ruta_salida)
        config = self.presets[PresetCompresion(preset_clave)]
        
        descripcion = (
            f"**✅ Video Comprimido**\n"
            f"• Preset: {config.nombre}\n" 
            f"• Calidad: {config.calidad}\n"
            f"• Tamaño: {self._formatear_tamaño(tamaño_archivo)}"
        )
        
        # Enviar archivo
        await self.client.send_file(
            event.chat_id,
            ruta_salida,
            caption=descripcion,
            attributes=[
                DocumentAttributeVideo(
                    duration=0,
                    w=0,
                    h=0,
                )
            ] if preset_clave != "audio" else [
                DocumentAttributeAudio(
                    duration=0,
                    title=f"Audio Extraído"
                )
            ]
        )

    def _formatear_tamaño(self, tamaño_bytes: int) -> str:
        """Formatear tamaño de archivo en formato legible"""
        if tamaño_bytes == 0:
            return "0B"
        
        unidades = ["B", "KB", "MB", "GB"]
        i = 0
        while tamaño_bytes >= 1024 and i < len(unidades) - 1:
            tamaño_bytes /= 1024.0
            i += 1
            
        return f"{tamaño_bytes:.1f} {unidades[i]}"

    async def _limpiar_archivos(self, rutas_archivos: List[str]):
        """Limpiar archivos temporales"""
        for ruta in rutas_archivos:
            try:
                if os.path.exists(ruta):
                    os.remove(ruta)
            except Exception as e:
                logger.debug(f"No se pudo eliminar {ruta}: {e}")

    async def ejecutar(self):
        """Bucle principal de ejecución del bot"""
        try:
            await self.inicializar_cliente()
            logger.info("Bot ejecutándose...")
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Bot falló: {e}")
            raise

async def main():
    """Punto de entrada de la aplicación"""
    try:
        # Validar FFmpeg
        resultado = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if resultado.returncode != 0:
            logger.error("FFmpeg no encontrado. Por favor instala FFmpeg.")
            return
        
        # Crear y ejecutar bot
        bot = CompresorVideoProfesional()
        await bot.ejecutar()
        
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
