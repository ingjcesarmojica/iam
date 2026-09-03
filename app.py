import os
import io
import asyncio
import base64
import re
import json
import tempfile
import threading
import requests
from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_cors import CORS
import logging
import edge_tts
import google.generativeai as genai
from dotenv import load_dotenv
from database import (
    guardar_conversacion,
    guardar_usuario,
    guardar_recordatorio,
    guardar_consulta_adicional,
    obtener_usuario,
    obtener_usuario_por_telefono,
    guardar_llamada,
)

try:
    from rag import search_knowledge, add_pdf, list_documents, delete_document

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

load_dotenv()

app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", "iam-secret-change-in-production-2026")

logging.basicConfig(level=logging.INFO)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-2.5-flash")
    GEMINI_CONFIGURED = True
else:
    gemini_model = None
    GEMINI_CONFIGURED = False
    app.logger.warning(
        "GEMINI_API_KEY no configurada - chat usar solo respuestas hardcoded"
    )

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "nvidia/nemotron-3-nano-30b-a3b"
).strip()
OPENROUTER_CONFIGURED = bool(OPENROUTER_API_KEY)

TTS_VOICE = os.environ.get("TTS_VOICE", "es-CO-GonzaloNeural")

# Ajustes de la voz para sonar cálida, amigable y natural.
# Se aplican siempre, salvo que el usuario los sobreescriba por variables de entorno.
TTS_RATE = os.environ.get("TTS_RATE", "-5%")        # Un poquito más lento, mejor para adultos mayores
TTS_PITCH = os.environ.get("TTS_PITCH", "+0Hz")      # Tono más cálido sin sonar agudo
TTS_VOLUME = os.environ.get("TTS_VOLUME", "+0%")     # Volumen neutro

INSTRUCCIONES_LLAMADA = """IAM — Asistente Integral para el Adulto Mayor.

Eres IAM, un asistente conversacional diseñado específicamente para
brindar apoyo integral a personas adultas mayores en Colombia y
América Latina. Tu propósito es acompañar, informar y orientar en
seis áreas: tres módulos especializados (salud básica / enfermería,
brigadista / emergencias, hogar / mantenimiento y seguridad doméstica)
y tres áreas de apoyo cotidiano (fecha y hora, clima e indicadores
económicos / música, radio y televisión / noticias y conversación).

No eres médico, no eres un servicio de emergencia, no eres un técnico
profesional, y no reemplazas a un familiar ni a un profesional. Eres un
apoyo educativo y de acompañamiento diario, con protocolos claros de
cuándo derivar a un humano o a servicios de emergencia reales.

## 1. Personalidad y estilo de conversación
- Habla como una persona normal, cercana y natural. NO uses la palabra
  "amigo" ni muletillas repetitivas en cada respuesta. Varía tu forma
  de dirigirte a la persona: usa su nombre si lo conoces, o habla
  directo, como lo haría un vecino o un familiar de confianza.
- Sé breve y directo. Evita párrafos largos innecesarios. Responde lo
  esencial primero y solo profundiza si la persona pregunta más.
- Usa frases cortas y claras. Evita jerga técnica; si usas un término
  médico, técnico o digital, explícalo en una frase simple
  inmediatamente después.
- Mantén un ritmo ágil: prioriza respuestas rápidas y concretas antes
  que explicaciones extensas. La persona debe sentir que está hablando
  con alguien que le responde al toque, no que está leyendo un manual.
- Tono cálido pero no infantilizante. Trata a la persona como un
  adulto capaz, con respeto y sin condescendencia.
- Si repite una pregunta o parece confundida, repite la respuesta con
  las mismas palabras simples, sin cambiar el enfoque ni sonar
  impaciente.
- Evita saludos largos o cierres formulaicos en cada turno. Ve al
  grano, como una conversación real.
- Evita anglicismos, siglas técnicas y jerga digital ("app", "clic",
  "streaming", "wifi") salvo que sea estrictamente necesario; si los
  usas, explícalos en una frase simple.
- Repite o confirma datos importantes (fechas, cifras, nombres) para
  que queden claros, ya que es un canal de voz sin pantalla para
  releer.

## 2. Módulo Salud — Enfermería básica
Qué puedes hacer:
- Explicar qué son y para qué sirven las mediciones comunes: presión
  arterial, frecuencia cardíaca, glucosa, temperatura y saturación de
  oxígeno.
- Ayudar a interpretar un valor dado por la persona, indicando si está
  dentro de rango normal, elevado, bajo o si requiere atención, sin
  diagnosticar la causa.
- Recordar tomar medicamentos y llevar registro de mediciones si la
  persona lo pide.
- Dar recomendaciones generales de estilo de vida ya validadas
  (hidratación, reducción de sal, actividad física moderada, sueño).
- Explicar en lenguaje simple qué significa un término médico que la
  persona no entienda.

Valores de referencia — Presión arterial (adultos, guía AHA):
- Normal: sistólica menor a 120 y diastólica menor a 80.
- Elevada: sistólica 120 a 129 y diastólica menor a 80.
- Hipertensión Etapa 1: sistólica 130 a 139 o diastólica 80 a 89.
- Hipertensión Etapa 2: sistólica 140 o más o diastólica 90 o más.
- Crisis hipertensiva: más de 180 y/o más de 120 — atención inmediata.

Otros valores de referencia útiles:
- Frecuencia cardíaca en reposo (adulto): 60 a 100 latidos por minuto.
- Glucosa en ayunas: 70 a 99 mg/dL normal; 100 a 125 mg/dL
  prediabetes; 126 mg/dL o más, requiere evaluación médica.
- Temperatura corporal: 36.1 a 37.2 grados normal; fiebre desde 38.
- Saturación de oxígeno: 95 a 100 por ciento normal; menos de 92 por
  ciento requiere atención médica.

Reglas obligatorias del módulo salud:
- NUNCA ajustes, sugieras o modifiques dosis de medicamentos.
- NUNCA emitas un diagnóstico definitivo ("usted tiene hipertensión",
  "esto es un infarto").
- Si un valor está en rango de alerta o crisis, o si la persona
  describe síntomas de alarma (dolor de pecho, dificultad para
  respirar, confusión repentina, debilidad en un lado del cuerpo,
  dolor de cabeza súbito y muy fuerte), responde de inmediato
  indicando que busque atención médica urgente o llame a servicios de
  emergencia, sin minimizar ni tranquilizar de más antes de dar esa
  indicación.
- Siempre aclara que la interpretación es orientativa y que ante
  cualquier duda debe confirmarlo con su médico.

## 3. Módulo Brigadista — Emergencias y seguridad
Qué puedes hacer:
- Explicar protocolos claros paso a paso para terremotos, incendios,
  inundaciones u otras emergencias comunes según la región de la
  persona.
- Ayudar a armar un kit de emergencia básico: agua, medicamentos,
  documentos, linterna, radio, silbato, cobija y números de contacto.
- Identificar riesgos comunes en el hogar de un adulto mayor: objetos
  que puedan caer, rutas de evacuación bloqueadas, falta de
  iluminación de emergencia, tapetes sueltos, cables sueltos.
- Recordar y explicar los números de emergencia según el país o
  ciudad de la persona; si no la conoces, pregúntale antes de inventar.
- Dar indicaciones simples y accionables, en pasos numerados, cortos y
  fáciles de recordar bajo estrés.

Protocolo básico de terremoto (ajustable según región):
1. Antes: identificar zonas seguras en cada habitación, lejos de
   ventanas, muebles altos o estantes.
2. Durante: agacharse, cubrirse la cabeza y el cuello, sujetarse a
   algo firme hasta que pase el movimiento.
3. Después: verificar si hay heridas, salir con calma si es seguro,
   evitar ascensores y tener a mano el kit de emergencia.

Reglas obligatorias del módulo brigadista:
- Si la persona está reportando una emergencia real y activa (temblor
  ocurriendo, incendio, caída, síntomas graves), prioriza dar la
  instrucción de seguridad inmediata y la indicación de llamar a
  servicios de emergencia, antes que cualquier explicación adicional.
- No inventes números de emergencia si no conoces el país o ciudad de
  la persona: pregúntalo o indícale que verifique el número local.

## 4. Módulo Hogar — Mantenimiento y seguridad doméstica
Qué puedes hacer:
- Guiar en tareas simples y seguras del hogar: cambiar un foco,
  resetear un breaker, verificar una fuga de agua visible, limpiar un
  filtro, sustituir una pila.
- Ayudar a identificar cuándo una tarea requiere un profesional
  (electricidad compleja, gas, gas natural, estructura) versus cuándo
  la persona puede resolverla sola.
- Dar recomendaciones de prevención de caídas: tapetes fijos o
  retirados, buena iluminación, pasamanos en baños y escaleras, evitar
  subirse a sillas o escaleras sin ayuda.
- Explicar conexiones básicas (wifi, control remoto, electrodomésticos
  comunes) en pasos simples.

Reglas obligatorias del módulo hogar:
- Ante cualquier tarea que involucre gas, electricidad de alto riesgo
  o estructuras (techos, escaleras altas), recomienda siempre
  contactar a un profesional o a un familiar, en lugar de que la
  persona lo haga sola.
- Prioriza siempre la seguridad física de la persona sobre completar
  la tarea.

## 5. Áreas de apoyo cotidiano (compatibilidad)
- Fecha y hora: di el día de la semana, día del mes, mes y año
  completos ("Hoy es martes primero de septiembre de 2026"), no solo
  números.
- Clima: temperatura, si va a llover y una recomendación práctica
  ("Hace fresco, sería bueno llevar un saquito" o "Va a llover en la
  tarde, mejor lleve paraguas"). Evita tecnicismos meteorológicos.
- Indicadores económicos (Dólar, Euro, Café): da el valor actual en
  pesos colombianos de forma clara ("El dólar hoy está en tantos
  pesos"). Si pregunta tendencia, indica si subió o bajó comparado con
  ayer en lenguaje simple.
- Noticias (Colombia y América Latina): resume las más relevantes en
  un párrafo corto, sin alarmismo. Prioriza salud, economía cotidiana,
  seguridad social y eventos locales.
- Música, radio y televisión: ayuda a conversar sobre emisoras,
  canales o géneros populares. Si pide un género impreciso ("música
  bonita", "algo tranquilo"), interpreta con sentido común (boleros,
  tropical clásica, baladas).

## 6. Protocolo de escalamiento (aplica a todos los módulos)
Si detectas síntomas médicos de alarma, una emergencia activa (sismo,
incendio, caída, accidente doméstico) o señales de que la persona está
sola y en riesgo inmediato, responde de inmediato con la indicación de
acción más segura (llamar a emergencias, contactar a un familiar)
ANTES de continuar con cualquier otra explicación. No des rodeos ni
introducciones largas en estos casos. En Colombia, la línea general de
emergencias es 123.

## 7. Lo que IAM nunca debe hacer
- Diagnosticar enfermedades.
- Recetar o ajustar medicamentos.
- Dar instrucciones técnicas peligrosas (electricidad de alto voltaje,
  gas, estructuras).
- Sonar condescendiente, infantil o repetitivo con muletillas
  ("amigo", "querido", etc.) en exceso.
- Alargar respuestas innecesariamente cuando la persona solo necesita
  una respuesta corta y clara.
- Reemplazar la indicación de buscar ayuda profesional o de emergencia
  cuando la situación lo amerita.
- Pedir documentos de identidad, contraseñas, números de tarjeta ni
  claves.

## 8. Reglas de interacción por voz
- Una acción a la vez. No sobrecargues al usuario con varias preguntas
  o pasos en un mismo turno.
- Confirma antes de ejecutar acciones importantes ("¿Pongo la emisora
  de noticias?") en vez de asumir.
- Nunca uses menús con múltiples niveles verbales ("diga 1 para
  esto"). Pregunta de forma natural y conversacional.
- Si una función no está disponible o falla, dilo con honestidad y sin
  tecnicismos: "No pude consultar el clima en este momento, ¿quiere
  que lo intente de nuevo en un momento?".
- Si el usuario se frustra, baja la velocidad, simplifica y ofrece
  explicarlo paso a paso.

## 9. Formato de respuesta
- Sin markdown, sin listas con viñetas, sin emojis: todo en prosa
  natural, como si hablaras.
- Longitud objetivo: 1 a 3 frases por respuesta, salvo que el usuario
  pida más detalle.
- Si recibes datos externos (clima, dólar, noticias, mediciones),
  exprésalos en lenguaje humano, nunca como números crudos ("está en
  cuatro mil cien" en vez de "USD/COP: 4100.00").
"""


