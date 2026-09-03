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
    "OPENROUTER_MODEL", "minimax/minimax-m3:free"
).strip()
OPENROUTER_CONFIGURED = bool(OPENROUTER_API_KEY)

TTS_VOICE = os.environ.get("TTS_VOICE", "es-CO-GonzaloNeural")

# Ajustes de la voz para sonar cálida, amigable y natural.
# Se aplican siempre, salvo que el usuario los sobreescriba por variables de entorno.
TTS_RATE = os.environ.get("TTS_RATE", "-5%")        # Un poquito más lento, mejor para adultos mayores
TTS_PITCH = os.environ.get("TTS_PITCH", "+0Hz")      # Tono más cálido sin sonar agudo
TTS_VOLUME = os.environ.get("TTS_VOLUME", "+0%")     # Volumen neutro

INSTRUCCIONES_LLAMADA = """Eres IAM, un asistente de voz cálido, paciente y eficaz para
personas adultas mayores en Colombia y América Latina. Tu propósito
es acompañar, orientar y resolver dudas del día a día con la misma
solvencia con la que lo haría un familiar de confianza bien
preparado: en salud básica (como un enfermero), en emergencias y
seguridad del hogar (como un brigadista), en mantenimiento del hogar
(como un técnico prudente), y en temas cotidianos como fecha, clima,
indicadores económicos, noticias, música, radio y televisión.

REGLA FUNDAMENTAL: Cualquier pregunta que te haga la persona, sin
importar el tema (salud, hogar, emergencias, noticias, geografía,
historia, cocina, religión, leyes, trámites, tecnología, cultura,
deportes, entretenimiento, etc.), SIEMPRE debes responderle con
información útil basada en tu conocimiento general. No te limites a
un solo campo: eres un asistente abierto y versátil. Si el tema es
médico, orienta como un enfermero prudente; si es técnico del hogar,
guía con cuidado; si es cultural o general, conversa con naturalidad;
si es de actualidad, comparte lo que sepas y sugiere dónde enterarse
mejor. No hay tema "fuera de tu alcance" en conversación cotidiana.

Hablas en español, sin tecnicismos innecesarios. Tratas a la persona
como adulta, con respeto y sin condescendencia. Varía cómo te
diriges: usa su nombre si lo conoces, o habla directo; evita la
muletilla "amigo" en cada turno. No hagas saludos largos ni cierres
formulaicos. Responde de forma breve, clara y útil: 1 a 3 frases para
lo cotidiano, hasta 5-6 frases si la persona pide pasos o
explicaciones más largas.

Actúa con criterio. Si la persona describe algo claramente urgente,
recomienda llamar a la línea 123 o a un familiar. No diagnostiques
enfermedades, no cambies dosis de medicamentos, no guíes tareas de
gas o electricidad de alto riesgo: en esos casos recomienda
profesional o familiar. Pero en todo lo demás, sé un asistente útil,
abierto y conversacional: responde a lo que te pregunten con base en
tu conocimiento, sin encajonarte en guiones rígidos.
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
            "temperature": 0.5,
            "max_tokens": 250,
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

        # ── Detección automática de ciudad en el mensaje ──────────────
        # Si el usuario menciona una ciudad colombiana conocida (por
        # ejemplo "el clima en Bogotá"), la guardamos en el estado
        # para no volver a preguntarla después. Esto evita que IAM
        # pregunte "¿en qué ciudad se encuentra?" en cada consulta.
        try:
            from guion import detectar_ciudad_en_texto

            ciudad_detectada = detectar_ciudad_en_texto(message)
            if ciudad_detectada and not state.get("caller_ciudad"):
                state["caller_ciudad"] = ciudad_detectada
                save_call_state(state)
                app.logger.info(f"Ciudad detectada y guardada: {ciudad_detectada}")
        except Exception as e:
            app.logger.warning(f"Error detectando ciudad: {e}")

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
                # Respuesta breve y útil ante una emergencia.
                # El LLM ya recibió el system prompt con criterios de
                # escalamiento; aquí solo devolvemos una indicación corta
                # mientras el LLM puede ampliar con contexto si es necesario.
                name = state.get("caller_name") or ""
                nombre_call = f", {name}" if name else ""
                response = (
                    f"Cuente conmigo{nombre_call}. Si se trata de algo urgente, "
                    "le recomiendo llamar a la línea 123 o pedirle a alguien de "
                    "confianza que lo acompañe. ¿En qué le ayudo?"
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
    específico del tema. Deja que el LLM responda libremente sin
    filtrar palabras clave (no descartamos respuestas que digan
    honestamente "no estoy seguro", porque eso ya es una respuesta
    útil y honesta).
    """
    # Prompt base humanizado para el LLM (corto, para respuestas rápidas)
    base_prompt = (
        "Eres IAM, asistente cálido para adultos mayores en Colombia. "
        "Habla en español, sin tecnicismos ni anglicismos. "
        f"Usuario: {nombre or 'adulto mayor'}. Ciudad: {ciudad or 'Colombia'}. "
        "Canal: voz. Responde SIEMPRE con información útil a la pregunta "
        "que te hagan, sin importar el tema (salud, hogar, noticias, "
        "cultura, leyes, geografía, trámites, etc.). Si es médico, orienta "
        "como enfermero; si es técnico del hogar, guía con cuidado; si es "
        "general, conversa con naturalidad. Responde en 1-3 frases para "
        "lo cotidiano o en 5-6 frases si piden pasos o más detalle."
    )
    if contexto_adicional:
        base_prompt += "\n" + contexto_adicional

    llm_resp = ""
    try:
        llm_resp = get_llm_response(message, context=base_prompt) or ""
    except Exception as e:
        app.logger.error(f"LLM error en _delegar_al_llm: {e}")
        return _respuesta_amable_fallback(message, nombre, contexto_adicional)

    texto_limpio = llm_resp.strip()

    # Si el LLM devolvió vacío, usamos el fallback.
    if not texto_limpio:
        return _respuesta_amable_fallback(message, nombre, contexto_adicional)

    return texto_limpio


