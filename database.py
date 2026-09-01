"""
Módulo Supabase - Base de datos en la nube para IAM.

Almacena datos básicos del adulto mayor (nombre, ciudad) y el historial
de conversaciones para personalizar la atención y guardar recordatorios.
No se almacenan datos sensibles (números de tarjeta, claves, contraseñas).
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_supabase = None


def get_supabase():
    """Obtiene cliente Supabase (singleton)."""
    global _supabase
    if _supabase is not None:
        return _supabase

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("SUPABASE_URL/SUPABASE_KEY no configuradas - modo sin BD")
        return None

    try:
        from supabase import create_client

        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase conectado correctamente")
        return _supabase
    except Exception as e:
        logger.error(f"Error conectando Supabase: {e}")
        return None


def guardar_usuario(datos):
    """
    Guarda o actualiza un adulto mayor en la tabla 'usuarios'.
    datos: dict con campos del adulto mayor (nombre, email opcional, ciudad, preferencias).
    Retorna (True, id) o (False, error).
    """
    sb = get_supabase()
    if sb is None:
        return False, "Supabase no disponible"

    try:
        registro = {
            "nombre": datos.get("nombre", ""),
            "email": datos.get("email", ""),
            "telefono": datos.get("telefono", ""),
            "ciudad": datos.get("ciudad", ""),
            "preferencias": datos.get("preferencias", ""),
            "paso_actual": datos.get("paso_actual", ""),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Si hay email, usamos upsert por email; si no, insert simple.
        if registro["email"]:
            result = sb.table("usuarios").upsert(
                registro, on_conflict="email"
            ).execute()
        else:
            result = sb.table("usuarios").insert(registro).execute()

        user_id = None
        if hasattr(result, "data") and result.data:
            user_id = result.data[0].get("id")

        logger.info(f"Usuario guardado: {registro['nombre']}")
        return True, user_id

    except Exception as e:
        logger.error(f"Error guardando usuario: {e}")
        return False, str(e)


def guardar_recordatorio(datos):
    """
    Guarda un recordatorio personal del adulto mayor (cita médica,
    cumpleaños, medicamento, evento familiar, etc.).
    datos: dict con usuario_nombre, titulo, fecha (YYYY-MM-DD), hora opcional,
           descripcion opcional, tipo opcional.
    Retorna (True, id) o (False, error).
    """
    sb = get_supabase()
    if sb is None:
        return False, "Supabase no disponible"

    try:
        registro = {
            "usuario_nombre": datos.get("usuario_nombre", datos.get("nombre", "")),
            "usuario_email": datos.get("usuario_email", datos.get("email", "")),
            "titulo": datos.get("titulo", ""),
            "descripcion": datos.get("descripcion", ""),
            "fecha": datos.get("fecha", ""),
            "hora": datos.get("hora", ""),
            "tipo": datos.get("tipo", "otro"),
            "estado": datos.get("estado", "activo"),
            "created_at": datetime.utcnow().isoformat(),
        }

        result = sb.table("recordatorios").insert(registro).execute()

        recordatorio_id = None
        if hasattr(result, "data") and result.data:
            recordatorio_id = result.data[0].get("id")

        logger.info(
            f"Recordatorio guardado: {registro['titulo']} ({registro['fecha']}) "
            f"para {registro['usuario_nombre']}"
        )
        return True, recordatorio_id

    except Exception as e:
        logger.error(f"Error guardando recordatorio: {e}")
        return False, str(e)


def obtener_recordatorios_usuario(nombre):
    """
    Obtiene los recordatorios activos de un adulto mayor por nombre.
    Retorna lista de dicts.
    """
    sb = get_supabase()
    if sb is None:
        return []

    try:
        result = (
            sb.table("recordatorios")
            .select("*")
            .eq("usuario_nombre", nombre)
            .eq("estado", "activo")
            .order("fecha", desc=False)
            .execute()
        )
        if hasattr(result, "data"):
            return result.data
        return []
    except Exception as e:
        logger.error(f"Error obteniendo recordatorios: {e}")
        return []


def guardar_conversacion(datos):
    """
    Guarda registro de la conversación con IAM en 'conversaciones'.
    datos: dict con campos de la conversación.
    Retorna (True, id) o (False, error).
    """
    sb = get_supabase()
    if sb is None:
        return False, "Supabase no disponible"

    try:
        registro = {
            "usuario_nombre": datos.get("nombre", ""),
            "usuario_ciudad": datos.get("ciudad", ""),
            "mensaje_usuario": datos.get("mensaje_usuario", ""),
            "respuesta_agente": datos.get("respuesta_agente", ""),
            "paso": datos.get("paso", ""),
            "created_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"guardar_conversacion: registro={registro}")
        result = sb.table("conversaciones").insert(registro).execute()
        logger.info(
            f"guardar_conversacion: result.data={result.data if hasattr(result, 'data') else 'no data attr'}"
        )

        conv_id = None
        if hasattr(result, "data") and result.data:
            conv_id = result.data[0].get("id")

        return True, conv_id

    except Exception as e:
        logger.error(f"Error guardando conversación: {e}")
        return False, str(e)


def guardar_consulta_adicional(datos):
    """
    Guarda una consulta adicional en 'consultas_adicionales'.
    """
    sb = get_supabase()
    if sb is None:
        return False, "Supabase no disponible"

    try:
        registro = {
            "usuario_nombre": datos.get("nombre", ""),
            "usuario_ciudad": datos.get("ciudad", ""),
            "consulta": datos.get("consulta", ""),
            "created_at": datetime.utcnow().isoformat(),
        }

        result = sb.table("consultas_adicionales").insert(registro).execute()

        consulta_id = None
        if hasattr(result, "data") and result.data:
            consulta_id = result.data[0].get("id")

        return True, consulta_id

    except Exception as e:
        logger.error(f"Error guardando consulta adicional: {e}")
        return False, str(e)


def obtener_usuario(nombre_o_email):
    """
    Obtiene un adulto mayor por nombre o email.
    Retorna dict con datos o None.
    """
    sb = get_supabase()
    if sb is None:
        return None

    try:
        if "@" in nombre_o_email:
            result = (
                sb.table("usuarios").select("*").eq("email", nombre_o_email).execute()
            )
        else:
            result = (
                sb.table("usuarios").select("*").eq("nombre", nombre_o_email).execute()
            )
        if hasattr(result, "data") and result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error obteniendo usuario: {e}")
        return None


def obtener_usuario_por_telefono(telefono):
    """
    Obtiene un adulto mayor por número de teléfono (si lo proporcionó).
    Retorna dict con datos o None.
    """
    sb = get_supabase()
    if sb is None:
        return None

    try:
        result = sb.table("usuarios").select("*").eq("telefono", telefono).execute()
        if hasattr(result, "data") and result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error obteniendo usuario por telefono: {e}")
        return None


def guardar_llamada(datos):
    """
    Guarda un registro de sesión de voz con IAM en la tabla 'llamadas'.
    """
    sb = get_supabase()
    if sb is None:
        return False, "Supabase no disponible"

    try:
        registro = {
            "usuario_nombre": datos.get("nombre", ""),
            "usuario_ciudad": datos.get("ciudad", ""),
            "duracion_segundos": datos.get("duracion_segundos", 0),
            "paso_final": datos.get("paso_final", ""),
            "estado": datos.get("estado", "completada"),
            "created_at": datetime.utcnow().isoformat(),
        }

        result = sb.table("llamadas").insert(registro).execute()

        llamada_id = None
        if hasattr(result, "data") and result.data:
            llamada_id = result.data[0].get("id")

        logger.info(
            f"Sesion de voz guardada: {registro['usuario_nombre']} "
            f"({registro['duracion_segundos']}s)"
        )
        return True, llamada_id

    except Exception as e:
        logger.error(f"Error guardando sesion de voz: {e}")
        return False, str(e)
