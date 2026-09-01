"""
Guion Conversacional - Agente IAM (Asistente de IA para el Adulto Mayor).

Flujo conversacional pensado para una persona mayor hablando por voz:
- Saludo cálido
- Pregunta el nombre (cómo prefiere que lo llamen)
- Pregunta la ciudad donde vive (para clima y servicios locales)
- Pasa a la conversación libre, donde IAM ayuda en temas del día a día:
  fecha y hora, clima, indicadores económicos, noticias, música, radio, TV,
  recordatorios y conversación amable.

No se piden documentos ni datos sensibles. El objetivo es acompañar con
calidez, paciencia y un lenguaje muy sencillo.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

# Zona horaria de Colombia (UTC-5)
TZ_COLOMBIA = ZoneInfo("America/Bogota")

# ── Palabras clave para entender la intención del usuario adulto mayor ──
INTENCIONES = {
    "fecha_hora": [
        "qué día es", "que dia es", "qué fecha es", "que fecha es",
        "en qué día estamos", "en que dia estamos", "qué hora es",
        "que hora es", "dime la fecha", "dime la hora", "la fecha",
        "la hora", "el día", "el dia", "qué día", "que dia",
    ],
    "clima": [
        "clima", "tiempo", "temperatura", "va a llover", "hace frío",
        "hace frio", "hace calor", "lluvia", "paraguas", "abrigo",
        "saquito", "sol", "nublado", "pronóstico", "pronostico",
    ],
    "dolar": [
        "dólar", "dolar", "divisas", "divisa", "tasa de cambio",
        "peso colombiano", "el precio del dólar", "el precio del dolar",
        "cuánto está el dólar", "cuanto esta el dolar", "valor del dólar",
    ],
    "euro": [
        "euro", "euros",
    ],
    "cafe": [
        "café", "cafe", "precio del café", "precio del cafe",
        "federación de cafeteros", "federacion de cafeteros",
    ],
    "noticias": [
        "noticias", "noticia", "qué pasó", "que pasó", "que paso",
        "qué sucede", "que sucede", "información de hoy",
        "informacion de hoy", "el noticiero", "última hora",
        "ultima hora", "últimas noticias", "ultimas noticias",
    ],
    "musica": [
        "música", "musica", "canción", "cancion", "cantante",
        "ponme una canción", "ponme una cancion", "quiero escuchar",
        "pon una canción", "pon una cancion", "ponme música",
        "ponme musica", "algo de música", "algo de musica",
    ],
    "radio": [
        "radio", "emisora", "sintonizar", "frecuencia", "la radio",
        "la emisora", "pon la radio", "pon la emisora",
    ],
    "tv": [
        "televisión", "television", "tele", "canal", "programación",
        "programacion", "tv", "ver televisión", "ver television",
        "cambiar el canal", "el canal de noticias", "caracol", "rcn",
    ],
    "emergencia": [
        "me siento mal", "no me siento bien", "me duele", "me caí",
        "me cai", "dolor fuerte", "auxilio", "ayuda por favor",
        "emergencia", "no puedo respirar", "me estoy ahogando",
        "emergencia médica", "emergencia medica", "llama a mi hijo",
        "llama a mi hija", "necesito ayuda urgente",
    ],
    "conversacion": [
        "estoy solo", "estoy sola", "me siento solo", "me siento sola",
        "soledad", "triste", "tristeza", "solo quiero hablar",
        "solo quiero conversar", "me aburro",
        "hablemos", "conversemos",
    ],
    "despedida": [
        "adiós", "adios", "chao", "hasta luego", "nos vemos",
        "gracias eso es todo", "eso es todo", "muchas gracias",
        "ya no necesito nada", "ya está", "ya esta", "bye",
    ],
}


def clasificar_intencion(texto):
    """Clasifica la intención del usuario adulto mayor según palabras clave.
    Retorna la primera intención que coincida, o None si no hay coincidencia.
    """
    if not texto:
        return None
    texto_norm = texto.lower().strip()
    for intencion, palabras in INTENCIONES.items():
        for palabra in palabras:
            if palabra in texto_norm:
                return intencion
    return None


PASOS = {
    "saludo_inicial": {
        "id": "saludo_inicial",
        "siguiente": "conversacion_libre",
        "mensaje": (
            "¡Hola! Qué gusto saludarte. Dime, ¿en qué te puedo colaborar hoy?"
        ),
        "validar": None,
        "botones": None,
    },
    "ofrecer_ayuda": {
        "id": "ofrecer_ayuda",
        "siguiente": "conversacion_libre",
        "mensaje": None,  # Se calcula dinámicamente
        "validar": None,
        "botones": None,
    },
    "conversacion_libre": {
        "id": "conversacion_libre",
        "siguiente": "conversacion_libre",
        "mensaje": None,
        "validar": None,
        "botones": None,
    },
    "despedida": {
        "id": "despedida",
        "siguiente": None,
        "mensaje": (
            "Ha sido un gusto acompañarle. "
            "Recuerde que aquí estoy siempre que me necesite. "
            "Que tenga un día muy bonito y no olvide tomar sus aguas."
        ),
        "validar": None,
        "botones": None,
    },
}


def obtener_paso(paso_id):
    """Obtiene un paso del guion por su ID."""
    return PASOS.get(paso_id)


def formatear_mensaje(paso, datos):
    """Formatea el mensaje del paso con los datos del usuario."""
    mensaje = paso.get("mensaje", "")
    if mensaje is None:
        return ""
    try:
        return mensaje.format(**datos)
    except KeyError:
        return mensaje


def obtener_momento_del_dia():
    """Retorna la parte variable del saludo para usar con templates.
    Ejemplo: 'tardes' para usar en 'Buenas {momento_del_dia}'.
    """
    hora = datetime.now(TZ_COLOMBIA).hour
    if 6 <= hora < 12:
        return "días"
    elif 12 <= hora < 18:
        return "tardes"
    else:
        return "noches"


def obtener_dia_semana():
    """Retorna el nombre del día de la semana en español."""
    dias = [
        "lunes", "martes", "miércoles", "jueves",
        "viernes", "sábado", "domingo",
    ]
    return dias[datetime.now(TZ_COLOMBIA).weekday()]


def obtener_mes():
    """Retorna el nombre del mes en español."""
    meses = [
        "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return meses[datetime.now(TZ_COLOMBIA).month]


def obtener_fecha_completa():
    """Retorna la fecha completa en lenguaje natural para voz."""
    ahora = datetime.now(TZ_COLOMBIA)
    return (
        f"{obtener_dia_semana()} {ahora.day} de {obtener_mes()} de {ahora.year}"
    )


def obtener_hora_actual():
    """Retorna la hora actual en lenguaje natural para voz."""
    ahora = datetime.now(TZ_COLOMBIA)
    hora = ahora.hour
    minutos = ahora.minute
    if hora == 1:
        hora_str = "la una"
    elif hora == 0:
        hora_str = "las doce de la noche"
    elif hora < 12:
        hora_str = f"las {hora} de la mañana"
    elif hora == 12:
        hora_str = "las doce del mediodía"
    elif hora < 19:
        hora_str = f"las {hora - 12} de la tarde"
    else:
        hora_str = f"las {hora - 12} de la noche"
    if minutos == 0:
        return f"Son {hora_str} en punto."
    if minutos == 1:
        return f"Es {hora_str} y un minuto."
    return f"Son {hora_str} y {minutos} minutos."


def validar_nombre(respuesta):
    """Valida el nombre del usuario de forma amable y paciente."""
    MENSAJE = (
        "No alcancé a escuchar bien su nombre. "
        "¿Podría repetirlo con calma después de la señal, por favor?"
    )
    if not respuesta:
        return False, MENSAJE
    respuesta = respuesta.strip()
    respuesta = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\s]", "", respuesta).strip()
    if len(respuesta) < 2:
        return False, MENSAJE
    if not re.search(r"[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ]", respuesta):
        return False, MENSAJE
    if respuesta.replace(" ", "").isdigit():
        return False, MENSAJE
    nombre_limpio = " ".join(p.capitalize() for p in respuesta.split())
    return True, nombre_limpio


def validar_ciudad(respuesta):
    """Valida la ciudad de forma flexible (palabras)."""
    MENSAJE = (
        "No escuché bien la ciudad. ¿Me la repite con calma, por favor? "
        "Solo dígame el nombre de la ciudad donde vive."
    )
    if not respuesta:
        return False, MENSAJE
    respuesta = respuesta.strip()
    respuesta = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ\s]", "", respuesta).strip()
    if len(respuesta) < 2:
        return False, MENSAJE
    if not re.search(r"[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ]", respuesta):
        return False, MENSAJE
    ciudad_limpia = " ".join(p.capitalize() for p in respuesta.split())
    return True, ciudad_limpia


def validar_respuesta(paso, respuesta):
    """Valida la respuesta del usuario segun el tipo de campo."""
    tipo = paso.get("validar")
    if tipo is None:
        return True, respuesta
    if tipo == "nombre":
        return validar_nombre(respuesta)
    if tipo == "ciudad":
        return validar_ciudad(respuesta)
    return True, respuesta
