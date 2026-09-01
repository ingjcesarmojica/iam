-- ================================================
-- SCHEMA: Base de datos IAM (Asistente para el Adulto Mayor)
-- Supabase (PostgreSQL)
-- Ejecutar en SQL Editor de Supabase Dashboard
-- ================================================

-- ── Tabla: usuarios ─────────────────────────────────────────────────
-- Registro básico del adulto mayor. No se almacenan datos sensibles
-- (no se piden documentos de identidad, claves ni números de tarjeta).
CREATE TABLE IF NOT EXISTS usuarios (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nombre TEXT NOT NULL,
    email TEXT,                       -- opcional, solo si el usuario lo comparte
    telefono TEXT,                    -- opcional
    ciudad TEXT,                      -- ciudad de residencia (para clima y servicios locales)
    preferencias TEXT,                -- JSON libre: géneros musicales, emisoras favoritas, etc.
    paso_actual TEXT DEFAULT 'saludo_inicial', -- paso del guion: saludo_inicial, conversar, despedida
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE usuarios IS 'Registro de adultos mayores que usan IAM. Solo datos básicos.';

-- ── Tabla: recordatorios ────────────────────────────────────────────
-- Recordatorios personales del adulto mayor: citas médicas, cumpleaños,
-- eventos familiares, tomas de medicamentos, etc.
CREATE TABLE IF NOT EXISTS recordatorios (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_nombre TEXT NOT NULL,
    usuario_email TEXT,
    titulo TEXT NOT NULL,             -- ej: 'Cita con el cardiólogo'
    descripcion TEXT,
    fecha DATE NOT NULL,
    hora TEXT,                        -- 'HH:MM' opcional
    tipo TEXT,                        -- 'medico', 'cumpleanos', 'medicamento', 'familia', 'otro'
    estado TEXT DEFAULT 'activo',     -- 'activo', 'completado', 'cancelado'
    created_at TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE recordatorios IS 'Recordatorios personales del adulto mayor (citas médicas, cumpleaños, etc.).';

-- ── Tabla: conversaciones ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversaciones (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_nombre TEXT,
    usuario_ciudad TEXT,
    mensaje_usuario TEXT,
    respuesta_agente TEXT,
    paso TEXT,                        -- paso del guion en el que estaba
    created_at TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE conversaciones IS 'Historial de conversaciones con IAM para personalizar la atención.';

-- ── Tabla: consultas_adicionales ────────────────────────────────────
-- Preguntas sueltas o seguimiento cuando la respuesta por voz no fue suficiente.
CREATE TABLE IF NOT EXISTS consultas_adicionales (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_nombre TEXT,
    usuario_ciudad TEXT,
    consulta TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Tabla: llamadas ─────────────────────────────────────────────────
-- Registro de las sesiones de voz con IAM (antes 'llamadas').
CREATE TABLE IF NOT EXISTS llamadas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_nombre TEXT,
    usuario_ciudad TEXT,
    duracion_segundos INTEGER DEFAULT 0,
    paso_final TEXT,                  -- 'saludo_inicial', 'conversar', 'despedida', etc.
    estado TEXT DEFAULT 'completada', -- 'completada', 'interrumpida'
    created_at TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE llamadas IS 'Registro de sesiones de voz con IAM.';

-- ── Índices para búsquedas rápidas ──────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_usuarios_nombre ON usuarios(nombre);
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email);
CREATE INDEX IF NOT EXISTS idx_recordatorios_nombre ON recordatorios(usuario_nombre);
CREATE INDEX IF NOT EXISTS idx_recordatorios_fecha ON recordatorios(fecha);
CREATE INDEX IF NOT EXISTS idx_recordatorios_estado ON recordatorios(estado);
CREATE INDEX IF NOT EXISTS idx_conversaciones_nombre ON conversaciones(usuario_nombre);
CREATE INDEX IF NOT EXISTS idx_conversaciones_fecha ON conversaciones(created_at);

-- ── RLS (Row Level Security) - Opcional ─────────────────────────────
-- Habilitar si se usa autenticación con Supabase Auth
-- ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE recordatorios ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE conversaciones ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE llamadas ENABLE ROW LEVEL SECURITY;

-- ── Vista: próximos recordatorios ───────────────────────────────────
CREATE OR REPLACE VIEW vista_recordatorios_proximos AS
SELECT
    r.id,
    r.usuario_nombre,
    r.titulo,
    r.descripcion,
    r.fecha,
    r.hora,
    r.tipo,
    r.estado,
    r.created_at
FROM recordatorios r
WHERE r.estado = 'activo' AND r.fecha >= CURRENT_DATE
ORDER BY r.fecha ASC, r.hora ASC NULLS LAST;

-- ── Vista de estadísticas IAM ───────────────────────────────────────
CREATE OR REPLACE VIEW vista_estadisticas_iam AS
SELECT
    (SELECT COUNT(*) FROM usuarios) AS total_usuarios,
    (SELECT COUNT(*) FROM recordatorios WHERE estado = 'activo') AS recordatorios_activos,
    (SELECT COUNT(*) FROM conversaciones) AS total_conversaciones,
    (SELECT COUNT(*) FROM llamadas) AS total_sesiones;

-- ================================================
-- FIN DEL SCHEMA
-- ================================================