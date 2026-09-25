-- ============================================================================
-- EJEMPLOS DE INSERCIÓN DE REGLAS DE NEGOCIO
-- Ejemplos en los 3 niveles: GLOBAL, LÍNEA DE NEGOCIO, EMPRESA
-- ============================================================================

-- ============================================================================
-- NIVEL 1: REGLAS GLOBALES (Aplican a TODAS las empresas)
-- ============================================================================

-- REGLA 1.1: Validación de Email
DECLARE @json_condiciones NVARCHAR(MAX) = N'[
    {
        "campo": "email",
        "operador": "regex",
        "valor": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
        "orden": 1
    }
]';

DECLARE @json_acciones NVARCHAR(MAX) = N'[
    {
        "tipo": "permitir",
        "orden": 1
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'validacion_email_global',
    @nombre = 'Validación de Email',
    @descripcion = 'Valida formato de email (aplica a todas las empresas)',
    @nivel_alcance = 'global',
    @prioridad = 100,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 1.2: Validación de Moneda (Valores > 0)
SET @json_condiciones = N'[
    {
        "campo": "monto",
        "operador": "gte",
        "valor": "0",
        "orden": 1
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "permitir",
        "orden": 1
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'validacion_monto_minimo',
    @nombre = 'Monto Mínimo Válido',
    @descripcion = 'El monto debe ser mayor a cero',
    @nivel_alcance = 'global',
    @prioridad = 95,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 1.3: Validación de Rango de Fechas
SET @json_condiciones = N'[
    {
        "campo": "fecha_documento",
        "operador": "gte",
        "valor": "2024-01-01",
        "orden": 1
    },
    {
        "campo": "fecha_documento",
        "operador": "lte",
        "valor": "2099-12-31",
        "orden": 2
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "permitir",
        "orden": 1
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'validacion_fecha_documento',
    @nombre = 'Validación de Fecha de Documento',
    @descripcion = 'La fecha debe estar en rango válido',
    @nivel_alcance = 'global',
    @prioridad = 90,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- ============================================================================
-- NIVEL 2: REGLAS POR LÍNEA DE NEGOCIO
-- ============================================================================

-- REGLA 2.1: Límite de Descuento - RETAIL
SET @json_condiciones = N'[
    {
        "campo": "porcentaje_descuento",
        "operador": "gte",
        "valor": "0",
        "orden": 1
    },
    {
        "campo": "porcentaje_descuento",
        "operador": "lte",
        "valor": "30",
        "orden": 2
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "permitir",
        "orden": 1
    },
    {
        "tipo": "registrar",
        "detalles": {"mensaje": "Descuento dentro del límite RETAIL (máximo 30%)"},
        "orden": 2
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'limite_descuento_retail',
    @nombre = 'Límite de Descuento - RETAIL',
    @descripcion = 'Descuento máximo del 30% para línea RETAIL',
    @nivel_alcance = 'linea_negocio',
    @linea_negocio = 'RETAIL',
    @prioridad = 85,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 2.2: Límite de Crédito - RETAIL
SET @json_condiciones = N'[
    {
        "campo": "monto_solicitud",
        "operador": "lte",
        "valor": "50000",
        "orden": 1
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "permitir",
        "orden": 1
    },
    {
        "tipo": "registrar",
        "detalles": {"mensaje": "Crédito dentro del límite RETAIL (máximo $50,000)"},
        "orden": 2
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'limite_credito_retail',
    @nombre = 'Límite de Crédito - RETAIL',
    @descripcion = 'Crédito máximo de $50,000 para línea RETAIL',
    @nivel_alcance = 'linea_negocio',
    @linea_negocio = 'RETAIL',
    @prioridad = 80,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 2.3: Comisión por Venta - AUTOMOTRIZ
SET @json_condiciones = N'[
    {
        "campo": "tipo_documento",
        "operador": "eq",
        "valor": "factura",
        "orden": 1
    },
    {
        "campo": "monto",
        "operador": "gte",
        "valor": "1000",
        "orden": 2
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "calcular",
        "detalles": {"variable": "comision", "formula": "monto * 0.05"},
        "orden": 1
    },
    {
        "tipo": "registrar",
        "detalles": {"mensaje": "Comisión automática 5% calculada para AUTOMOTRIZ"},
        "orden": 2
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'comision_venta_automotriz',
    @nombre = 'Comisión por Venta - AUTOMOTRIZ',
    @descripcion = 'Comisión del 5% en facturas AUTOMOTRIZ >= $1,000',
    @nivel_alcance = 'linea_negocio',
    @linea_negocio = 'AUTOMOTRIZ',
    @prioridad = 75,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 2.4: Límite de Crédito - MAQUINARIA
SET @json_condiciones = N'[
    {
        "campo": "monto_solicitud",
        "operador": "lte",
        "valor": "500000",
        "orden": 1
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "permitir",
        "orden": 1
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'limite_credito_maquinaria',
    @nombre = 'Límite de Crédito - MAQUINARIA',
    @descripcion = 'Crédito máximo de $500,000 para línea MAQUINARIA',
    @nivel_alcance = 'linea_negocio',
    @linea_negocio = 'MAQUINARIA',
    @prioridad = 70,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- ============================================================================
-- NIVEL 3: REGLAS POR EMPRESA
-- ============================================================================

-- REGLA 3.1: Descuento VIP - CASAB JOYERÍA (empresa_id=523)
SET @json_condiciones = N'[
    {
        "campo": "segmento_cliente",
        "operador": "eq",
        "valor": "VIP",
        "orden": 1
    },
    {
        "campo": "monto",
        "operador": "gte",
        "valor": "5000",
        "orden": 2
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "calcular",
        "detalles": {"variable": "descuento_vip", "formula": "monto * 0.25"},
        "orden": 1
    },
    {
        "tipo": "asignar_campo",
        "detalles": {"campo": "estado_documento", "valor": "descuento_aplicado"},
        "orden": 2
    },
    {
        "tipo": "notificar",
        "detalles": {"destino": "gerencia", "mensaje": "Descuento VIP 25% aplicado en Casab"},
        "orden": 3
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'descuento_vip_casab',
    @nombre = 'Descuento VIP - Casab Joyería',
    @descripcion = 'Descuento del 25% para clientes VIP de Casab (empresa_id=523)',
    @nivel_alcance = 'empresa',
    @id_empresa = 523,
    @prioridad = 95,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 3.2: Retención ISR - CASAB JOYERÍA (empresa_id=523)
SET @json_condiciones = N'[
    {
        "campo": "tipo_documento",
        "operador": "eq",
        "valor": "factura",
        "orden": 1
    },
    {
        "campo": "monto",
        "operador": "gte",
        "valor": "1000",
        "orden": 2
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "calcular",
        "detalles": {"variable": "retencion_isr", "formula": "monto * 0.025"},
        "orden": 1
    },
    {
        "tipo": "asignar_campo",
        "detalles": {"campo": "estado_retencion", "valor": "retencion_pendiente"},
        "orden": 2
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'retencion_isr_casab',
    @nombre = 'Retención ISR - Casab',
    @descripcion = 'Retención ISR 2.5% en facturas Casab >= $1,000',
    @nivel_alcance = 'empresa',
    @id_empresa = 523,
    @prioridad = 85,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 3.3: Retención FUENTE - CASAB JOYERÍA (empresa_id=523)
SET @json_condiciones = N'[
    {
        "campo": "tipo_documento",
        "operador": "en",
        "valor": "factura,nota_credito",
        "orden": 1
    },
    {
        "campo": "monto",
        "operador": "gte",
        "valor": "100",
        "orden": 2
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "calcular",
        "detalles": {"variable": "retencion_fuente", "formula": "monto * 0.03"},
        "orden": 1
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'retencion_fuente_casab',
    @nombre = 'Retención Fuente - Casab',
    @descripcion = 'Retención Fuente 3% en documentos Casab >= $100',
    @nivel_alcance = 'empresa',
    @id_empresa = 523,
    @prioridad = 80,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 3.4: Límite de Crédito - CASAB JOYERÍA (empresa_id=523)
SET @json_condiciones = N'[
    {
        "campo": "saldo_disponible",
        "operador": "lt",
        "valor": "0",
        "orden": 1
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "bloquear",
        "detalles": {"razon": "Límite de crédito excedido en Casab"},
        "orden": 1
    },
    {
        "tipo": "notificar",
        "detalles": {"destino": "cartera", "mensaje": "Cliente excedió límite de crédito"},
        "orden": 2
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'limite_credito_casab',
    @nombre = 'Límite de Crédito - Casab',
    @descripcion = 'Bloquea operaciones si saldo disponible es negativo',
    @nivel_alcance = 'empresa',
    @id_empresa = 523,
    @prioridad = 100,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 3.5: Descuento VIP - IMVESA (empresa_id=601)
SET @json_condiciones = N'[
    {
        "campo": "segmento_cliente",
        "operador": "eq",
        "valor": "VIP",
        "orden": 1
    },
    {
        "campo": "monto",
        "operador": "gte",
        "valor": "3000",
        "orden": 2
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "calcular",
        "detalles": {"variable": "descuento_vip", "formula": "monto * 0.15"},
        "orden": 1
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'descuento_vip_imvesa',
    @nombre = 'Descuento VIP - Imvesa',
    @descripcion = 'Descuento del 15% para clientes VIP de Imvesa (empresa_id=601)',
    @nivel_alcance = 'empresa',
    @id_empresa = 601,
    @prioridad = 90,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- REGLA 3.6: Validación de Bodega Permitidas - HND (empresa_id=100)
SET @json_condiciones = N'[
    {
        "campo": "id_bodega",
        "operador": "en",
        "valor": "1,2",
        "orden": 1
    }
]';

SET @json_acciones = N'[
    {
        "tipo": "permitir",
        "orden": 1
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'bodegas_validas_hnd',
    @nombre = 'Validación de Bodegas - HND',
    @descripcion = 'Solo bodegas 1 y 2 permitidas en HND',
    @nivel_alcance = 'empresa',
    @id_empresa = 100,
    @prioridad = 85,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones,
    @json_acciones = @json_acciones;

-- ============================================================================
-- EJEMPLOS DE EVALUACIÓN DE REGLAS
-- ============================================================================

-- Evaluar regla de descuento VIP en Casab
DECLARE @contexto_casab NVARCHAR(MAX) = N'{
    "id_cliente": 1050,
    "segmento_cliente": "VIP",
    "monto": 15000,
    "tipo_documento": "factura",
    "id_empresa": 523
}';

PRINT '========================================';
PRINT 'Evaluando: Descuento VIP - Casab';
PRINT '========================================';
EXEC sp_evaluar_regla_jerarquica
    @id_regla = 'descuento_vip_casab',
    @id_empresa = 523,
    @linea_negocio = 'RETAIL',
    @json_contexto = @contexto_casab,
    @evaluada_por = 'usuario@casab.hn';

-- Evaluar regla de retención ISR en Casab
DECLARE @contexto_retencion NVARCHAR(MAX) = N'{
    "id_cliente": 1050,
    "monto": 5000,
    "tipo_documento": "factura",
    "id_empresa": 523
}';

PRINT '========================================';
PRINT 'Evaluando: Retención ISR - Casab';
PRINT '========================================';
EXEC sp_evaluar_regla_jerarquica
    @id_regla = 'retencion_isr_casab',
    @id_empresa = 523,
    @linea_negocio = 'RETAIL',
    @json_contexto = @contexto_retencion,
    @evaluada_por = 'usuario@casab.hn';

-- ============================================================================
-- EJEMPLOS DE LISTADO Y CONSULTAS
-- ============================================================================

-- Listar todas las reglas GLOBALES
PRINT '========================================';
PRINT 'Reglas GLOBALES';
PRINT '========================================';
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance = 'global',
    @estado = 'activa';

-- Listar reglas por línea de negocio: RETAIL
PRINT '========================================';
PRINT 'Reglas RETAIL';
PRINT '========================================';
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance = 'linea_negocio',
    @linea_negocio = 'RETAIL',
    @estado = 'activa';

-- Listar reglas específicas de Casab (empresa_id=523)
PRINT '========================================';
PRINT 'Reglas CASAB (empresa_id=523)';
PRINT '========================================';
EXEC sp_listar_reglas_por_alcance
    @nivel_alcance = 'empresa',
    @id_empresa = 523,
    @estado = 'activa';

-- Ver auditoría de evaluaciones de Casab
PRINT '========================================';
PRINT 'Auditoría CASAB (últimos 30 días)';
PRINT '========================================';
EXEC sp_obtener_auditoria
    @id_empresa = 523,
    @dias = 30,
    @limite = 50;

-- Ver resumen de auditoría
PRINT '========================================';
PRINT 'Resumen de Auditoría';
PRINT '========================================';
SELECT * FROM vw_resumen_auditoria
WHERE id_empresa = 523;

-- Ver reglas activas por nivel
PRINT '========================================';
PRINT 'Resumen de Reglas Activas';
PRINT '========================================';
SELECT * FROM vw_reglas_activas_por_nivel;
