-- ============================================================================
-- EJEMPLOS DE INSERCIÓN DE REGLAS DE NEGOCIO (CORREGIDO)
-- Ejemplos en los 3 niveles: GLOBAL, LÍNEA DE NEGOCIO, EMPRESA
-- ============================================================================

-- ============================================================================
-- NIVEL 1: REGLAS GLOBALES (Aplican a TODAS las empresas)
-- ============================================================================

-- REGLA 1.1: Validación de Email
DECLARE @json_condiciones NVARCHAR(MAX) = N'[
    {
        "campo": "email",
        "operador": "eq",
        "valor": "valido",
        "orden": 1
    }
]';

DECLARE @json_acciones NVARCHAR(MAX) = N'[
    {
        "tipo": "permitir",
        "detalles": {},
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

PRINT 'REGLA 1.1 creada: validacion_email_global';

GO

-- REGLA 1.2: Validación de Moneda (Valores > 0)
DECLARE @json_condiciones_2 NVARCHAR(MAX) = N'[
    {
        "campo": "monto",
        "operador": "gte",
        "valor": "0",
        "orden": 1
    }
]';

DECLARE @json_acciones_2 NVARCHAR(MAX) = N'[
    {
        "tipo": "permitir",
        "detalles": {},
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
    @json_condiciones = @json_condiciones_2,
    @json_acciones = @json_acciones_2;

PRINT 'REGLA 1.2 creada: validacion_monto_minimo';

GO

-- REGLA 1.3: Validación de Estado
DECLARE @json_condiciones_3 NVARCHAR(MAX) = N'[
    {
        "campo": "estado_documento",
        "operador": "en",
        "valor": "activo,procesado,pendiente",
        "orden": 1
    }
]';

DECLARE @json_acciones_3 NVARCHAR(MAX) = N'[
    {
        "tipo": "permitir",
        "detalles": {},
        "orden": 1
    }
]';

EXEC sp_crear_regla_negocio
    @id_regla = 'validacion_estado_documento',
    @nombre = 'Validación de Estado de Documento',
    @descripcion = 'El estado debe ser válido',
    @nivel_alcance = 'global',
    @prioridad = 90,
    @creada_por = 'sistema',
    @json_condiciones = @json_condiciones_3,
    @json_acciones = @json_acciones_3;

PRINT 'REGLA 1.3 creada: validacion_estado_documento';

GO

-- ============================================================================
-- NIVEL 2: REGLAS POR LÍNEA DE NEGOCIO
-- ============================================================================

-- REGLA 2.1: Límite de Descuento - RETAIL
DECLARE @json_cond_2_1 NVARCHAR(MAX) = N'[
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

DECLARE @json_acc_2_1 NVARCHAR(MAX) = N'[
    {
        "tipo": "permitir",
        "detalles": {},
        "orden": 1
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
    @json_condiciones = @json_cond_2_1,
    @json_acciones = @json_acc_2_1;

PRINT 'REGLA 2.1 creada: limite_descuento_retail';

GO

-- REGLA 2.2: Límite de Crédito - RETAIL
DECLARE @json_cond_2_2 NVARCHAR(MAX) = N'[
    {
        "campo": "monto_solicitud",
        "operador": "lte",
        "valor": "50000",
        "orden": 1
    }
]';

