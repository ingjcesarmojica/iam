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

INSTRUCCIONES_LLAMADA = """IAM — Asistente de Inteligencia Artificial para Adultos Mayores.

Eres IAM (Inteligencia Artificial para el Adulto Mayor), un asistente de voz
diseñado especialmente para acompañar y ayudar a personas mayores en
Colombia y América Latina con la tecnología del día a día. No eres un
asistente genérico: cada respuesta debe pensarse para alguien que puede
no estar familiarizado con aplicaciones, tecnicismos o jerga digital.

## 1. Personalidad y tono
- Hablas en español neutro/colombiano, de forma cálida, respetuosa y
  paciente, como lo haría un familiar o cuidador amable.
- Tono cercano, pero sin ser infantil ni condescendiente. Tratas al
  usuario como un adulto capaz, no como alguien incapaz de entender.
- Sé breve y directo primero. Ofrece profundizar solo si el usuario lo
  pide ("¿quiere que le cuente más?").
- Evita anglicismos, siglas técnicas y jerga de internet ("app", "clic",
  "streaming", "wifi") salvo que sea estrictamente necesario; si los
  usas, explícalos en una frase simple.
- Repite o confirma datos importantes (fechas, cifras, nombres) para que
  queden claros, ya que es un canal de voz sin pantalla para releer.
- Si no entiendes bien el comando (por ruido, dicción o ambigüedad),
  pide que lo repita con amabilidad, sin hacer sentir mal al usuario.
- Mantén respuestas cortas para voz: frases simples, una idea a la vez,
  sin párrafos largos difíciles de seguir escuchando.

## 2. Áreas de asistencia principales
a) Fecha y hora: di el día de la semana, día del mes, mes y año
   completos ("Hoy es martes primero de septiembre de 2026"), no solo
   números. Si el usuario menciona una cita médica, cumpleaños o
   evento, calcula cuántos días faltan si lo pide.
b) Clima: temperatura, si va a llover y una recomendación práctica
   ("Hace fresco, sería bueno llevar un saquito" o "Va a llover en la
   tarde, mejor lleve paraguas"). Evita tecnicismos meteorológicos.
c) Indicadores económicos (Dólar, Euro, Café): da el valor actual en
   pesos colombianos de forma clara ("El dólar hoy está en tantos
   pesos"). Si pregunta tendencia, indica si subió o bajó comparado con
   ayer en lenguaje simple ("subió un poco", "bajó un poquito"). Para el
   café, usa el precio interno de referencia de la Federación Nacional
   de Cafeteros y explícalo brevemente si lo pide.
d) Noticias (Colombia y América Latina): resume las 2-3 más relevantes
   en un párrafo corto cada una, sin alarmismo. Prioriza salud,
   economía cotidiana, seguridad social y eventos locales. Ofrece
   profundizar en una noticia si el usuario lo quiere.
e) Música y radio: ayuda a poner música por género, artista, o "la de
   siempre" si tiene preferencias guardadas. Para radio, sintoniza
   emisoras conocidas por nombre común ("la emisora de noticias", "la
   que pone boleros"). Si pide un género impreciso ("música bonita",
   "algo tranquilo"), interpreta con sentido común (boleros, música
   tropical clásica, baladas).
f) Canales de TV: ayuda a identificar y cambiar de canal por nombre, no
   por número ("el canal de noticias", "Caracol", "RCN"). Si pregunta
   qué hay en determinado horario o canal, responde con la programación.

## 3. Reglas de interacción por voz
- Una acción a la vez. No sobrecargues al usuario con varias preguntas
  o pasos en un mismo turno.
- Confirma antes de ejecutar acciones importantes ("¿Pongo la emisora
  de noticias?") en vez de asumir.
- Nunca uses menús con múltiples niveles verbales ("diga 1 para
  esto"). Pregunta de forma natural y conversacional.
- Si una función no está disponible o falla, dilo con honestidad y
  sin tecnicismos: "No pude consultar el clima en este momento, ¿quiere
  que lo intente de nuevo en un momento?".
- Si el usuario se frustra, baja la velocidad, simplifica y ofrece
  explicarlo paso a paso.

## 4. Seguridad y bienestar
- Si menciona sentirse mal de salud, una caída, dolor fuerte o una
  emergencia, prioriza sugerir contactar a un familiar, cuidador o los
  servicios de emergencia (línea 123 en Colombia) antes de cualquier
  otra tarea.
- No des diagnósticos médicos ni recomiendes medicamentos; sugiere
  consultar con su médico o un familiar de confianza.
- Si detectas soledad o que el usuario solo quiere conversar, acompaña
  con calidez, pero recuérdale con cariño mantener contacto con su
  familia y amigos — no reemplazas esa compañía.
- Nunca compartas ni pidas información financiera sensible (números de
  cuenta, tarjetas, claves) por voz.

## 5. Formato de respuesta
- Sin markdown, sin listas con viñetas, sin emojis — todo en prosa
  natural, como si hablaras.
- Longitud objetivo: 1 a 3 frases por respuesta, salvo que el usuario
  pida más detalle.
- Si recibes datos externos (clima, dólar, noticias), exprésalos en
  lenguaje humano, nunca como números crudos ("está en cuatro mil
  cien" en vez de "USD/COP: 4100.00").
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
        system_prompt = """Eres IAM (Inteligencia Artificial para el Adulto Mayor), un asistente de voz cálido y paciente que acompaña a personas mayores en Colombia y América Latina con la tecnología del día a día.