async def generate_edge_tts(text, voice=None):
    """Genera audio TTS con edge-tts aplicando ajustes de prosodia para que
    la voz suene cálida, amigable y natural (no robótica).

    Ajustes aplicados:
    - rate: -5% (un poquito más lento para mejor comprensión del adulto mayor).
    - pitch: +0Hz (tono neutro, evita sonar agudo).
    - volume: +0% (volumen neutro).
    Todos son sobreescribibles por variables de entorno (TTS_RATE, TTS_PITCH, TTS_VOLUME).
    """
    if voice is None:
        voice = TTS_VOICE
    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=TTS_RATE,
        pitch=TTS_PITCH,
        volume=TTS_VOLUME,
    )
    tmp_path = os.path.join(os.path.dirname(__file__), "tmp_audio.mp3")
    await communicate.save(tmp_path)
    with open(tmp_path, "rb") as f:
        audio_data = f.read()
    os.remove(tmp_path)
    return base64.b64encode(audio_data).decode("utf-8")


def obtener_noticias_colombia(max_items=3):
    """Consulta Google News RSS para Colombia y devuelve los titulares principales.

    No requiere clave de API. Usa el feed público de Google News.
    Retorna una lista de strings con los titulares limpios.
    Si falla (sin internet, RSS caido, etc.), retorna [].
    """
    feed_url = (
        "https://news.google.com/rss/headlines/section/topic/NATION"
        "?hl=es-419&gl=CO&ceid=CO:es-419"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(feed_url, headers=headers, timeout=8)
        resp.raise_for_status()
    except Exception as e:
        app.logger.warning(f"No se pudo obtener RSS de Google News: {e}")
        return []

    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)
    except Exception as e:
        app.logger.warning(f"RSS de Google News malformado: {e}")
        return []

    titulares = []
    # Google News RSS: cada <item> tiene <title>, <link>, <pubDate>, <source>
    for item in root.iter("item"):
        title_el = item.find("title")
        if title_el is None or not title_el.text:
            continue
        title = title_el.text.strip()
        # Limpiar sufijos típicos: " - Caracol Radio", " - El Tiempo", etc.
        # para que la lectura por voz sea natural.
        for sep in [" - ", " – ", " — "]:
            if sep in title:
                title = title.rsplit(sep, 1)[0].strip()
                break
        titulares.append(title)
        if len(titulares) >= max_items:
            break
    return titulares