DECLARE @json_acc_2_2 NVARCHAR(MAX) = N'[
    {
        "tipo": "permitir",
        "detalles": {},
        "orden": 1
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
    @json_condiciones = @json_cond_2_2,
    @json_acciones = @json_acc_2_2;

PRINT 'REGLA 2.2 creada: limite_credito_retail';

GO

-- REGLA 2.3: Comisión por Venta - AUTOMOTRIZ
DECLARE @json_cond_2_3 NVARCHAR(MAX) = N'[
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

DECLARE @json_acc_2_3 NVARCHAR(MAX) = N'[
    {
        "tipo": "calcular",
        "detalles": {"variable": "comision", "formula": "monto * 0.05"},
        "orden": 1
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
    @json_condiciones = @json_cond_2_3,
    @json_acciones = @json_acc_2_3;

PRINT 'REGLA 2.3 creada: comision_venta_automotriz';

GO

-- REGLA 2.4: Límite de Crédito - MAQUINARIA
DECLARE @json_cond_2_4 NVARCHAR(MAX) = N'[
    {
        "campo": "monto_solicitud",
        "operador": "lte",
        "valor": "500000",
        "orden": 1
    }
]';

DECLARE @json_acc_2_4 NVARCHAR(MAX) = N'[
    {
        "tipo": "permitir",
        "detalles": {},
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
    @json_condiciones = @json_cond_2_4,
    @json_acciones = @json_acc_2_4;

PRINT 'REGLA 2.4 creada: limite_credito_maquinaria';

GO

-- ============================================================================
-- NIVEL 3: REGLAS POR EMPRESA
-- ============================================================================

-- REGLA 3.1: Descuento VIP - CASAB JOYERÍA (empresa_id=523)
DECLARE @json_cond_3_1 NVARCHAR(MAX) = N'[
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

DECLARE @json_acc_3_1 NVARCHAR(MAX) = N'[
    {
        "tipo": "calcular",
        "detalles": {"variable": "descuento_vip", "formula": "monto * 0.25"},
        "orden": 1
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
    @json_condiciones = @json_cond_3_1,
    @json_acciones = @json_acc_3_1;

PRINT 'REGLA 3.1 creada: descuento_vip_casab';

GO

-- REGLA 3.2: Retención ISR - CASAB JOYERÍA (empresa_id=523)
DECLARE @json_cond_3_2 NVARCHAR(MAX) = N'[
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

DECLARE @json_acc_3_2 NVARCHAR(MAX) = N'[
    {
        "tipo": "calcular",
        "detalles": {"variable": "retencion_isr", "formula": "monto * 0.025"},
        "orden": 1
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
    @json_condiciones = @json_cond_3_2,
    @json_acciones = @json_acc_3_2;

PRINT 'REGLA 3.2 creada: retencion_isr_casab';

GO

-- REGLA 3.3: Retención FUENTE - CASAB JOYERÍA (empresa_id=523)
DECLARE @json_cond_3_3 NVARCHAR(MAX) = N'[
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

DECLARE @json_acc_3_3 NVARCHAR(MAX) = N'[
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
    @json_condiciones = @json_cond_3_3,
    @json_acciones = @json_acc_3_3;

PRINT 'REGLA 3.3 creada: retencion_fuente_casab';

GO

-- REGLA 3.4: Descuento VIP - IMVESA (empresa_id=601)
DECLARE @json_cond_3_4 NVARCHAR(MAX) = N'[
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

DECLARE @json_acc_3_4 NVARCHAR(MAX) = N'[
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
    @json_condiciones = @json_cond_3_4,
    @json_acciones = @json_acc_3_4;

PRINT 'REGLA 3.4 creada: descuento_vip_imvesa';

GO

-- REGLA 3.5: Validación de Bodega Permitidas - HND (empresa_id=100)
DECLARE @json_cond_3_5 NVARCHAR(MAX) = N'[
    {
        "campo": "id_bodega",
        "operador": "en",
        "valor": "1,2",
        "orden": 1
    }
]';

DECLARE @json_acc_3_5 NVARCHAR(MAX) = N'[
    {
        "tipo": "permitir",
        "detalles": {},
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
    @json_condiciones = @json_cond_3_5,
    @json_acciones = @json_acc_3_5;

PRINT 'REGLA 3.5 creada: bodegas_validas_hnd';

GO

-- ============================================================================
-- EJEMPLOS DE EVALUACIÓN DE REGLAS
-- ============================================================================

PRINT '';
PRINT '========================================';
PRINT 'EVALUANDO REGLA: Descuento VIP - Casab';
PRINT '========================================';

DECLARE @contexto_casab NVARCHAR(MAX) = N'{
    "id_cliente": 1050,
    "segmento_cliente": "VIP",
    "monto": 15000,
    "tipo_documento": "factura",
    "id_empresa": 523
}';

EXEC sp_evaluar_regla_jerarquica
    @id_regla_param = 'descuento_vip_casab',
    @id_empresa_param = 523,
    @linea_negocio_param = 'RETAIL',
    @json_contexto = @contexto_casab,
    @evaluada_por = 'usuario@casab.hn';

GO

-- Evaluar regla de retención ISR
PRINT '';
PRINT '========================================';
PRINT 'EVALUANDO REGLA: Retención ISR - Casab';
PRINT '========================================';

DECLARE @contexto_retencion NVARCHAR(MAX) = N'{
    "id_cliente": 1050,
    "monto": 5000,
    "tipo_documento": "factura",
    "id_empresa": 523
}';

EXEC sp_evaluar_regla_jerarquica
    @id_regla_param = 'retencion_isr_casab',
    @id_empresa_param = 523,
    @linea_negocio_param = 'RETAIL',
    @json_contexto = @contexto_retencion,
    @evaluada_por = 'usuario@casab.hn';

GO

-- ============================================================================
-- EJEMPLOS DE LISTADO Y CONSULTAS
-- ============================================================================

PRINT '';
PRINT '========================================';
PRINT 'REGLAS GLOBALES ACTIVAS';
PRINT '========================================';

EXEC sp_listar_reglas_por_alcance
    @nivel_alcance_param = 'global',
    @estado_param = 'activa';

GO

PRINT '';
PRINT '========================================';
PRINT 'REGLAS RETAIL ACTIVAS';
PRINT '========================================';

EXEC sp_listar_reglas_por_alcance
    @nivel_alcance_param = 'linea_negocio',
    @linea_negocio_param = 'RETAIL',
    @estado_param = 'activa';

GO

PRINT '';
PRINT '========================================';
PRINT 'REGLAS CASAB (empresa_id=523)';
PRINT '========================================';

EXEC sp_listar_reglas_por_alcance
    @nivel_alcance_param = 'empresa',
    @id_empresa_param = 523,
    @estado_param = 'activa';

GO

PRINT '';
PRINT '========================================';
PRINT 'AUDITORÍA CASAB (últimos 30 días)';
PRINT '========================================';

EXEC sp_obtener_auditoria
    @id_empresa_param = 523,
    @dias_param = 30,
    @limite_param = 50;

GO

PRINT '';
PRINT '========================================';
PRINT 'RESUMEN DE REGLAS ACTIVAS';
PRINT '========================================';

SELECT * FROM vw_reglas_activas_por_nivel;

GO

PRINT '';
PRINT '========================================';
PRINT 'VISTA: Reglas por Empresa';
PRINT '========================================';

SELECT TOP 10 * FROM vw_reglas_por_empresa;

GO

PRINT '';
PRINT '✅ TODAS LAS REGLAS FUERON CREADAS EXITOSAMENTE';

GO
