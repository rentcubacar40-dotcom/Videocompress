#!/usr/bin/env python3
"""
Bot Compresor de Videos - Edición Profesional
Optimizado para Render 4GB RAM - Compresión máxima con calidad
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
    bitrate_video: str
    descripcion: str
    calidad: str
    velocidad: str
    relacion_tamaño: float
    resoluciones: List[str]

@dataclass
class DatosProgreso:
    etapa: EtapaProcesamiento
    porcentaje: int
    bytes_descargados: int
    bytes_totales: int
    velocidad: float
    tiempo_restante: str
    hora_inicio: datetime

class CompresorVideoProfesional:
    """
    Bot de compresión de videos de alto rendimiento optimizado para Render 4GB RAM
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
        self.trabajos_concurrentes = 3
        self.tamaño_chunk = 128 * 1024  # 128KB para redes lentas
        
        # Gestión de estado
        self.trabajos_activos: Dict[int, Dict] = {}
        self.sesiones_usuario: Dict[int, Dict] = {}
        self.seguimiento_progreso: Dict[int, DatosProgreso] = {}
        self.mensajes_progreso: Dict[int, any] = {}
        
        # Estadísticas del sistema
        self.estadisticas = {
            'trabajos_totales': 0,
            'trabajos_exitosos': 0,
            'trabajos_fallidos': 0,
            'tiempo_compresion_total': 0,
            'hora_inicio': datetime.now()
        }
        
        # Inicializar presets de compresión optimizados
        self.presets = self._inicializar_presets()
        
        # Cliente de Telegram
        self.client = None
        
        logger.info("Compresor de Video Profesional inicializado")

    def _inicializar_presets(self) -> Dict[PresetCompresion, ConfiguracionCompresion]:
        """Inicializar presets de compresión optimizados para reducir tamaño"""
        return {
            PresetCompresion.COMPRESION_MAXIMA: ConfiguracionCompresion(
                nombre="🔥 COMPRESIÓN MÁXIMA",
                crf="38",  # Más alto para mayor compresión
                preset="ultrafast",
                bitrate_audio="48k",
                bitrate_video="500k",
                descripcion="Tamaño mínimo - Ideal para Moodle",
                calidad="Aceptable",
                velocidad="Muy Rápida",
                relacion_tamaño=0.05,  # Solo 5% del tamaño original
                resoluciones=["360p", "480p"]
            ),
            PresetCompresion.BALANCEADO: ConfiguracionCompresion(
                nombre="⚖️ BALANCEADO",
                crf="32",
                preset="superfast",
                bitrate_audio="64k",
                bitrate_video="800k",
                descripcion="Balance perfecto tamaño/calidad",
                calidad="Buena",
                velocidad="Rápida",
                relacion_tamaño=0.10,  # 10% del tamaño original
                resoluciones=["480p", "720p"]
            ),
            PresetCompresion.CALIDAD_OPTIMA: ConfiguracionCompresion(
                nombre="🎨 CALIDAD ÓPTIMA",
                crf="26",
                preset="fast",
                bitrate_audio="96k",
                bitrate_video="1200k",
                descripcion="Buena calidad - Tamaño reducido",
                calidad="Muy Buena",
                velocidad="Media",
                relacion_tamaño=0.20,  # 20% del tamaño original
                resoluciones=["720p"]
            ),
            PresetCompresion.SOLO_AUDIO: ConfiguracionCompresion(
                nombre="🎵 SOLO AUDIO",
                crf="N/A",
                preset="fast",
                bitrate_audio="64k",
                bitrate_video="0k",
                descripcion="Extrae solo el audio - MP3",
                calidad="Audio",
                velocidad="Rápida",
                relacion_tamaño=0.02,  # Solo 2% del tamaño original
                resoluciones=["audio"]
            )
        }

    async def inicializar_cliente(self):
        """Inicializar cliente de Telegram con configuraciones optimizadas"""
        self.client = TelegramClient(
            'sesion_compresor',
            self.api_id,
            self.api_hash,
            connection_retries=8,
            timeout=90,
            request_retries=4
        )
        
        await self.client.start(bot_token=self.bot_token)
        self._configurar_manejadores()
        
        logger.info("Cliente de Telegram inicializado exitosamente")
        await self._notificar_admin("Bot iniciado correctamente")

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

        @self.client.on(events.NewMessage(pattern='/myid'))
        async def manejador_myid(event):
            await self._manejar_comando_myid(event)

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

    async def _notificar_admin(self, mensaje: str):
        """Enviar notificación al administrador"""
        try:
            admin_id = os.getenv('ADMIN_ID')
            if admin_id:
                await self.client.send_message(
                    int(admin_id),
                    f"🤖 **Notificación del Sistema**\n{mensaje}"
                )
        except Exception as e:
            logger.warning(f"No se pudo enviar notificación al admin: {e}")

    async def _manejar_comando_inicio(self, event):
        """Manejar comando /start"""
        mensaje_bienvenida = """
🤖 **Compresor de Videos Profesional**

¡Bienvenido! Soy tu asistente especializado en comprimir videos para plataformas educativas como Moodle.

**🎯 Características:**
• Compresión ultra eficiente
• Progreso en tiempo real
• Soporte para videos hasta 2GB
• Optimizado para subir a Moodle

**📋 Comandos disponibles:**
/start - Mostrar este mensaje
/help - Guía completa de uso
/stats - Estadísticas del sistema
/cancel - Cancelar operación actual
/myid - Obtener tu ID de usuario

**🚀 ¿Cómo usar?**
1. Envíame cualquier video
2. Elige el nivel de compresión
3. Espera el procesamiento
4. Descarga tu video optimizado

¡Envía un video para comenzar!
        """
        await event.reply(mensaje_bienvenida)

    async def _manejar_comando_ayuda(self, event):
        """Manejar comando /help"""
        texto_ayuda = """
📖 **Guía de Usuario - Compresor de Videos**

**🎛️ Niveles de Compresión Disponibles:**

**🔥 COMPRESIÓN MÁXIMA**
- Tamaño mínimo posible
- Ideal para Moodle y plataformas educativas
- Calidad: Aceptable | Velocidad: Muy Rápida
- Tamaño final: ~5% del original

**⚖️ BALANCEADO**
- Balance perfecto entre tamaño y calidad
- Recomendado para la mayoría de casos
- Calidad: Buena | Velocidad: Rápida
- Tamaño final: ~10% del original

**🎨 CALIDAD ÓPTIMA**
- Buena calidad visual
- Tamaño significativamente reducido
- Calidad: Muy Buena | Velocidad: Media
- Tamaño final: ~20% del original

**🎵 SOLO AUDIO**
- Extrae solo el audio del video
- Formato MP3 de alta compresión
- Perfecto para podcasts o audio
- Tamaño final: ~2% del original

**💡 Consejos para Moodle:**
• Usa **COMPRESIÓN MÁXIMA** para archivos muy grandes
• **BALANCEADO** es ideal para la mayoría de videos
• **720p** es suficiente calidad para clases online
        """
        await event.reply(texto_ayuda)

    async def _manejar_comando_estadisticas(self, event):
        """Manejar comando /stats"""
        tiempo_activo = datetime.now() - self.estadisticas['hora_inicio']
        memoria = psutil.Process().memory_info().rss / 1024 / 1024
        
        texto_estadisticas = f"""
📊 **Estadísticas del Sistema**

**📈 Rendimiento:**
• Tiempo activo: {str(tiempo_activo).split('.')[0]}
• Trabajos totales: {self.estadisticas['trabajos_totales']}
• Exitosos: {self.estadisticas['trabajos_exitosos']}
• Fallidos: {self.estadisticas['trabajos_fallidos']}
• Trabajos activos: {len(self.trabajos_activos)}

**💻 Sistema:**
• Uso de memoria: {memoria:.1f} MB
• Uso de CPU: {psutil.cpu_percent()}%
• Uso de disco: {psutil.disk_usage('/').percent}%

**⚙️ Configuración:**
• Tamaño máximo: {self._formatear_tamaño(self.tamaño_maximo)}
• Trabajos concurrentes: {self.trabajos_concurrentes}
        """
        await event.reply(texto_estadisticas)

    async def _manejar_comando_myid(self, event):
        """Manejar comando /myid - Obtener ID de usuario"""
        user_id = event.sender_id
        await event.reply(f"**Tu ID de Telegram es:** `{user_id}`")

    async def _manejar_comando_cancelar(self, event):
        """Manejar comando /cancel"""
        user_id = event.sender_id
        
        if user_id in self.trabajos_activos:
            # Cancelar trabajo activo
            del self.trabajos_activos[user_id]
            if user_id in self.seguimiento_progreso:
                del self.seguimiento_progreso[user_id]
            if user_id in self.mensajes_progreso:
                del self.mensajes_progreso[user_id]
            await event.reply("✅ Operación cancelada exitosamente.")
        else:
            await event.reply("❌ No hay operación activa para cancelar.")

    async def _manejar_mensaje_video(self, event):
        """Manejar mensajes con archivos de video"""
        user_id = event.sender_id
        
        # Verificar si el usuario tiene trabajo activo
        if user_id in self.trabajos_activos:
            await event.reply("⏳ Por favor espera a que tu operación actual termine o usa /cancel")
            return

        mensaje = event.message
        tamaño_archivo = mensaje.file.size
        
        # Validar tamaño del archivo
        if tamaño_archivo > self.tamaño_maximo:
            await mensaje.reply(
                f"❌ **Archivo demasiado grande**\n\n"
                f"**Tamaño actual:** {self._formatear_tamaño(tamaño_archivo)}\n"
                f"**Límite permitido:** {self._formatear_tamaño(self.tamaño_maximo)}\n\n"
                f"Por favor, envía un video más pequeño."
            )
            return

        # Almacenar información del video
        self.sesiones_usuario[user_id] = {
            'tamaño_archivo': tamaño_archivo,
            'mensaje': mensaje,
            'hora_recepcion': datetime.now()
        }

        # Mostrar opciones de compresión
        await self._mostrar_menu_compresion(event, tamaño_archivo)

    async def _mostrar_menu_compresion(self, event, tamaño_archivo: int):
        """Mostrar menú de selección de compresión"""
        botones = []
        
        # Crear botones de presets
        for preset in PresetCompresion:
            config = self.presets[preset]
            
            # Solo mostrar las resoluciones 360p, 480p, 720p según el preset
            if preset == PresetCompresion.COMPRESION_MAXIMA:
                resoluciones_disponibles = ["360p", "480p"]
            elif preset == PresetCompresion.BALANCEADO:
                resoluciones_disponibles = ["480p", "720p"]
            elif preset == PresetCompresion.CALIDAD_OPTIMA:
                resoluciones_disponibles = ["720p"]
            else:  # SOLO_AUDIO
                resoluciones_disponibles = ["audio"]
            
            for resolucion in resoluciones_disponibles:
                tamaño_estimado = int(tamaño_archivo * config.relacion_tamaño)
                etiqueta = f"{config.nombre} {resolucion} (~{self._formatear_tamaño(tamaño_estimado)})"
                datos_callback = f"preset:{preset.value}:{resolucion}"
                botones.append([Button.inline(etiqueta, datos_callback.encode())])
        
        # Agregar botón de cancelar
        botones.append([Button.inline("❌ Cancelar Operación", b"cancel")])
        
        texto_menu = f"""
🎬 **Opciones de Compresión de Video**

**📁 Tamaño original:** {self._formatear_tamaño(tamaño_archivo)}
**⏱️ Tiempo estimado:** {self._estimar_tiempo_procesamiento(tamaño_archivo)}

**Selecciona la calidad deseada:**
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
                partes = datos.split(":")
                preset_clave = partes[1]
                resolucion = partes[2]
                
                info_video = self.sesiones_usuario.get(user_id)
                if not info_video:
                    await event.edit("❌ Sesión expirada. Por favor envía el video nuevamente.")
                    return
                
                # Iniciar procesamiento inmediatamente
                await self._iniciar_trabajo_compresion(event, info_video, preset_clave, resolucion)
                
        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await event.answer("Error procesando la solicitud", alert=True)

    async def _iniciar_trabajo_compresion(self, event, info_video, preset_clave: str, resolucion: str):
        """Iniciar trabajo de compresión de video"""
        user_id = event.sender_id
        
        try:
            # Marcar trabajo como activo
            self.trabajos_activos[user_id] = {
                'hora_inicio': datetime.now(),
                'preset': preset_clave,
                'resolucion': resolucion,
                'mensaje_evento': event
            }
            
            self.estadisticas['trabajos_totales'] += 1
            
            # Inicializar seguimiento de progreso
            self.seguimiento_progreso[user_id] = DatosProgreso(
                etapa=EtapaProcesamiento.DESCARGANDO,
                porcentaje=0,
                bytes_descargados=0,
                bytes_totales=info_video['tamaño_archivo'],
                velocidad=0,
                tiempo_restante="Calculando...",
                hora_inicio=datetime.now()
            )
            
            # Crear mensaje de progreso inicial
            config = self.presets[PresetCompresion(preset_clave)]
            mensaje_progreso = await event.edit(
                f"⚙️ **Iniciando compresión**\n\n"
                f"**Preset:** {config.nombre}\n"
                f"**Resolución:** {resolucion}\n"
                f"**Calidad:** {config.calidad}\n"
                f"**Velocidad:** {config.velocidad}\n\n"
                f"📥 Descargando video... 0%"
            )
            self.mensajes_progreso[user_id] = mensaje_progreso
            
            await self._procesar_pipeline_video(event, info_video, preset_clave, resolucion)
            
        except Exception as e:
            logger.error(f"Error en trabajo de compresión: {e}")
            await event.edit(f"❌ **Error en procesamiento:** {str(e)}")
            self.estadisticas['trabajos_fallidos'] += 1
            
            # Limpiar en caso de fallo
            if user_id in self.trabajos_activos:
                del self.trabajos_activos[user_id]
            if user_id in self.seguimiento_progreso:
                del self.seguimiento_progreso[user_id]
            if user_id in self.mensajes_progreso:
                del self.mensajes_progreso[user_id]

    async def _procesar_pipeline_video(self, event, info_video, preset_clave: str, resolucion: str):
        """Pipeline completo de procesamiento de video"""
        user_id = event.sender_id
        mensaje = info_video['mensaje']
        config = self.presets[PresetCompresion(preset_clave)]
        
        # Generar nombres de archivo únicos
        ruta_entrada = os.path.join(tempfile.gettempdir(), f"entrada_{user_id}_{int(time.time())}.mp4")
        ruta_salida = os.path.join(tempfile.gettempdir(), f"salida_{user_id}_{int(time.time())}.mp4")
        
        try:
            # Etapa 1: Descargar
            await self._actualizar_mensaje_progreso(user_id, "📥 **Descargando video...**\n0%")
            await self._descargar_video(mensaje, ruta_entrada, user_id)
            
            # Etapa 2: Analizar
            await self._actualizar_mensaje_progreso(user_id, "🔍 **Analizando video...**")
            duracion_video = await self._obtener_duracion_video(ruta_entrada)
            
            # Etapa 3: Comprimir
            await self._actualizar_mensaje_progreso(user_id, "🎬 **Comprimiendo video...**\n0%")
            await self._comprimir_video(ruta_entrada, ruta_salida, preset_clave, resolucion, user_id, duracion_video)
            
            # Etapa 4: Subir
            await self._actualizar_mensaje_progreso(user_id, "📤 **Subiendo resultado...**\n0%")
            await self._subir_resultado(event, ruta_salida, preset_clave, resolucion)
            
            # Éxito
            self.estadisticas['trabajos_exitosos'] += 1
            tiempo_trabajo = (datetime.now() - self.trabajos_activos[user_id]['hora_inicio']).total_seconds()
            self.estadisticas['tiempo_compresion_total'] += tiempo_trabajo
            
            tamaño_final = os.path.getsize(ruta_salida) if os.path.exists(ruta_salida) else 0
            reduccion = (1 - (tamaño_final / info_video['tamaño_archivo'])) * 100
            
            await self._actualizar_mensaje_progreso(
                user_id,
                f"✅ **¡Compresión completada!**\n\n"
                f"**Reducción de tamaño:** {reduccion:.1f}%\n"
                f"**Tamaño final:** {self._formatear_tamaño(tamaño_final)}\n"
                f"**Calidad:** {resolucion}\n"
                f"**Tiempo total:** {tiempo_trabajo:.1f}s"
            )
            
        except Exception as e:
            logger.error(f"Error en pipeline: {e}")
            await self._actualizar_mensaje_progreso(user_id, f"❌ **Error en procesamiento:** {str(e)}")
            raise
        finally:
            # Limpiar archivos temporales
            await self._limpiar_archivos([ruta_entrada, ruta_salida])
            
            # Limpiar estado del usuario
            if user_id in self.trabajos_activos:
                del self.trabajos_activos[user_id]
            if user_id in self.seguimiento_progreso:
                del self.seguimiento_progreso[user_id]
            if user_id in self.mensajes_progreso:
                del self.mensajes_progreso[user_id]
            if user_id in self.sesiones_usuario:
                del self.sesiones_usuario[user_id]

    async def _descargar_video(self, mensaje, ruta_entrada: str, user_id: int):
        """Descargar video con seguimiento de progreso"""
        ultima_actualizacion = time.time()
        
        def callback_progreso(actual, total):
            nonlocal ultima_actualizacion
            if time.time() - ultima_actualizacion > 1.0:  # Actualizar cada 1 segundo
                porcentaje = (actual / total) * 100
                asyncio.create_task(self._actualizar_mensaje_progreso(
                    user_id, 
                    f"📥 **Descargando video...**\n{porcentaje:.1f}%"
                ))
                ultima_actualizacion = time.time()
        
        await mensaje.download_media(
            file=ruta_entrada,
            progress_callback=callback_progreso
        )

    async def _comprimir_video(self, ruta_entrada: str, ruta_salida: str, preset_clave: str, 
                             resolucion: str, user_id: int, duracion: float):
        """Comprimir video usando FFmpeg con progreso en tiempo real"""
        config = self.presets[PresetCompresion(preset_clave)]
        
        # Construir comando FFmpeg optimizado para máxima compresión
        if preset_clave == "audio":
            comando = [
                'ffmpeg', '-i', ruta_entrada, '-vn',
                '-c:a', 'libmp3lame', '-b:a', config.bitrate_audio,
                '-y', ruta_salida
            ]
        else:
            comando = [
                'ffmpeg', '-i', ruta_entrada,
                '-c:v', 'libx264', '-crf', config.crf,
                '-preset', config.preset,
                '-c:a', 'aac', '-b:a', config.bitrate_audio,
                '-movflags', '+faststart',
                '-progress', 'pipe:1', '-loglevel', 'error'
            ]
            
            # Aplicar resolución
            if resolucion == "360p":
                comando.extend(['-vf', 'scale=-2:360'])
            elif resolucion == "480p":
                comando.extend(['-vf', 'scale=-2:480'])
            elif resolucion == "720p":
                comando.extend(['-vf', 'scale=-2:720'])
            
            comando.extend(['-y', ruta_salida])
        
        # Ejecutar con seguimiento de progreso
        proceso = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Monitorear progreso
        async for linea in proceso.stdout:
            linea = linea.decode().strip()
            if linea.startswith('out_time='):
                tiempo_actual = self._parsear_tiempo(linea.split('=')[1])
                if duracion > 0:
                    porcentaje = (tiempo_actual / duracion) * 100
                    await self._actualizar_mensaje_progreso(
                        user_id,
                        f"🎬 **Comprimiendo video...**\n{porcentaje:.1f}%"
                    )
        
        await proceso.wait()

    async def _subir_resultado(self, event, ruta_salida: str, preset_clave: str, resolucion: str):
        """Subir archivo comprimido con progreso"""
        user_id = event.sender_id
        
        if not os.path.exists(ruta_salida):
            raise FileNotFoundError("Archivo comprimido no encontrado")
            
        tamaño_archivo = os.path.getsize(ruta_salida)
        config = self.presets[PresetCompresion(preset_clave)]
        
        # Calcular reducción
        tamaño_original = self.sesiones_usuario[user_id]['tamaño_archivo']
        reduccion = (1 - (tamaño_archivo / tamaño_original)) * 100
        
        descripcion = (
            f"**✅ Video Comprimido**\n"
            f"• Preset: {config.nombre}\n"
            f"• Resolución: {resolucion}\n"
            f"• Tamaño: {self._formatear_tamaño(tamaño_archivo)}\n"
            f"• Reducción: {reduccion:.1f}%"
        )
        
        ultima_actualizacion = time.time()
        
        def callback_progreso_subida(actual, total):
            nonlocal ultima_actualizacion
            if time.time() - ultima_actualizacion > 1.0:
                porcentaje = (actual / total) * 100
                asyncio.create_task(self._actualizar_mensaje_progreso(
                    user_id,
                    f"📤 **Subiendo resultado...**\n{porcentaje:.1f}%"
                ))
                ultima_actualizacion = time.time()
        
        # Enviar archivo
        await self.client.send_file(
            event.chat_id,
            ruta_salida,
            caption=descripcion,
            progress_callback=callback_progreso_subida,
            attributes=[
                DocumentAttributeVideo(
                    duration=0,
                    w=0,
                    h=0,
                )
            ] if preset_clave != "audio" else [
                DocumentAttributeAudio(
                    duration=0,
                    title=f"Audio Extraído - {config.nombre}"
                )
            ]
        )

    async def _actualizar_mensaje_progreso(self, user_id: int, mensaje: str):
        """Actualizar mensaje de progreso eficientemente"""
        try:
            if user_id in self.mensajes_progreso:
                await self.mensajes_progreso[user_id].edit(mensaje)
        except Exception as e:
            logger.debug(f"Error actualizando progreso: {e}")

    def _formatear_tamaño(self, tamaño_bytes: int) -> str:
        """Formatear tamaño de archivo en formato legible"""
        if tamaño_bytes == 0:
            return "0B"
        
        unidades = ["B", "KB", "MB", "GB"]
        i = 0
        while tamaño_bytes >= 1024 and i < len(unidades) - 1:
            tamaño_bytes /= 1024.0
            i += 1
            
        return f"{tamaño_bytes:.2f} {unidades[i]}"

    def _estimar_tiempo_procesamiento(self, tamaño_archivo: int) -> str:
        """Estimar tiempo de procesamiento basado en tamaño del archivo"""
        if tamaño_archivo < 50 * 1024 * 1024:  # < 50MB
            return "1-2 minutos"
        elif tamaño_archivo < 200 * 1024 * 1024:  # < 200MB
            return "2-4 minutos"
        elif tamaño_archivo < 500 * 1024 * 1024:  # < 500MB
            return "4-7 minutos"
        elif tamaño_archivo < 1024 * 1024 * 1024:  # < 1GB
            return "7-12 minutos"
        else:  # 1GB+
            return "12-20 minutos"

    def _parsear_tiempo(self, cadena_tiempo: str) -> float:
        """Parsear cadena de tiempo de FFmpeg a segundos"""
        try:
            if ':' in cadena_tiempo:
                partes = cadena_tiempo.split(':')
                if len(partes) == 3:
                    h, m, s = partes
                    return float(h) * 3600 + float(m) * 60 + float(s)
                elif len(partes) == 2:
                    m, s = partes
                    return float(m) * 60 + float(s)
            return float(cadena_tiempo)
        except:
            return 0.0

    async def _obtener_duracion_video(self, ruta_entrada: str) -> float:
        """Obtener duración del video usando FFprobe"""
        try:
            comando = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                ruta_entrada
            ]
            resultado = await asyncio.create_subprocess_exec(
                *comando,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await resultado.communicate()
            return float(stdout.decode().strip())
        except Exception as e:
            logger.warning(f"No se pudo obtener la duración del video: {e}")
            return 0.0

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
        finally:
            logger.info("Bot detenido")

async def main():
    """Punto de entrada de la aplicación"""
    try:
        # Validar disponibilidad de FFmpeg
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
    # Configurar política de event loop para mejor rendimiento
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Ejecutar la aplicación
    asyncio.run(main())