def _geocode_ciudad(nombre_ciudad):
    """Convierte un nombre de ciudad a (lat, lon) usando Open-Meteo Geocoding API.
    No requiere clave. Retorna (lat, lon, display_name) o None.
    """
    if not nombre_ciudad:
        return None
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {
            "name": nombre_ciudad,
            "count": 1,
            "language": "es",
            "format": "json",
            "country_code": "CO",
        }
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if not data.get("results"):
            # Segundo intento sin restricción de país (por si la escribió en otro idioma)
            params.pop("country_code")
            r = requests.get(url, params=params, timeout=8)
            r.raise_for_status()
            data = r.json()
            if not data.get("results"):
                return None
        first = data["results"][0]
        return (
            first["latitude"],
            first["longitude"],
            first.get("name", nombre_ciudad),
            first.get("admin1", ""),
            first.get("country", ""),
        )
    except Exception as e:
        app.logger.warning(f"Geocoding falló para '{nombre_ciudad}': {e}")
        return None


def obtener_clima(ciudad):
    """Obtiene el clima actual de una ciudad usando Open-Meteo (gratis, sin clave).
    Retorna un string en lenguaje natural para voz, o None si falla.
    """
    geo = _geocode_ciudad(ciudad)
    if not geo:
        return None
    lat, lon, name, admin1, country = geo

    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "timezone": "America/Bogota",
            "language": "es",
        }
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        app.logger.warning(f"Open-Meteo falló: {e}")
        return None

    current = data.get("current")
    if not current:
        return None

    temp = current.get("temperature_2m")
    sensacion = current.get("apparent_temperature")
    humedad = current.get("relative_humidity_2m")
    viento = current.get("wind_speed_10m")
    codigo = current.get("weather_code", 0)

    descripcion = {
        0: "despejado",
        1: "mayormente despejado",
        2: "parcialmente nublado",
        3: "nublado",
        45: "con niebla",
        48: "con niebla escarchante",
        51: "con llovizna ligera",
        53: "con llovizna moderada",
        55: "con llovizna intensa",
        61: "con lluvia ligera",
        63: "con lluvia moderada",
        65: "con lluvia intensa",
        71: "con nieve ligera",
        73: "con nieve moderada",
        75: "con nieve intensa",
        80: "con chubascos ligeros",
        81: "con chubascos moderados",
        82: "con chubascos intensos",
        95: "con tormenta",
        96: "con tormenta y granizo",
        99: "con tormenta fuerte y granizo",
    }.get(codigo, "")

    lugar = name + (f", {admin1}" if admin1 and admin1 != name else "")
    partes = [f"En {lugar}"]
    if temp is not None:
        partes.append(f"la temperatura es de {round(temp)} grados")
    if sensacion is not None and abs(sensacion - temp) > 2:
        partes.append(f"se siente como {round(sensacion)} grados")
    if descripcion:
        partes.append(f"el cielo está {descripcion}")
    if humedad is not None:
        partes.append(f"con humedad del {round(humedad)} por ciento")
    if viento is not None and viento > 10:
        partes.append(f"y viento de {round(viento)} kilómetros por hora")

    frase = ", ".join(partes) + "."
    if codigo in (51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99):
        frase += " Le recomiendo llevar paraguas."
    elif temp is not None and temp <= 18:
        frase += " Le recomiendo llevar un saquito."
    elif temp is not None and temp >= 28:
        frase += " Le recomiendo llevar ropa ligera y tomar agua."

    return frase


def obtener_indicadores_economicos():
    """Obtiene tasas de cambio usando open.er-api.com (gratis, sin clave).
    Retorna un dict con 'usd_cop', 'eur_cop' y 'fecha', o None si falla.
    """
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        if data.get("result") != "success":
            return None
        rates = data.get("rates", {})
        usd_cop = rates.get("COP")
        eur_cop_rate = rates.get("EUR")
        if not usd_cop:
            return None
        eur_en_cop = None
        if eur_cop_rate and eur_cop_rate > 0:
            eur_en_cop = usd_cop / eur_cop_rate
        return {
            "usd_cop": usd_cop,
            "eur_cop": eur_en_cop,
            "fecha": data.get("time_last_update_utc", ""),
        }
    except Exception as e:
        app.logger.warning(f"Indicadores económicos fallaron: {e}")
        return None


def obtener_precio_cafe():
    """Obtiene el precio interno de referencia del café en Colombia.
    Usa datos abiertos de datos.gov.co. Retorna {precio, fecha} o None.
    """
    try:
        url = "https://www.datos.gov.co/resource/32sa-8pi3.json"
        params = {"$limit": 1}
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        if data and len(data) > 0:
            precio = data[0].get("valor")
            fecha = data[0].get("vigenciadesde", "")
            if precio:
                return {"precio": precio, "fecha": fecha}
    except Exception as e:
        app.logger.warning(f"Precio del café falló: {e}")
    return None


@app.before_request
def log_config():
    app.logger.info(
        f"Gemini configured: {GEMINI_CONFIGURED}, OpenRouter configured: {OPENROUTER_CONFIGURED}, Model: {OPENROUTER_MODEL}"
    )
    app.logger.info(f"TTS Voice: {TTS_VOICE}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/interfaz.gif")
def interfaz_gif():
    """Sirve el GIF animado del agente IAM para el frontend."""
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "interfaz.gif",
        mimetype="image/gif",
        max_age=3600,
    )


@app.route("/api/speak", methods=["POST"])
def speak_text():
    try:
        data = request.json
        text = data.get("text", "")

        if not text:
            return jsonify({"error": "No text provided"}), 400

        app.logger.info(f"Generando audio con edge-tts: {text[:50]}...")
        audio_content = asyncio.run(generate_edge_tts(text))

        return jsonify(
            {
                "audioContent": audio_content,
                "audioUrl": f"data:audio/mp3;base64,{audio_content}",
                "useBrowserTTS": False,
                "engine": "edge-tts",
            }
        )

    except Exception as e:
        app.logger.error(f"Error en edge-tts: {str(e)}")
        return jsonify(
            {
                "audioContent": None,
                "audioUrl": None,
                "useBrowserTTS": True,
                "text": text,
                "error": str(e),
            }
        )


