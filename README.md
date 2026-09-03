# IAM — Asistente Integral para el Adulto Mayor

IAM es un asistente de voz pensado para acompañar y ayudar a personas
adultas mayores en Colombia y América Latina. Su propósito es informar
y orientar en seis áreas:

- **Módulo Salud** (enfermería básica): mediciones comunes
  (presión arterial, frecuencia cardíaca, glucosa, temperatura,
  saturación de oxígeno), recordatorios de medicamentos y orientación
  general sin diagnosticar.
- **Módulo Brigadista** (emergencias y seguridad): protocolos de
  terremoto, incendio, inundación, kit de emergencia, riesgos del
  hogar y números de emergencia locales.
- **Módulo Hogar** (mantenimiento y seguridad doméstica): guías
  simples para tareas del hogar (cambiar foco, resetear breaker, fugas,
  conexiones, prevención de caídas) y derivación a profesional cuando
  hay riesgo.
- **Apoyo cotidiano**: fecha y hora, clima, indicadores económicos
  (dólar, euro, café), música, radio, televisión y noticias.
- **Conversación amable**: compañía para quien quiera simplemente
  charlar.

## Características
- Voz cálida y paciente en español neutro/colombiano (edge-tts).
- Reconoce intenciones de salud, emergencias, hogar, fecha, clima,
  indicadores, música, radio, TV, noticias y conversación.
- Prioriza la seguridad: ante síntomas de alarma o emergencias activas,
  indica de inmediato llamar a la línea 123 (Colombia) o a un familiar.
- NUNCA diagnostica, receta ni ajusta medicamentos; NUNCA guía tareas
  de gas, electricidad de alto riesgo o estructuras.
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
