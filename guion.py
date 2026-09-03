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
        "la hora", "qué día", "que dia",
        "qué hora", "que hora", "qué horas son", "que horas son",
        "qué día de la semana", "que dia de la semana",
        "estamos a qué día", "estamos a que dia",
        "en qué fecha estamos", "en que fecha estamos",
        "qué día es hoy", "que dia es hoy",
        "a qué hora", "a que hora",
    ],
    "clima": [
        "clima", "tiempo", "temperatura", "va a llover", "hace frío",
        "hace frio", "hace calor", "lluvia", "paraguas", "abrigo",
        "saquito", "hace sol", "nublado", "pronóstico", "pronostico",
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
        "últimas novedades", "ultimas novedades", "novedades",
        "qué hay de nuevo", "que hay de nuevo", "qué hay nuevo",
        "que hay nuevo", "cuéntame las noticias", "cuentame las noticias",
        "dame las noticias", "dime las noticias", "me das las noticias",
        "qué se sabe", "que se sabe", "qué hay en colombia", "que hay en colombia",
        "actualidad", "resumen del día", "resumen del dia", "resumen de hoy",
        "qué ocurre", "que ocurre", "hoy en las noticias",
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
        "me desmayé", "me desmaye", "me sangra mucho",
        "me estoy desangrando", "me ahogo", "no me da el aire",
        "no respiro", "me morí", "ayuda ya", "por favor vengan",
        "vengan rápido", "socorro",
    ],
    "salud": [
        "presión", "presion", "tensión", "tension", "tensiómetro",
        "tensiometro", "presión arterial", "presion arterial",
        "me tomé la presión", "me tome la presion", "tengo la presión",
        "está alta la presión", "esta alta la presion",
        "está baja la presión", "esta baja la presion",
        "frecuencia cardíaca", "frecuencia cardiaca", "latidos",
        "corazón rápido", "corazon rapido", "corazón lento",
        "corazon lento", "pulso", "oxímetro", "oximetro",
        "saturación", "saturacion", "oxígeno", "oxigeno",
        "glucosa", "azúcar", "azucar", "glicemia", "hemoglobina",
        "temperatura", "fiebre", "tengo fiebre", "me siento afiebrado",
        "termómetro", "termometro",
        "medicamento", "medicamentos", "pastilla", "pastillas",
        "remedio", "remedios", "dosis", "tomo pastillas",
        "recordar medicamento", "recordatorio pastilla",
        "diabetes", "hipertensión", "hipertension", "corazón enfermo",
        "colesterol", "tiroides",
        "qué significa", "que significa", "qué es", "que es",
        "tengo dolor", "me duele mucho", "me duele la cabeza",
        "me duele el pecho", "me duele la espalda",
    ],
    "brigadista": [
        "terremoto", "temblor", "sismo", "sacudida", "tembló", "temblo",
        "temblando", "se mueve todo", "se está moviendo",
        "se esta moviendo", "incendio", "fuego", "se quemó", "se quemo",
        "humo", "inundación", "inundacion", "se inundó", "se inundo",
        "agua en la calle", "aguacero fuerte", "desbordamiento",
        "deslave", "deslizamiento", "tormenta", "huracán", "huracan",
        "kit de emergencia", "mochila de emergencia", "maletín de emergencia",
        "maletin de emergencia",
        "número de emergencia", "numero de emergencia", "línea 123",
        "linea 123", "a quién llamo", "a quien llamo", "a quién llamo si",
        "a quien llamo si", "bomberos", "policía", "policia",
        "ambulancia", "cruz roja", "defensa civil",
        "qué hago si tiembla", "que hago si tiembla",
        "qué hago si hay temblor", "que hago si hay temblor",
        "cómo me preparo", "como me preparo",
        "evacuar", "evacuación", "evacuacion", "salida de emergencia",
        "ruta de escape",
        # Primeros auxilios
        "rcp", "reanimación", "reanimacion", "cómo se hace rcp",
        "como se hace rcp", "masaje cardíaco", "masaje cardiaco",
        "paro cardíaco", "paro cardiaco", "ahogamiento",
        "se ahogó", "se ahogo", "ven un perro", "ven un perro",
        "mordió", "mordio", "mordedura",
        "qué hago si", "que hago si",
    ],
    "hogar": [
        "se fundió el foco", "se fundio el foco", "cambiar foco",
        "cambiar bombilla", "cambiar bombillo", "no enciende la luz",
        "no hay luz", "se fue la luz", "se fue la energia",
        "se fue la energía", "breaker", "interruptor", "flipón",
        "flipon", "caja de breakers", "resetear breaker",
        "se rompió una tubería", "se rompio una tuberia",
        "se rompió la tubería", "se rompio la tuberia",
        "se rompió una pipa", "se rompio una pipa",
        "tubería rota", "tuberia rota", "tubería dañada", "tuberia danada",
        "se dañó", "se dano", "se averió", "se averio",
        "fuga de agua", "fuga en el baño", "gotea", "goteo",
        "agua en el piso", "inundación en casa", "inundacion en casa",
        "está inundando", "esta inundando", "inunda", "anegado",
        "destapando", "destapador", "destape", "sifón", "sifon",
        "problema con el wifi", "no me conecta el wifi",
        "no me conecta el internet", "se cayó el internet",
        "se cayo el internet", "no funciona el control",
        "no enciende la tele", "no enciende el tv", "control remoto",
        "no suena el timbre", "timbre", "puerta atascada",
        "se trabó la puerta", "se trabo la puerta", "cerradura",
        "cómo me conecto", "como me conecto", "cómo pongo el wifi",
        "como pongo el wifi", "contraseña del wifi", "contraseña wifi",
        "olvidé la clave", "olvide la clave", "olvidé la contraseña",
        "olvide la contrasena",
        "caí", "me cai", "me caí en la casa", "me cai en la casa",
        "prevenir caídas", "prevenir caidas", "tapete", "pasamano",
        "pasamanos", "barandal", "escalera",
        "eléctrico", "electrico", "enchufe", "toma", "toma corriente",
        "toma de corriente", "no sirve la estufa", "estufa",
        "refrigerador", "nevera", "lavadora",
    ],
    "conversacion": [
        "estoy solo", "estoy sola", "me siento solo", "me siento sola",
        "me siento muy sola", "me siento muy solo",
        "me siento tan sola", "me siento tan solo",
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


# ── Ciudades principales de Colombia (para detectar la ciudad en el
# mensaje del usuario cuando pregunta el clima, etc.) ────────────────
# Diccionario normalizado -> nombre bonito. La lista interna incluye
# variantes sin acento y en minúsculas para hacer match robusto.
_CIUDADES_VARIANTES = [
    ("bogotá", "Bogotá"),
    ("bogota", "Bogotá"),
    ("medellín", "Medellín"),
    ("medellin", "Medellín"),
    ("cali", "Cali"),
    ("barranquilla", "Barranquilla"),
    ("cartagena", "Cartagena"),
    ("cúcuta", "Cúcuta"),
    ("cucuta", "Cúcuta"),
    ("bucaramanga", "Bucaramanga"),
    ("pereira", "Pereira"),
    ("manizales", "Manizales"),
    ("ibagué", "Ibagué"),
    ("ibague", "Ibagué"),
    ("neiva", "Neiva"),
    ("villavicencio", "Villavicencio"),
    ("pasto", "Pasto"),
    ("montería", "Montería"),
    ("monteria", "Montería"),
    ("sincelejo", "Sincelejo"),
    ("popayán", "Popayán"),
    ("popayan", "Popayán"),
    ("valledupar", "Valledupar"),
    ("tunja", "Tunja"),
    ("riohacha", "Riohacha"),
    ("quibdó", "Quibdó"),
    ("quibdo", "Quibdó"),
    ("armenia", "Armenia"),
    ("palmira", "Palmira"),
    ("buenaventura", "Buenaventura"),
    ("tuluá", "Tuluá"),
    ("tulua", "Tuluá"),
    ("duitama", "Duitama"),
    ("sogamoso", "Sogamoso"),
    ("yopal", "Yopal"),
    ("florencia", "Florencia"),
    ("mocoa", "Mocoa"),
    ("arauca", "Arauca"),
    ("leticia", "Leticia"),
    ("mitú", "Mitú"),
    ("mitu", "Mitú"),
    ("san andrés", "San Andrés"),
    ("san andres", "San Andrés"),
    ("providencia", "Providencia"),
    ("santa marta", "Santa Marta"),
    ("santamarta", "Santa Marta"),
    ("tumaco", "Tumaco"),
    ("ipiales", "Ipiales"),
    ("soacha", "Soacha"),
    ("zipaquirá", "Zipaquirá"),
    ("zipaquira", "Zipaquirá"),
    ("girón", "Girón"),
    ("giron", "Girón"),
    ("barrancabermeja", "Barrancabermeja"),
    ("chía", "Chía"),
    ("chia", "Chía"),
    ("mosquera", "Mosquera"),
    ("facatativá", "Facatativá"),
    ("facatativa", "Facatativá"),
    ("funza", "Funza"),
    ("madrid", "Madrid"),
    ("cajicá", "Cajicá"),
    ("cajica", "Cajicá"),
    ("melgar", "Melgar"),
    ("girardot", "Girardot"),
    ("fusagasugá", "Fusagasugá"),
    ("fusagasuga", "Fusagasugá"),
    # Algunas ciudades grandes de Latinoamérica y otros países por si
    # el usuario vive en otra ciudad.
    ("lima", "Lima"),
    ("quito", "Quito"),
    ("santiago", "Santiago"),
    ("buenos aires", "Buenos Aires"),
    ("ciudad de méxico", "Ciudad de México"),
    ("caracas", "Caracas"),
    ("la paz", "La Paz"),
    ("montevideo", "Montevideo"),
    ("asunción", "Asunción"),
    ("asuncion", "Asunción"),
    ("guayaquil", "Guayaquil"),
    ("san josé", "San José"),
    ("san jose", "San José"),
    ("panamá", "Panamá"),
    ("panama", "Panamá"),
    ("barcelona", "Barcelona"),
    ("miami", "Miami"),
    ("orlando", "Orlando"),
    ("nueva york", "Nueva York"),
    ("new york", "Nueva York"),
]
# Lista para el patrón regex (ordenada por longitud descendente para
# que las ciudades compuestas matcheen antes que sus prefijos).
_CIUDADES_NORM = sorted([v[0] for v in _CIUDADES_VARIANTES], key=len, reverse=True)
# Mapa de nombre normalizado -> nombre bonito.
_CIUDADES_NORM_TO_BONITO = {v[0]: v[1] for v in _CIUDADES_VARIANTES}


def detectar_ciudad_en_texto(texto):
    """Busca el nombre de una ciudad conocida dentro del texto.
    Devuelve el nombre bonito de la ciudad detectado o None si no
    encuentra ninguna. Solo usamos esta función para detectar
    ciudades mencionadas explícitamente por el usuario.
    """
    if not texto:
        return None
    texto_norm = texto.lower().strip()
    for ciudad in _CIUDADES_NORM:
        patron = r"(?:^|\b)" + re.escape(ciudad) + r"(?:\b|$)"
        if re.search(patron, texto_norm):
            return _CIUDADES_NORM_TO_BONITO[ciudad]
    return None


PASOS = {
    "saludo_inicial": {
        "id": "saludo_inicial",
        "siguiente": "conversacion_libre",
        "mensaje": (
            "Hola. ¿En qué le puedo ayudar hoy?"
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
            "Aquí estaré siempre que me necesite. "
            "Que le vaya bien."
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