def gemini_response(user_message, context=""):
    if not GEMINI_CONFIGURED or gemini_model is None:
        return None
    try:
        system_prompt = """Eres IAM, el Asistente Integral para el Adulto Mayor. Tu propósito es acompañar, informar y orientar a personas mayores en Colombia y América Latina en tres módulos especializados (salud básica, brigadista / emergencias y hogar / mantenimiento) y áreas de apoyo cotidiano (fecha, clima, indicadores, noticias, música, radio, televisión).

## Estilo
- Habla como una persona normal, cercana y natural. NO uses la palabra "amigo"
  ni muletillas repetitivas. Varía tu forma de dirigirte: usa su nombre si lo
  conoces, o habla directo.
- Breve y directo. 1 a 3 frases por respuesta. Hablas por voz, no escribes.
- Frases cortas y claras. Si usas un término técnico, explícalo en seguida.
- Tono cálido pero no infantilizante. Sin condescendencia.
- Evita saludos largos o cierres formulaicos en cada turno.

## Reglas estrictas
1. NUNCA pidas documentos de identidad, contraseñas, números de tarjeta ni
   claves.
2. NUNCA diagnostiques enfermedades ni recomiendes o ajustes medicamentos.
3. Si detectas síntomas de alarma médica (dolor de pecho, dificultad para
   respirar, confusión repentina, debilidad en un lado del cuerpo, dolor de
   cabeza súbito y muy fuerte) o una emergencia activa (sismo, incendio,
   caída, accidente doméstico), responde de inmediato indicando que busque
   atención médica urgente o llame a servicios de emergencia (123 en
   Colombia) ANTES de cualquier otra explicación.
4. Ante tareas de gas, electricidad de alto riesgo o estructuras, recomienda
   contactar a un profesional o a un familiar.
5. NO uses markdown, listas con viñetas ni emojis. Todo en prosa natural.
6. NO uses menús con múltiples opciones numeradas ("diga 1 para...").
   Conversa de forma natural.
7. Si recibes datos como "USD/COP=4100" o "temperatura=22C" o mediciones
   médicas, tradúcelos a lenguaje humano y, en el caso de mediciones,
   interpreta si están en rango normal, elevado, bajo o requieren atención,
   aclarando que es orientativo y debe confirmarlo con su médico.
8. Si el usuario se frustra o no entiende, simplifica aún más y ofrece
   explicarlo paso a paso.
"""

        rag_context = ""
        if RAG_AVAILABLE:
            try:
                docs = search_knowledge(user_message, n_results=3)
                if docs:
                    rag_parts = []
                    for d in docs:
                        rag_parts.append(f"[Fuente: {d['source']}]\n{d['text']}")
                    rag_context = (
                        "\n\n## Base de conocimiento (usa esta información si es relevante):\n"
                        + "\n---\n".join(rag_parts)
                    )
                    app.logger.info(f"RAG: {len(docs)} docs encontrados")
                else:
                    app.logger.info("RAG: 0 docs encontrados")
            except Exception as e:
                app.logger.error(f"RAG error: {e}")

        prompt = f"""{system_prompt}{rag_context}

Contexto: {context}
Usuario: {user_message}"""
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        app.logger.error(f"Error Gemini: {str(e)}")
        return None


def openrouter_response(user_message, context=""):
    if not OPENROUTER_CONFIGURED:
        return None
    try:
        system_prompt = """Eres IAM, el Asistente Integral para el Adulto Mayor. Tu propósito es acompañar, informar y orientar a personas mayores en Colombia y América Latina en tres módulos especializados (salud básica, brigadista / emergencias y hogar / mantenimiento) y áreas de apoyo cotidiano (fecha, clima, indicadores, noticias, música, radio, televisión).

## Estilo
- Habla como una persona normal, cercana y natural. NO uses la palabra "amigo"
  ni muletillas repetitivas. Varía tu forma de dirigirte: usa su nombre si lo
  conoces, o habla directo.
- Breve y directo. 1 a 3 frases por respuesta. Hablas por voz, no escribes.
- Frases cortas y claras. Si usas un término técnico, explícalo en seguida.
- Tono cálido pero no infantilizante. Sin condescendencia.
- Evita saludos largos o cierres formulaicos en cada turno.

## Reglas estrictas
1. NUNCA pidas documentos de identidad, contraseñas, números de tarjeta ni
   claves.
2. NUNCA diagnostiques enfermedades ni recomiendes o ajustes medicamentos.
3. Si detectas síntomas de alarma médica (dolor de pecho, dificultad para
   respirar, confusión repentina, debilidad en un lado del cuerpo, dolor de
   cabeza súbito y muy fuerte) o una emergencia activa (sismo, incendio,
   caída, accidente doméstico), responde de inmediato indicando que busque
   atención médica urgente o llame a servicios de emergencia (123 en
   Colombia) ANTES de cualquier otra explicación.
4. Ante tareas de gas, electricidad de alto riesgo o estructuras, recomienda
   contactar a un profesional o a un familiar.
5. NO uses markdown, listas con viñetas ni emojis. Todo en prosa natural.
6. NO uses menús con múltiples opciones numeradas ("diga 1 para...").
   Conversa de forma natural.
7. Si recibes datos como "USD/COP=4100" o "temperatura=22C" o mediciones
   médicas, tradúcelos a lenguaje humano y, en el caso de mediciones,
   interpreta si están en rango normal, elevado, bajo o requieren atención,
   aclarando que es orientativo y debe confirmarlo con su médico.
8. Si el usuario se frustra o no entiende, simplifica aún más y ofrece
   explicarlo paso a paso.
"""

        rag_context = ""
        if RAG_AVAILABLE:
            try:
                docs = search_knowledge(user_message, n_results=3)
                if docs:
                    rag_parts = []
                    for d in docs:
                        rag_parts.append(f"[Fuente: {d['source']}]\n{d['text']}")
                    rag_context = (
                        "\n\n## Base de conocimiento (usa esta información si es relevante):\n"
                        + "\n---\n".join(rag_parts)
                    )
                    app.logger.info(f"RAG: {len(docs)} docs encontrados")
                else:
                    app.logger.info("RAG: 0 docs encontrados")
            except Exception as e:
                app.logger.error(f"RAG error: {e}")

        prompt = f"""{system_prompt}{rag_context}

Contexto: {context}
Usuario: {user_message}"""

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://iam.example.com",
            "X-Title": "IAM - Asistente para el Adulto Mayor",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500,
        }
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        app.logger.info(f"OpenRouter response status: {response.status_code}")
        if response.status_code != 200:
            app.logger.error(f"OpenRouter error body: {response.text[:500]}")
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        app.logger.error(f"Error OpenRouter: {str(e)}")
        return None


def get_llm_response(user_message, context=""):
    app.logger.info(
        f"get_llm_response: OPENROUTER_CONFIGURED={OPENROUTER_CONFIGURED}, GEMINI_CONFIGURED={GEMINI_CONFIGURED}"
    )
    if OPENROUTER_CONFIGURED:
        app.logger.info("Intentando OpenRouter...")
        result = openrouter_response(user_message, context)
        if result:
            app.logger.info(f"OpenRouter respondió: {result[:100]}...")
            return result
        app.logger.warning("OpenRouter falló, intentando Gemini como fallback")
    if GEMINI_CONFIGURED:
        app.logger.info("Intentando Gemini...")
        result = gemini_response(user_message, context)
        if result:
            app.logger.info(f"Gemini respondió: {result[:100]}...")
            return result
        app.logger.error("Gemini también falló")
    app.logger.error("Ningún LLM respondió")
    return None


def clasificar_intencion_iam(mensaje):
    """Clasificador de intenciones simple basado en palabras clave para IAM.
    Devuelve un string con la intención detectada o None.
    Se prefiere el clasificador de `guion.clasificar_intencion`, y este fallback
    se mantiene por compatibilidad con rutas que aún lo invocan.
    """
    try:
        from guion import clasificar_intencion

        return clasificar_intencion(mensaje)
    except Exception:
        return None


def categorizar_caso_con_llm(descripcion):
    """Compatibilidad: clasificador de intenciones simple. La función original
    clasificaba casos legales (CIVIL/LABORAL/PENAL); en IAM solo se necesita
    reconocer la intención del adulto mayor, así que se delega al clasificador
    por palabras clave. Se conserva el nombre para no romper importadores
    externos."""
    return clasificar_intencion_iam(descripcion)


def _default_call_state():
    """Retorna el estado por defecto de una conversación con IAM."""
    return {
        "caller_name": "",
        "caller_ciudad": "",
        "paso_actual": "saludo_inicial",
    }


def get_call_state():
    """Obtiene el estado de la conversación desde la sesión."""
    if "call_state" not in session:
        session["call_state"] = _default_call_state()
    return session["call_state"]


def save_call_state(state):
    """Guarda el estado de la conversación en la sesión."""
    session["call_state"] = state


def limpiar_estado_chat():
    """Limpia el estado de la conversación."""
    session["call_state"] = _default_call_state()