def _respuesta_amable_fallback(message, nombre, contexto_adicional=""):
    """Respuesta de fallback cuando el LLM falla o da una respuesta débil.
    Devuelve algo cálido y útil para el adulto mayor, sin sonar repetitivo.
    """
    nombre = nombre or ""
    # Identificar el tema por el contexto adicional
    tema = ""
    ctx = contexto_adicional.lower()
    if "clima" in ctx:
        tema = "el clima"
    elif "dólar" in ctx or "euro" in ctx:
        tema = "el precio del dólar o euro"
    elif "café" in ctx:
        tema = "el precio del café"
    elif "noticias" in ctx:
        tema = "las noticias del momento"
    elif "música" in ctx:
        tema = "la música"
    elif "radio" in ctx:
        tema = "la radio"
    elif "televisión" in ctx:
        tema = "la televisión"

    if tema:
        return (
            f"Disculpe, no alcancé a consultar {tema} en este momento. "
            f"Le recomiendo sintonizar un noticiero o preguntarle a un familiar de confianza. "
            f"¿Le puedo ayudar con algo más?"
        )

    # Fallback genérico más abierto y útil.
    return (
        f"No estoy seguro de tener una respuesta exacta para eso en este momento. "
        f"¿Quiere que intentemos de otra forma o lo hablamos con calma? "
        f"Si lo prefiere, puedo sugerirte dónde buscar: un familiar, un noticiero "
        f"o una consulta específica."
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
            # Si no detectamos ciudad en el mensaje, dejamos que el LLM
            # responda libremente: puede inferir el clima aproximado,
            # pedir la ciudad con amabilidad o sugerir cómo enterarse.
            response = _delegar_al_llm(
                message, nombre, ciudad,
                contexto_adicional=(
                    "El usuario pregunta por el clima pero no mencionó "
                    "en qué ciudad se encuentra. Pídele con amabilidad "
                    "el nombre de su ciudad o municipio y dile que "
                    "mientras tanto puede asomarse a la ventana o "
                    "escuchar el noticiero para enterarse del tiempo."
                ),
            )
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
        # Si la API falla, delegamos al LLM para que responda libremente.
        response = _delegar_al_llm(message, nombre, ciudad)
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
        # Si la API falla, el LLM responde libremente.
        response = _delegar_al_llm(message, nombre, ciudad)
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
        # Si la API falla, el LLM responde libremente.
        response = _delegar_al_llm(message, nombre, ciudad)
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "noticias":
        titulares = []
        try:
            titulares = obtener_noticias_colombia(max_items=4)
        except Exception as e:
            app.logger.error(f"Error al obtener noticias: {e}")

        if titulares:
            intro = "Estas son las noticias más importantes hoy en Colombia:"
            partes = [intro]
            for i, t in enumerate(titulares, 1):
                partes.append(f"{i}. {t}")
            response = " ".join(partes)
        else:
            # Si el RSS falla, dejamos que el LLM responda libremente.
            response = _delegar_al_llm(message, nombre, ciudad)

        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "musica":
        # Delegar al LLM sin prompt restrictivo.
        response = _delegar_al_llm(message, nombre, ciudad)
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "radio":
        # Delegar al LLM sin prompt restrictivo.
        response = _delegar_al_llm(message, nombre, ciudad)
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "tv":
        # Delegar al LLM sin prompt restrictivo.
        response = _delegar_al_llm(message, nombre, ciudad)
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "conversacion":
        # Delegar al LLM sin prompt restrictivo.
        response = _delegar_al_llm(message, nombre, ciudad)
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "salud":
        # Delegar al LLM sin prompt restrictivo: el system prompt
        # principal ya lo guía como enfermero. Dejamos que responda
        # libremente según su conocimiento.
        response = _delegar_al_llm(message, nombre, ciudad)
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "brigadista":
        # Delegar al LLM sin prompt restrictivo: el system prompt
        # principal ya lo guía como brigadista.
        response = _delegar_al_llm(message, nombre, ciudad)
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "hogar":
        # Delegar al LLM sin prompt restrictivo: el system prompt
        # principal ya lo guía como técnico doméstico prudente.
        response = _delegar_al_llm(message, nombre, ciudad)
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
