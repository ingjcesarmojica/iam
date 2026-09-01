-- Migracion: Agregar campos del adulto mayor a tabla usuarios
-- Ejecutar en Supabase SQL Editor

-- Agregar columna ciudad (para clima y servicios locales)
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ciudad TEXT;

-- Agregar columna preferencias (géneros musicales, emisoras favoritas, etc.)
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS preferencias TEXT;

-- Crear índice por ciudad para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_usuarios_ciudad ON usuarios(ciudad);

-- Tabla de sesiones de voz con IAM
CREATE TABLE IF NOT EXISTS llamadas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_nombre TEXT,
    usuario_ciudad TEXT,
    duracion_segundos INTEGER DEFAULT 0,
    paso_final TEXT,                  -- 'saludo_inicial', 'conversar', 'despedida', etc.
    estado TEXT DEFAULT 'completada', -- 'completada', 'interrumpida'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llamadas_nombre ON llamadas(usuario_nombre);
CREATE INDEX IF NOT EXISTS idx_llamadas_fecha ON llamadas(created_at);

COMMENT ON TABLE llamadas IS 'Registro de sesiones de voz con IAM (Asistente para el Adulto Mayor).';