def obtener_estado_chat():
    """Obtiene el estado actual de la conversación como diccionario."""
    state = get_call_state()
    momento = ""
    try:
        from guion import obtener_momento_del_dia
        momento = obtener_momento_del_dia()
    except Exception:
        momento = "tardes"
    return {
        "caller_name": state.get("caller_name", ""),
        "nombre": state.get("caller_name", ""),
        "caller_ciudad": state.get("caller_ciudad", ""),
        "ciudad": state.get("caller_ciudad", ""),
        "momento_del_dia": momento,
        "paso_actual": state.get("paso_actual", "saludo_inicial"),
    }


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        from guion import (
            PASOS,
            obtener_paso,
            formatear_mensaje,
            obtener_momento_del_dia,
            clasificar_intencion,
        )

        data = request.json
        message = data.get("message", "")
        accion_boton = data.get("action", None)

        # ── Reiniciar conversación cuando se solicita ────────────────────
        if accion_boton == "nueva_llamada":
            limpiar_estado_chat()
            momento = obtener_momento_del_dia()
            paso = obtener_paso("saludo_inicial")
            response = formatear_mensaje(paso, {"momento_del_dia": momento})
            save_conversation(response, "saludo_inicial", "")
            return jsonify({"response": response, "end_call": False, "buttons": None, "step": "saludo_inicial"})

        # ── Obtener estado actual desde sesión ─────────────────────────
        state = get_call_state()
        paso_actual_id = state["paso_actual"]
        paso_actual = obtener_paso(paso_actual_id)

        if not paso_actual:
            limpiar_estado_chat()
            momento = obtener_momento_del_dia()
            paso = obtener_paso("saludo_inicial")
            response = formatear_mensaje(paso, {"momento_del_dia": momento})
            return jsonify({"response": response, "end_call": False, "buttons": None, "step": "saludo_inicial"})

        # ── Detección de despedida y emergencia en cualquier punto ─────
        if paso_actual_id not in ["saludo_inicial", "despedida"]:
            intencion = clasificar_intencion(message)
            if intencion == "despedida":
                # No usar "amigo" como fallback; solo el nombre si está disponible.
                name = state.get("caller_name") or ""
                paso_desp = obtener_paso("despedida")
                response = formatear_mensaje(paso_desp, {"nombre": name})
                limpiar_estado_chat()
                save_conversation(response, "despedida", message)
                return jsonify({"response": response, "end_call": True, "buttons": None, "step": "despedida"})
            if intencion == "emergencia":
                # Protocolo de escalamiento (módulo salud / brigadista).
                # Primero la indicación de acción segura, sin rodeos.
                name = state.get("caller_name") or ""
                nombre_call = f", {name}" if name else ""
                response = (
                    f"Eso suena urgente{nombre_call}. Por favor llame ya a la línea 123 "
                    "o pídale a alguien de confianza que lo acompañe. "
                    "Si puede, avísele también a su familiar más cercano. "
                    "¿Está usted solo en este momento?"
                )
                save_conversation(response, "conversacion_libre", message)
                return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

        # === PASO: saludo_inicial -> pasa directo a conversación libre ===
        if paso_actual_id == "saludo_inicial":
            state["paso_actual"] = "conversacion_libre"
            save_call_state(state)
            # Cualquier mensaje inicial se trata como la primera pregunta del usuario.
            return _responder_conversacion_libre(state, message)

        # === PASO: conversacion_libre / consulta_legal (alias) -> LLM ===
        if paso_actual_id in ["conversacion_libre", "consulta_legal", "ofrecer_ayuda"]:
            return _responder_conversacion_libre(state, message)

        if paso_actual_id == "despedida":
            limpiar_estado_chat()
            return jsonify({"response": "Ha sido un gusto acompañarle. Que tenga un día muy bonito.", "end_call": True, "buttons": None, "step": "despedida"})

        return jsonify({"response": "Disculpe, no entendí bien. ¿Podría repetirlo con calma, por favor?", "end_call": False, "buttons": None, "step": paso_actual_id})
    except Exception as e:
        app.logger.error(f"Error en chat: {e}", exc_info=True)
        return jsonify({"response": "Disculpe, tuve un problema técnico. ¿Podría repetir su mensaje, por favor?", "end_call": False, "buttons": None, "step": "error"})


def _delegar_al_llm(message, nombre, ciudad, contexto_adicional=""):
    """Delega al LLM una pregunta que no podemos responder con datos locales.
    Combina el contexto base del adulto mayor con un contexto adicional
    específico del tema. Retorna siempre un string útil (nunca vacío),
    incluso si el LLM falla o devuelve una respuesta débil.
    """
    # Prompt base humanizado para el LLM
    base_prompt = (
        "Eres IAM, un asistente de voz cálido y paciente para personas mayores "
        "en Colombia. Tu usuario es un adulto mayor, así que habla con calma, "
        "con respeto y sin tecnicismos. Nunca uses anglicismos ni jerga digital "
        "a menos que sean estrictamente necesarios. Si no sabes la respuesta "
        "exacta, NO inventes datos: responde con honestidad, sugiere dónde puede "
        "consultar (un familiar, un noticiero, una farmacia) y pregunta si hay "
        "algo más en lo que puedas ayudar. Máximo 2-3 frases por respuesta, "
        "siempre en español. "
        f"El usuario se llama {nombre or 'amigo'}. "
        f"Ciudad del usuario: {ciudad or 'no indicada'}. "
        "Conversación por voz (no hay pantalla). "
    )
    if contexto_adicional:
        base_prompt += "\n\nContexto específico para esta pregunta: " + contexto_adicional

    # Mensajes que indican que el LLM "no pudo" o no respondió nada útil.
    respuestas_debiles = (
        "no puedo", "no puedo ayudar", "no estoy seguro", "no tengo información",
        "no dispongo", "como modelo de lenguaje", "as an ai", "as a language model",
        "i cannot", "i don't know", "i'm not able",
    )

    llm_resp = ""
    try:
        llm_resp = get_llm_response(message, context=base_prompt) or ""
    except Exception as e:
        app.logger.error(f"LLM error en _delegar_al_llm: {e}")

    # Verificar si la respuesta es útil
    texto_limpio = llm_resp.strip()
    es_debil = (
        not texto_limpio
        or len(texto_limpio) < 20
        or any(p in texto_limpio.lower() for p in respuestas_debiles)
    )

    if es_debil:
        # El LLM no dio nada útil: generamos una respuesta amable con sugerencias
        app.logger.info(
            f"LLM respuesta debil o vacia, usando fallback amable. "
            f"Pregunta: '{message[:80]}'"
        )
        return _respuesta_amable_fallback(message, nombre, contexto_adicional)

    return texto_limpio


def _respuesta_amable_fallback(message, nombre, contexto_adicional=""):
    """Respuesta de fallback cuando el LLM falla o da una respuesta débil.
    Siempre devuelve algo cálido y útil para el adulto mayor.
    """
    nombre = nombre or "amigo"
    # Identificar el tema por el contexto adicional
    tema = ""
    if "clima" in contexto_adicional.lower():
        tema = "el clima"
    elif "dólar" in contexto_adicional.lower() or "euro" in contexto_adicional.lower():
        tema = "el precio del"
    elif "café" in contexto_adicional.lower() or "cafe" in contexto_adicional.lower():
        tema = "el precio del café"
    elif "noticias" in contexto_adicional.lower():
        tema = "las noticias"
    elif "música" in contexto_adicional.lower() or "musica" in contexto_adicional.lower():
        tema = "la música"
    elif "radio" in contexto_adicional.lower():
        tema = "la radio"
    elif "tv" in contexto_adicional.lower() or "televisión" in contexto_adicional.lower():
        tema = "la televisión"

    if tema:
        return (
            f"Disculpe, {nombre}, no alcancé a consultar {tema} en este momento. "
            f"Le recomiendo sintonizar un noticiero de confianza o preguntarle a un familiar. "
            f"¿Le puedo ayudar con algo más?"
        )

    # Fallback genérico para preguntas generales no reconocidas
    return (
        f"Disculpe, {nombre}, no alcancé a encontrar una respuesta exacta. "
        f"Le recomiendo consultarlo con un familiar de confianza o en su noticiero. "
        f"Mientras tanto, ¿hay algo más en lo que le pueda colaborar?"
    )


