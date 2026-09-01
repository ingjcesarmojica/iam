# IAM — Asistente de IA para el Adulto Mayor

IAM es un asistente de voz pensado para acompañar y ayudar a personas
mayores en Colombia y América Latina con la tecnología del día a día:
fecha y hora, clima, indicadores económicos (dólar, euro, café), música,
radio, televisión, noticias y conversación amable.

## Características
- Voz cálida y paciente en español neutro/colombiano (edge-tts).
- Reconoce intenciones como pedir el clima, la fecha, el dólar, noticias,
  música o sintonizar radio/TV.
- Prioriza la seguridad: si el adulto mayor menciona una emergencia,
  sugiere contactar familiares o la línea 123.
- Se integra con OpenRouter (LLM principal), Gemini (fallback),
  Pinecone (RAG), Supabase (datos) y edge-tts (voz).

## Instalación
```bash
pip install -r requirements.txt
cp .env.example .env  # completar las claves
python app.py
```

## Uso
Abrir `http://localhost:5000` en el navegador y hablar con IAM por voz.