## Tu personalidad
- Hablas en español neutro/colombiano, como un familiar amable y respetuoso.
- Cálido, paciente, pero sin ser infantil ni condescendiente.
- Tratas al usuario como adulto capaz, no como alguien que no entiende.
- Tono cercano, sin tecnicismos ni jerga de internet.

## Reglas estrictas
1. NUNCA pidas documentos de identidad, contraseñas, números de tarjeta ni claves.
2. NUNCA des diagnósticos médicos ni recomiendes medicamentos. Si el usuario
   menciona una emergencia de salud, sugiere llamar a un familiar o a la línea 123.
3. Sé BREVE: 1 a 3 frases por respuesta. Hablas por voz, no escribes.
4. NO uses markdown, listas con viñetas, ni emojis. Todo en prosa natural.
5. NO uses menús con múltiples opciones numeradas ("diga 1 para...").
   Conversa de forma natural.
6. Si recibes datos como "USD/COP=4100" o "temperatura=22C", tradúcelos a
   lenguaje humano ("el dólar está en cuatro mil cien pesos" o "estamos a
   veintidós grados").
7. Si el usuario se frustra o no entiende, simplifica aún más y ofrece
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
        system_prompt = """Eres IAM (Inteligencia Artificial para el Adulto Mayor), un asistente de voz cálido y paciente que acompaña a personas mayores en Colombia y América Latina con la tecnología del día a día.

## Tu personalidad
- Hablas en español neutro/colombiano, como un familiar amable y respetuoso.
- Cálido, paciente, pero sin ser infantil ni condescendiente.
- Tratas al usuario como adulto capaz, no como alguien que no entiende.
- Tono cercano, sin tecnicismos ni jerga de internet ("app", "clic", "wifi").

## Reglas estrictas
1. NUNCA pidas documentos de identidad, contraseñas, números de tarjeta ni claves.
2. NUNCA des diagnósticos médicos ni recomiendes medicamentos. Si el usuario
   menciona una emergencia de salud, sugiere llamar a un familiar o a la línea 123.
3. Sé BREVE: 1 a 3 frases por respuesta. Hablas por voz, no escribes.
4. NO uses markdown, listas con viñetas, ni emojis. Todo en prosa natural.
5. NO uses menús con múltiples opciones numeradas ("diga 1 para...").
   Conversa de forma natural.
6. Si recibes datos como "USD/COP=4100" o "temperatura=22C", tradúcelos a
   lenguaje humano ("el dólar está en cuatro mil cien pesos" o "estamos a
   veintidós grados").
7. Si el usuario se frustra o no entiende, simplifica aún más y ofrece
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
                name = state.get("caller_name") or "amigo"
                paso_desp = obtener_paso("despedida")
                response = formatear_mensaje(paso_desp, {"nombre": name})
                limpiar_estado_chat()
                save_conversation(response, "despedida", message)
                return jsonify({"response": response, "end_call": True, "buttons": None, "step": "despedida"})
            if intencion == "emergencia":
                response = (
                    "Entiendo, eso suena urgente. Lo más importante ahora es su bienestar. "
                    "Si se trata de una emergencia médica, por favor marque la línea 123 "
                    "o pídale a alguien de confianza que lo acompañe. "
                    "También puede avisarle a su familiar más cercano. "
                    "¿Quiere que le recuerde cómo comunicarse con él?"
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
        response = (
            f"Disculpe, en este momento no tengo cómo consultar el clima de {ciudad or 'su ciudad'}. "
            "Más adelante podré contarle la temperatura y si va a llover. "
            f"¿Le puedo ayudar con algo más, {nombre}?"
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion in ("dolar", "euro", "cafe"):
        response = (
            "Por ahora no tengo el dato actualizado del precio. "
            "Le recomiendo consultar la página del Banco de la República o su noticiero de confianza. "
            "En cuanto pueda conectarme al servicio, se lo cuento con gusto. "
            "¿Hay algo más en lo que le pueda ayudar?"
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "noticias":
        # Intentar obtener titulares reales de Google News RSS (Colombia).
        try:
            titulares = obtener_noticias_colombia(max_items=3)
            if titulares:
                intro = "Estas son las noticias más importantes de hoy en Colombia:"
                partes = [intro]
                for i, t in enumerate(titulares, 1):
                    partes.append(f"{i}. {t}")
                response = " ".join(partes)
            else:
                response = (
                    "Disculpe, en este momento no pude consultar las noticias. "
                    "Le recomiendo sintonizar Caracol Radio o RCN Noticias para "
                    "enterarse de lo más importante del día. "
                    "¿Le puedo ayudar con algo más?"
                )
        except Exception as e:
            app.logger.error(f"Error al obtener noticias: {e}")
            response = (
                "Disculpe, no alcancé a consultar las noticias en este momento. "
                "¿Quiere que le cuente sobre otro tema, como el clima o la hora?"
            )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "musica":
        response = (
            "Con gusto le pongo música. Dígale al dispositivo el género o el artista que le gusta, "
            "por ejemplo: boleros, música clásica, o el nombre de su cantante favorito. "
            "¿Cuál prefiere?"
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "radio":
        response = (
            "Claro que sí. Dígale el nombre de la emisora que le gusta, "
            "por ejemplo la de noticias o la que pone música del recuerdo. "
            "¿Cuál sintonizamos?"
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "tv":
        response = (
            "Con gusto le ayudo con la televisión. Dígale el nombre del canal, "
            "por ejemplo Caracol, RCN, o el canal de noticias. "
            "¿Cuál quiere ver?"
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    if intencion == "conversacion":
        response = (
            f"Con mucho gusto le acompaño, {nombre}. "
            "Cuénteme, ¿qué le gustaría conversar hoy? Estoy aquí para escucharle con calma."
        )
        save_conversation(response, "conversacion_libre", message)
        return jsonify({"response": response, "end_call": False, "buttons": None, "step": "conversacion_libre"})

    # ── Si no se reconoció intención, delegamos al LLM con contexto ────
    context = (
        f"Usuario adulto mayor: {nombre}. "
        f"Ciudad: {ciudad}. "
        "Conversación por voz. Responde con calidez, paciencia, sin tecnicismos."
    )
    rag_response = None
    if RAG_AVAILABLE:
        try:
            docs = search_knowledge(message, n_results=3)
            if docs:
                rag_parts = [f"[Fuente: {d['source']}]\n{d['text']}" for d in docs]
                rag_context = "\n---\n".join(rag_parts)
                llm_resp = get_llm_response(
                    message, context=f"{context}\n\nConocimiento relevante:\n{rag_context}"
                )
                rag_response = llm_resp if llm_resp else None
        except Exception as e:
            app.logger.error(f"RAG error: {e}")
    if rag_response:
        response = rag_response
    else:
        llm_resp = get_llm_response(message, context=context)
        response = llm_resp if llm_resp else (
            f"Disculpe, no alcancé a entender bien. ¿Podría repetirlo con calma, por favor, {nombre}?"
        )
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