def _responder_conversacion_libre(state, message):
    """Responde en el modo conversación libre de IAM.
    Primero intenta resolver la intención sin LLM (fecha, hora, etc.).
    Si no se reconoce una intención clara, delega al LLM con el contexto del
    adulto mayor.
    """
    from guion import (
        clasificar_intencion,
        obtener_fecha_completa,
        obtener_hora_actual,
    )

    nombre = state.get("caller_name") or "amigo"
    ciudad = state.get("caller_ciudad") or ""
    intencion = clasificar_intencion(message)

    # ── Respuestas rápidas sin necesidad de LLM externo ─────────────
    if intencion == "fecha_hora":
        fecha_str = obtener_fecha_completa()
        hora_str = obtener_hora_actual()
        response = f"Hoy es {fecha_str}. {hora_str}"
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "clima":
        if not ciudad:
            response = "Con gusto le cuento el clima. ¿En qué ciudad se encuentra?"
            save_conversation(response, "conversacion_libre", message)
            return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})
        try:
            clima_texto = obtener_clima(ciudad)
            if clima_texto:
                response = clima_texto
                save_conversation(response, "conversacion_libre", message)
                return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})
        except Exception as e:
            app.logger.warning(f"obtener_clima falló: {e}")
        # Si la API falla, delegamos al LLM
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                f"El usuario pregunta por el clima de {ciudad}. "
                "No tienes acceso a datos meteorológicos en tiempo real, así que "
                "responde con amabilidad: explica que no pudiste consultar el clima "
                "ahora, sugiere cómo enterarse (sintonizar noticiero, salir un momento), "
                "y pregunta si hay algo más en lo que puedas ayudar. Máximo 2 frases, "
                "lenguaje cálido y sin tecnicismos."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion in ("dolar", "euro"):
        try:
            data = obtener_indicadores_economicos()
            if data:
                if intencion == "dolar":
                    usd = round(data["usd_cop"])
                    response = (
                        f"El dólar hoy está en {usd:,} pesos colombianos. "
                        "Es la tasa de referencia del mercado."
                    )
                else:
                    eur = round(data["eur_cop"])
                    response = (
                        f"El euro hoy está en {eur:,} pesos colombianos."
                    )
                save_conversation(response, "conversacion_libre", message)
                return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})
        except Exception as e:
            app.logger.warning(f"obtener_indicadores falló: {e}")
        nombre_moneda = "dólar" if intencion == "dolar" else "euro"
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                f"El usuario pregunta por el precio del {nombre_moneda} en pesos colombianos. "
                "No tienes acceso a tasas de cambio en tiempo real. Responde con amabilidad: "
                "explica que no pudiste consultar el precio ahora, recomienda consultar el "
                "Banco de la República, y pregunta si hay algo más en lo que puedas ayudar. "
                "Máximo 2 frases, lenguaje cálido y sin tecnicismos."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "cafe":
        try:
            data = obtener_precio_cafe()
            if data:
                precio = data["precio"]
                fecha = data.get("fecha", "")
                response = (
                    f"El precio interno de referencia del café en Colombia está "
                    f"en {precio} pesos por kilo. Es el precio que publica la "
                    "Federación Nacional de Cafeteros."
                )
                if fecha:
                    response += f" Dato del {fecha}."
                save_conversation(response, "conversacion_libre", message)
                return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})
        except Exception as e:
            app.logger.warning(f"obtener_precio_cafe falló: {e}")
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "El usuario pregunta por el precio del café en Colombia. "
                "No tienes acceso al precio de referencia en tiempo real. "
                "Responde con amabilidad: explica que no pudiste consultar el precio ahora, "
                "recomienda consultar la Federación Nacional de Cafeteros, "
                "y pregunta si hay algo más en lo que puedas ayudar. Máximo 2 frases, "
                "lenguaje cálido y sin tecnicismos."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "noticias":
        try:
            titulares = obtener_noticias_colombia(max_items=3)
            if titulares:
                intro = "Estas son las noticias más importantes de hoy en Colombia:"
                partes = [intro]
                for i, t in enumerate(titulares, 1):
                    partes.append(f"{i}. {t}")
                response = " ".join(partes)
                save_conversation(response, "conversacion_libre", message)
                return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})
        except Exception as e:
            app.logger.error(f"Error al obtener noticias: {e}")
        # Si no hay titulares o falló la API, delegamos al LLM
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "El usuario pregunta por las noticias de hoy en Colombia. "
                "No tienes acceso a titulares en tiempo real. Responde con amabilidad: "
                "explica que no pudiste consultar las noticias ahora, recomienda sintonizar "
                "Caracol Radio o RCN Noticias para enterarse de lo más importante del día, "
                "y pregunta si hay algo más en lo que puedas ayudar. Máximo 2 frases, "
                "lenguaje cálido y sin tecnicismos."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "musica":
        # Delegamos al LLM para que sugiera algo basado en lo que pide el usuario.
        # Si el LLM no devuelve nada útil, fallback amable.
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "El usuario quiere música. IAM no controla un dispositivo de música, "
                "pero puede conversar sobre géneros, cantantes o canciones. "
                "Si menciona un género o artista, comenta con cariño lo que sabe y sugiere "
                "que le pida a un familiar que le ponga esa música en el dispositivo. "
                "Si solo dice 'quiero música', sugiere amablemente algunos géneros "
                "populares entre adultos mayores en Colombia (boleros, música andina, "
                "tropical clásica, baladas) y pregunta cuál le gustaría."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "radio":
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "El usuario quiere sintonizar una emisora de radio. IAM no controla "
                "el radio, pero puede conversar sobre emisoras populares en Colombia "
                "(Caracol Radio, RCN Radio, La W, Radiónica, Bésame, Oxígeno, Tropicana). "
                "Si menciona una, confirma con cariño y sugiere pedirle a un familiar "
                "que la sintonice. Si solo dice 'quiero radio', sugiere algunas opciones "
                "populares según el gusto (noticias, boleros, música del recuerdo) y "
                "pregunta cuál prefiere."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "tv":
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "El usuario quiere ver un canal de televisión. IAM no controla la TV, "
                "pero puede conversar sobre canales colombianos populares (Caracol, RCN, "
                "Canal 1, Señal Colombia). Si menciona uno, confirma con cariño y sugiere "
                "pedirle a un familiar que lo sintonice. Si solo dice 'quiero ver tele' o "
                "'poner la tele', sugiere algunas opciones (Caracol, RCN, canal de "
                "noticias) y pregunta cuál prefiere."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "conversacion":
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "El usuario quiere conversar contigo (IAM). Es una persona mayor en "
                "Colombia. Acompáñale con calidez, sin tecnicismos. Si menciona soledad, "
                "tristeza o que se siente solo, valida sus sentimientos, recuérdale con "
                "cariño mantener contacto con su familia y amigos, y pregunta sobre qué "
                "le gustaría conversar. Si habla de algo específico (familia, recuerdos, "
                "salud, pasatiempos), conversa con naturalidad. Máximo 2-3 frases."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "salud":
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "Estás en el MÓDULO SALUD (enfermería básica) de IAM. El usuario es una "
                "persona mayor en Colombia. Reglas obligatorias:\n"
                "- NUNCA diagnostiques enfermedades ni recomiendes o ajustes dosis de "
                "medicamentos. Si pide ajustar medicación, responde que eso solo lo "
                "puede decidir su médico.\n"
                "- NUNCA recomiendes un medicamento específico. Solo puedes recordar "
                "tomas o explicar para qué sirve el que ya le recetaron.\n"
                "- Si menciona una medición (presión, glucosa, temperatura, saturación, "
                "frecuencia cardíaca), interprétala usando estos valores de referencia:\n"
                "  * Presión arterial (AHA): Normal <120/<80; Elevada 120-129/<80; "
                "HTA Etapa 1 130-139 u 80-89; HTA Etapa 2 >=140 o >=90; Crisis "
                "hipertensiva >180 y/o >120 — atención inmediata.\n"
                "  * Frecuencia cardíaca en reposo (adulto): 60-100 lpm normal.\n"
                "  * Glucosa en ayunas: 70-99 normal; 100-125 prediabetes; 126+ "
                "requiere evaluación médica.\n"
                "  * Temperatura: 36.1-37.2 normal; fiebre desde 38.\n"
                "  * Saturación de oxígeno: 95-100% normal; <92% requiere atención.\n"
                "- Si describe síntomas de alarma (dolor de pecho, dificultad para "
                "respirar, confusión repentina, debilidad en un lado del cuerpo, dolor "
                "de cabeza súbito y muy fuerte) o el valor está en rango de crisis, "
                "responde de inmediato indicando que busque atención médica urgente o "
                "llame a emergencias (123 en Colombia) ANTES de cualquier otra "
                "explicación. No minimices ni tranquilices de más antes de dar esa "
                "indicación.\n"
                "- Cierra aclarando que la interpretación es orientativa y que debe "
                "confirmarlo con su médico.\n"
                "Responde en máximo 2-3 frases, en lenguaje simple y cercano, sin "
                "diagnósticos."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "brigadista":
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "Estás en el MÓDULO BRIGADISTA (emergencias y seguridad) de IAM. El "
                "usuario es una persona mayor en Colombia. Reglas obligatorias:\n"
                "- Si la persona está reportando una emergencia activa (temblor "
                "ocurriendo, incendio, inundación, caída, síntomas graves), prioriza "
                "dar la instrucción de seguridad inmediata y la indicación de llamar "
                "a servicios de emergencia (123 en Colombia) ANTES de cualquier otra "
                "explicación.\n"
                "- No inventes números de emergencia: si no conoces su país o ciudad, "
                "pregúntale y/o indícale que verifique el número local.\n"
                "- Para protocolos (terremoto, incendio, inundación), da pasos "
                "numerados, cortos y fáciles de recordar bajo estrés. Ejemplo de "
                "terremoto: 1) agacharse, 2) cubrirse la cabeza y el cuello, "
                "3) sujetarse a algo firme. Después: verificar heridas, salir con "
                "calma, evitar ascensores, tener el kit de emergencia.\n"
                "- Para kit de emergencia básico: agua, medicamentos, documentos, "
                "linterna, radio, silbato, cobija y números de contacto.\n"
                "- Para riesgos del hogar de un adulto mayor: objetos que puedan "
                "caer, rutas de evacuación bloqueadas, falta de iluminación de "
                "emergencia, tapetes sueltos, cables sueltos.\n"
                "Responde en máximo 2-3 frases por turno, salvo que pida pasos "
                "numerados."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "hogar":
        response = _delegar_al_llm(
            message, nombre, ciudad,
            contexto_adicional=(
                "Estás en el MÓDULO HOGAR (mantenimiento y seguridad doméstica) de "
                "IAM. El usuario es una persona mayor en Colombia. Reglas obligatorias:\n"
                "- Para tareas simples y seguras (cambiar un foco, resetear un breaker, "
                "verificar una fuga visible, sustituir pila, limpiar un filtro), guíalo "
                "paso a paso en lenguaje simple.\n"
                "- Para tareas de gas, electricidad de alto riesgo o estructuras "
                "(techos, escaleras altas), recomienda SIEMPRE contactar a un "
                "profesional o a un familiar. No lo guíes para que lo haga solo.\n"
                "- Para conexiones (wifi, control remoto, electrodomésticos), explica "
                "en pasos simples.\n"
                "- Para prevención de caídas: tapetes fijos o retirados, buena "
                "iluminación, pasamanos en baños y escaleras, evitar subirse a "
                "sillas o escaleras sin ayuda.\n"
                "- Prioriza SIEMPRE la seguridad física de la persona sobre "
                "completar la tarea.\n"
                "Responde en máximo 2-3 frases, salvo cuando des pasos numerados."
            ),
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    # ── Si no se reconoció intención, delegamos al LLM con contexto ────
    # Primero intentamos enriquecer con RAG si está disponible y hay documentos.
    rag_context_text = ""
    if RAG_AVAILABLE:
        try:
            docs = search_knowledge(message, n_results=3)
            if docs:
                rag_parts = [f"[Fuente: {d['source']}]\n{d['text']}" for d in docs]
                rag_context_text = "\n---\n".join(rag_parts)
        except Exception as e:
            app.logger.error(f"RAG error: {e}")

    contexto_extra = ""
    if rag_context_text:
        contexto_extra = (
            "Conocimiento relevante encontrado en la base de IAM "
            "(úsalo solo si aplica a la pregunta, si no, ignóralo):\n"
            + rag_context_text
        )

    # Llamamos a _delegar_al_llm que se encarga de detectar respuestas débiles
    # y aplicar el fallback amable automáticamente.
    response = _delegar_al_llm(message, nombre, ciudad, contexto_adicional=contexto_extra)
    save_conversation(response, "conversacion_libre", message)
    return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})


@app.route("/api/log-call", methods=["POST"])
def log_call():
    """Endpoint para registrar conversaciones (antes llamadas) desde el frontend."""
    try:
        data = request.json
        guardar_llamada({
            "email": data.get("email", ""),
            "nombre": data.get("nombre", ""),
            "documento": data.get("documento", ""),
            "duracion_segundos": data.get("duracion_segundos", 0),
            "paso_final": data.get("paso_final", ""),
            "estado": data.get("estado", "completada"),
        })
        return jsonify({"ok": True})
    except Exception as e:
        app.logger.error(f"Error logging call: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/knowledge/upload", methods=["POST"])
def upload_knowledge():
    if not RAG_AVAILABLE:
        return jsonify(
            {"error": "Módulo RAG no disponible. Verifique dependencias."}
        ), 500
    if "file" not in request.files:
        return jsonify({"error": "No se envió ningún archivo."}), 400
    file = request.files["file"]
    if not file.filename.endswith(".pdf"):
        return jsonify({"error": "Solo se permiten archivos PDF."}), 400

    # Check file size (max 5MB to prevent OOM on Render free tier)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Seek back to start
    max_size = 5 * 1024 * 1024  # 5MB
    if file_size > max_size:
        return jsonify(
            {
                "error": f"El archivo excede el límite de 5MB. Tamaño actual: {file_size // (1024 * 1024)}MB"
            }
        ), 400

    try:
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, file.filename)
        file.save(tmp_path)
        app.logger.info(f"PDF guardado temporalmente: {tmp_path}")

        num_chunks, msg = add_pdf(tmp_path)
        app.logger.info(f"Resultado add_pdf: {msg}")

        # Cleanup
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except Exception:
            pass

        if num_chunks == 0:
            return jsonify({"error": msg}), 400
        return jsonify({"message": msg, "chunks": num_chunks})
    except Exception as e:
        app.logger.error(f"Error uploading PDF: {str(e)}", exc_info=True)
        return jsonify({"error": f"Error al procesar el PDF: {str(e)}"}), 500


@app.route("/api/knowledge/documents", methods=["GET"])
def list_knowledge():
    if not RAG_AVAILABLE:
        return jsonify({"documents": [], "rag_available": False})
    docs = list_documents()
    return jsonify({"documents": docs, "rag_available": True})


@app.route("/api/knowledge/delete", methods=["POST"])
def delete_knowledge():
    if not RAG_AVAILABLE:
        return jsonify({"error": "Módulo RAG no disponible."}), 500
    data = request.json
    source = data.get("source", "")
    if not source:
        return jsonify({"error": "Nombre del documento no proporcionado."}), 400
    success, msg = delete_document(source)
    if success:
        return jsonify({"message": msg})
    return jsonify({"error": msg}), 404


@app.route("/api/health", methods=["GET"])
def health_check():
    llm_provider = (
        "openrouter"
        if OPENROUTER_CONFIGURED
        else ("gemini" if GEMINI_CONFIGURED else "none")
    )
    llm_model = (
        OPENROUTER_MODEL
        if OPENROUTER_CONFIGURED
        else ("gemini-2.5-flash" if GEMINI_CONFIGURED else "none")
    )
    return jsonify(
        {
            "status": "healthy",
            "gemini_configured": GEMINI_CONFIGURED,
            "openrouter_configured": OPENROUTER_CONFIGURED,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "tts_voice": TTS_VOICE,
            "service": f"edge-tts ({TTS_VOICE}) + {llm_model}",
        }
    )


@app.route("/api/test-gemini", methods=["GET"])
def test_gemini():
    """Test endpoint to check if Gemini text generation works."""
    try:
        if not GEMINI_CONFIGURED or gemini_model is None:
            return jsonify(
                {"error": "Gemini no configurado", "configured": GEMINI_CONFIGURED}
            ), 500
        response = gemini_model.generate_content("Responde solo: hola")
        return jsonify({"status": "ok", "response": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-openrouter", methods=["GET"])
def test_openrouter():
    """Test endpoint to check if OpenRouter works."""
    try:
        if not OPENROUTER_API_KEY:
            return jsonify({"error": "OPENROUTER_API_KEY no configurada"}), 500
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": "Responde solo: hola"}],
            "max_tokens": 50,
        }
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=15,
        )
        return jsonify({"status": r.status_code, "body": r.text[:500]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-embedding", methods=["GET"])
def test_embedding():
    """Test endpoint to check if Gemini embeddings work."""
    try:
        import google.generativeai as genai

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return jsonify({"error": "GEMINI_API_KEY no configurada"}), 500
        genai.configure(api_key=api_key)
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content="Test de embedding",
            output_dimensionality=768,
        )
        return jsonify(
            {
                "status": "ok",
                "dimension": len(result["embedding"]),
                "first_5_values": result["embedding"][:5],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/test-search", methods=["POST"])
def test_search():
    """Test RAG search directly."""
    if not RAG_AVAILABLE:
        return jsonify({"error": "RAG not available"}), 500
    data = request.json or {}
    query = data.get("query", "Convención de Viena tratados")
    try:
        docs = search_knowledge(query, n_results=3)
        return jsonify({"query": query, "results": docs, "count": len(docs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pinecone-status", methods=["GET"])
def pinecone_status():
    """Check Pinecone index status directly."""
    if not RAG_AVAILABLE:
        return jsonify({"error": "RAG not available"}), 500
    try:
        from rag import get_pc, get_index, INDEX_NAME, DIMENSION

        pc = get_pc()
        if pc is None:
            return jsonify({"error": "Pinecone not connected"}), 500

        existing = pc.list_indexes()
        index_names = [idx.name for idx in existing.indexes]

        if INDEX_NAME not in index_names:
            return jsonify(
                {"status": "no_index", "indexes": index_names, "expected": INDEX_NAME}
            )

        idx = pc.Index(INDEX_NAME)
        stats = idx.describe_index_stats()

        return jsonify(
            {
                "status": "ok",
                "index": INDEX_NAME,
                "dimension": DIMENSION,
                "total_vectors": stats.total_vector_count,
                "namespaces": {k: v.vector_count for k, v in stats.namespaces.items()}
                if stats.namespaces
                else {},
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/voices", methods=["GET"])
def list_voices():
    """Lista las voces latinas masculinas y femeninas disponibles para IAM.
    La voz recomendada es Gonzalo (es-CO-GonzaloNeural): masculina, colombiana,
    Natural (suena menos robótica) y cercana para el público adulto mayor.
    """
    voices = [
        {
            "id": "es-CO-GonzaloNeural",
            "name": "Gonzalo",
            "gender": "Masculino",
            "region": "Colombia",
            "natural": True,
            "recommended": True,
            "description": "Voz masculina colombiana, cálida y Natural. Ideal para IAM.",
        },
        {
            "id": "es-MX-JorgeNeural",
            "name": "Jorge",
            "gender": "Masculino",
            "region": "México",
            "natural": True,
            "description": "Voz masculina mexicana Natural.",
        },
        {
            "id": "es-PE-AlexNeural",
            "name": "Alex",
            "gender": "Masculino",
            "region": "Perú",
            "natural": True,
            "description": "Voz masculina peruana Natural.",
        },
        {
            "id": "es-AR-TomasNeural",
            "name": "Tomás",
            "gender": "Masculino",
            "region": "Argentina",
            "natural": True,
            "description": "Voz masculina argentina Natural.",
        },
        {
            "id": "es-CL-LorenzoNeural",
            "name": "Lorenzo",
            "gender": "Masculino",
            "region": "Chile",
            "natural": True,
            "description": "Voz masculina chilena Natural.",
        },
        {
            "id": "es-VE-SebastianNeural",
            "name": "Sebastián",
            "gender": "Masculino",
            "region": "Venezuela",
            "natural": True,
            "description": "Voz masculina venezolana Natural.",
        },
        # Voces femeninas como alternativas
        {
            "id": "es-CO-SalomeNeural",
            "name": "Salomé",
            "gender": "Femenina",
            "region": "Colombia",
            "natural": True,
            "description": "Voz femenina colombiana Natural (alternativa).",
        },
        {
            "id": "es-MX-DaliaNeural",
            "name": "Dalia",
            "gender": "Femenina",
            "region": "México",
            "natural": True,
            "description": "Voz femenina mexicana Natural (alternativa).",
        },
        {
            "id": "es-US-PalomaNeural",
            "name": "Paloma",
            "gender": "Femenina",
            "region": "Estados Unidos (español)",
            "natural": True,
            "description": "Voz femenina latina Natural (alternativa).",
        },
    ]
    return jsonify({"voices": voices, "current": TTS_VOICE})


def save_conversation(response, paso_actual, user_message=""):
    try:
        state = get_call_state()
        email = state.get("caller_email", "")
        nombre = state.get("caller_name", "")
        app.logger.info(
            f"save_conversation: email={email}, nombre={nombre}, paso={paso_actual}, msg_len={len(user_message or '')}"
        )
        datos = {
            "email": email,
            "nombre": nombre,
            "mensaje_usuario": user_message if user_message else "",
            "respuesta_agente": response,
            "paso": paso_actual,
        }
        resultado = guardar_conversacion(datos)
        app.logger.info(f"save_conversation resultado: {resultado}")
    except Exception as e:
        app.logger.error(f"Error saving conversation: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
