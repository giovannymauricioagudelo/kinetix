"""
BusinessRulesAgent - Router FastAPI
8 Endpoints para evaluación jerárquica de reglas de negocio
Motor: SQL Server con 3 niveles (global, línea negocio, empresa)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import pyodbc
import json
from datetime import datetime
import logging

# Logger
logger = logging.getLogger(__name__)

# Router
router = APIRouter()

# ============================================================================
# MODELOS PYDANTIC
# ============================================================================

class Condicion(BaseModel):
    """Modelo de una condición de regla"""
    campo: str = Field(..., description="Campo a evaluar")
    operador: str = Field(..., description="eq, neq, gt, gte, lt, lte, en, no_en, contiene, regex")
    valor: str = Field(..., description="Valor de comparación")
    orden: int = Field(..., description="Orden de evaluación")


class Accion(BaseModel):
    """Modelo de una acción de regla"""
    tipo: str = Field(..., description="calcular, asignar_campo, bloquear, permitir, notificar, registrar")
    detalles: Dict[str, Any] = Field(..., description="Detalles específicos de la acción")
    orden: int = Field(..., description="Orden de ejecución")


class CrearRegla(BaseModel):
    """Modelo para crear una regla"""
    id_regla: str = Field(..., description="ID único de la regla")
    nombre: str = Field(..., description="Nombre legible")
    descripcion: Optional[str] = Field(None, description="Descripción de la regla")
    nivel_alcance: str = Field(..., description="global, linea_negocio, empresa")
    linea_negocio: Optional[str] = Field(None, description="Requerido si nivel_alcance='linea_negocio'")
    id_empresa: Optional[int] = Field(None, description="Requerido si nivel_alcance='empresa'")
    prioridad: int = Field(50, description="1-100, siendo 100 la máxima")
    condiciones: List[Condicion] = Field(..., description="Array de condiciones")
    acciones: List[Accion] = Field(..., description="Array de acciones")


class ContextoEvaluacion(BaseModel):
    """Modelo para contexto de evaluación"""
    id_cliente: Optional[int] = None
    monto: Optional[float] = None
    segmento_cliente: Optional[str] = None
    tipo_documento: Optional[str] = None
    porcentaje_descuento: Optional[float] = None
    id_bodega: Optional[int] = None
    estado_documento: Optional[str] = None
    saldo_disponible: Optional[float] = None
    monto_solicitud: Optional[float] = None
    
    class Config:
        extra = "allow"  # Permitir campos adicionales


class ActualizarRegla(BaseModel):
    """Modelo para actualizar una regla"""
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    prioridad: Optional[int] = None
    estado: Optional[str] = None
    condiciones: Optional[List[Condicion]] = None
    acciones: Optional[List[Accion]] = None


# ============================================================================
# CONEXIÓN SQL SERVER
# ============================================================================

def get_connection():
    """Obtener conexión a SQL Server"""
    try:
        connection_string = (
            'Driver={ODBC Driver 17 for SQL Server};'
            'Server=localhost;'
            'Database=afp_db;'
            'UID=sa;'
            'PWD=tu_contraseña'  # ⚠️ CAMBIAR POR TU CONTRASEÑA
        )
        conn = pyodbc.connect(connection_string)
        conn.autocommit = True
        return conn
    except pyodbc.Error as e:
        logger.error(f"Error de conexión SQL Server: {e}")
        raise HTTPException(status_code=500, detail=f"Error de conexión: {str(e)}")


# ============================================================================
# ENDPOINT 1: Crear Regla
# ============================================================================

@router.post("/create", summary="Crear nueva regla de negocio")
async def crear_regla(
    regla: CrearRegla,
    creada_por: str = Query(..., description="Usuario que crea la regla")
) -> Dict[str, Any]:
    """
    Crear una nueva regla de negocio en la base de datos.
    
    **Parámetros:**
    - `regla`: Objeto con datos de la regla (id, nombre, alcance, etc)
    - `creada_por`: Usuario que crea la regla (ej: usuario@app.com)
    
    **Niveles de alcance:**
    - `global`: Aplica a TODAS las empresas
    - `linea_negocio`: Aplica a un sector específico (RETAIL, AUTOMOTRIZ, etc)
    - `empresa`: Aplica solo a una empresa (id_empresa obligatorio)
    
    **Ejemplo:**
    ```json
    {
      "id_regla": "descuento_vip_casab",
      "nombre": "Descuento VIP",
      "nivel_alcance": "empresa",
      "id_empresa": 523,
      "prioridad": 95,
      "condiciones": [
        {"campo": "segmento_cliente", "operador": "eq", "valor": "VIP", "orden": 1},
        {"campo": "monto", "operador": "gte", "valor": "5000", "orden": 2}
      ],
      "acciones": [
        {"tipo": "calcular", "detalles": {"variable": "descuento_vip", "formula": "monto * 0.25"}, "orden": 1}
      ]
    }
    ```
    """
    try:
        # Validar
        if regla.nivel_alcance == 'linea_negocio' and not regla.linea_negocio:
            raise HTTPException(status_code=400, detail="linea_negocio es obligatorio cuando nivel_alcance='linea_negocio'")
        if regla.nivel_alcance == 'empresa' and not regla.id_empresa:
            raise HTTPException(status_code=400, detail="id_empresa es obligatorio cuando nivel_alcance='empresa'")
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Convertir condiciones y acciones a JSON
        json_condiciones = json.dumps([
            {
                "campo": c.campo,
                "operador": c.operador,
                "valor": c.valor,
                "orden": c.orden
            }
            for c in regla.condiciones
        ])
        
        json_acciones = json.dumps([
            {
                "tipo": a.tipo,
                "detalles": a.detalles,
                "orden": a.orden
            }
            for a in regla.acciones
        ])
        
        # Ejecutar SP
        cursor.execute("""
            EXEC sp_crear_regla_negocio
                @id_regla = ?,
                @nombre = ?,
                @descripcion = ?,
                @nivel_alcance = ?,
                @linea_negocio = ?,
                @id_empresa = ?,
                @prioridad = ?,
                @creada_por = ?,
                @json_condiciones = ?,
                @json_acciones = ?
        """, (
            regla.id_regla,
            regla.nombre,
            regla.descripcion,
            regla.nivel_alcance,
            regla.linea_negocio,
            regla.id_empresa,
            regla.prioridad,
            creada_por,
            json_condiciones,
            json_acciones
        ))
        
        resultado = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if resultado[0] == 'EXITO':
            return {
                "resultado": "EXITO",
                "id_regla": resultado[1],
                "mensaje": f"Regla '{regla.nombre}' creada exitosamente",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail=f"Error: {resultado[1]}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al crear regla: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 2: Evaluar Regla
# ============================================================================

@router.post("/evaluate", summary="Evaluar regla contra contexto")
async def evaluar_regla(
    id_regla: str = Query(..., description="ID de la regla a evaluar"),
    id_empresa: int = Query(..., description="ID de la empresa en contexto"),
    linea_negocio: str = Query(..., description="Línea de negocio"),
    contexto: ContextoEvaluacion,
    evaluada_por: str = Query("api", description="Usuario que evalúa")
) -> Dict[str, Any]:
    """
    Evaluar una regla de negocio contra un contexto específico.
    
    **Parámetros:**
    - `id_regla`: ID de la regla a evaluar
    - `id_empresa`: ID de la empresa (para contexto jerárquico)
    - `linea_negocio`: Línea de negocio (RETAIL, AUTOMOTRIZ, etc)
    - `contexto`: Datos para evaluar las condiciones
    - `evaluada_por`: Usuario/sistema que evalúa
    
    **Evaluación jerárquica:**
    1. NIVEL 1: Se evalúan reglas GLOBALES (aplican a todas)
    2. NIVEL 2: Se evalúan reglas por LÍNEA DE NEGOCIO
    3. NIVEL 3: Se evalúan reglas por EMPRESA
    
    **Resultado:**
    - `decision`: permitida | bloqueada | condiciones_no_cumplidas | requiere_aprobacion
    - `condiciones_cumplidas`: boolean
    - `valores_calculados`: JSON con variables calculadas
    - `id_auditoria`: ID del registro de auditoría
    
    **Ejemplo:**
    ```json
    {
      "id_cliente": 1050,
      "segmento_cliente": "VIP",
      "monto": 15000,
      "tipo_documento": "factura"
    }
    ```
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Convertir contexto a JSON
        contexto_json = json.dumps(contexto.dict(exclude_none=True))
        
        # Ejecutar SP
        cursor.execute("""
            EXEC sp_evaluar_regla_jerarquica
                @id_regla_param = ?,
                @id_empresa_param = ?,
                @linea_negocio_param = ?,
                @json_contexto = ?,
                @evaluada_por = ?
        """, (id_regla, id_empresa, linea_negocio, contexto_json, evaluada_por))
        
        resultado = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if resultado[0] == 'EXITO':
            return {
                "resultado": "EXITO",
                "id_regla": resultado[1],
                "condiciones_cumplidas": bool(resultado[2]),
                "decision": resultado[3],
                "valores_calculados": json.loads(resultado[4]) if resultado[4] and resultado[4] != '{}' else {},
                "id_auditoria": resultado[5],
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail=f"Error: {resultado[1]}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al evaluar regla: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 3: Listar Reglas
# ============================================================================

@router.get("/list", summary="Listar reglas con filtros")
async def listar_reglas(
    nivel_alcance: Optional[str] = Query(None, description="global, linea_negocio, empresa"),
    linea_negocio: Optional[str] = Query(None, description="RETAIL, AUTOMOTRIZ, MAQUINARIA, etc"),
    id_empresa: Optional[int] = Query(None, description="ID de empresa para filtrar"),
    estado: str = Query("activa", description="activa, inactiva, prueba, archivada")
) -> Dict[str, Any]:
    """
    Listar reglas de negocio con filtros opcionales.
    
    **Filtros disponibles:**
    - `nivel_alcance`: Filtrar por nivel (global, linea_negocio, empresa)
    - `linea_negocio`: Filtrar por línea de negocio específica
    - `id_empresa`: Filtrar por empresa específica
    - `estado`: Filtrar por estado (default: activa)
    
    **Ejemplo:**
    ```
    GET /api/v1/rules/list?nivel_alcance=empresa&id_empresa=523&estado=activa
    ```
    
    **Respuesta:**
    ```json
    {
      "resultado": "EXITO",
      "total": 3,
      "reglas": [
        {
          "id_regla": "descuento_vip_casab",
          "nombre": "Descuento VIP - Casab",
          "nivel_alcance": "empresa",
          "prioridad": 95,
          "total_condiciones": 2,
          "total_acciones": 1
        }
      ]
    }
    ```
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            EXEC sp_listar_reglas_por_alcance
                @nivel_alcance_param = ?,
                @linea_negocio_param = ?,
                @id_empresa_param = ?,
                @estado_param = ?
        """, (nivel_alcance, linea_negocio, id_empresa, estado))
        
        reglas = []
        for row in cursor.fetchall():
            reglas.append({
                "id_regla": row[0],
                "nombre": row[1],
                "descripcion": row[2],
                "nivel_alcance": row[3],
                "linea_negocio": row[4],
                "id_empresa": row[5],
                "prioridad": row[6],
                "estado": row[7],
                "fecha_creacion": row[8].isoformat() if row[8] else None,
                "creada_por": row[9],
                "total_condiciones": row[10],
                "total_acciones": row[11]
            })
        
        cursor.close()
        conn.close()
        
        return {
            "resultado": "EXITO",
            "total": len(reglas),
            "reglas": reglas,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al listar reglas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 4: Actualizar Regla
# ============================================================================

@router.put("/{rule_id}", summary="Actualizar regla existente")
async def actualizar_regla(
    rule_id: str,
    regla: ActualizarRegla,
    actualizada_por: str = Query(..., description="Usuario que actualiza")
) -> Dict[str, Any]:
    """
    Actualizar una regla de negocio existente.
    
    **Parámetros:**
    - `rule_id`: ID de la regla a actualizar
    - `regla`: Campos a actualizar (solo los que cambien)
    - `actualizada_por`: Usuario que hace la actualización
    
    **Campos actualizables:**
    - nombre
    - descripcion
    - prioridad
    - estado (activa, inactiva, prueba, archivada)
    - condiciones (reemplaza todas)
    - acciones (reemplaza todas)
    
    **Ejemplo:**
    ```json
    {
      "prioridad": 90,
      "estado": "prueba",
      "condiciones": [...]
    }
    ```
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Convertir condiciones y acciones a JSON si existen
        json_condiciones = None
        if regla.condiciones:
            json_condiciones = json.dumps([
                {
                    "campo": c.campo,
                    "operador": c.operador,
                    "valor": c.valor,
                    "orden": c.orden
                }
                for c in regla.condiciones
            ])
        
        json_acciones = None
        if regla.acciones:
            json_acciones = json.dumps([
                {
                    "tipo": a.tipo,
                    "detalles": a.detalles,
                    "orden": a.orden
                }
                for a in regla.acciones
            ])
        
        cursor.execute("""
            EXEC sp_actualizar_regla_negocio
                @id_regla_param = ?,
                @nombre_param = ?,
                @descripcion_param = ?,
                @prioridad_param = ?,
                @estado_param = ?,
                @actualizada_por = ?,
                @json_condiciones = ?,
                @json_acciones = ?
        """, (
            rule_id,
            regla.nombre,
            regla.descripcion,
            regla.prioridad,
            regla.estado,
            actualizada_por,
            json_condiciones,
            json_acciones
        ))
        
        resultado = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if resultado[0] == 'EXITO':
            return {
                "resultado": "EXITO",
                "id_regla": resultado[1],
                "mensaje": "Regla actualizada exitosamente",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail=f"Error: {resultado[1]}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al actualizar regla: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 5: Eliminar Regla (Soft Delete)
# ============================================================================

@router.delete("/{rule_id}", summary="Eliminar (archivar) una regla")
async def eliminar_regla(
    rule_id: str,
    eliminada_por: str = Query(..., description="Usuario que elimina")
) -> Dict[str, Any]:
    """
    Eliminar (soft delete) una regla de negocio.
    
    **Nota:** Es un soft delete - la regla se marca como 'archivada', no se elimina.
    
    **Parámetros:**
    - `rule_id`: ID de la regla a eliminar
    - `eliminada_por`: Usuario que elimina
    
    **Respuesta:**
    ```json
    {
      "resultado": "EXITO",
      "id_regla": "descuento_vip_casab",
      "mensaje": "Regla archivada exitosamente"
    }
    ```
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            EXEC sp_eliminar_regla_negocio
                @id_regla_param = ?,
                @eliminada_por = ?
        """, (rule_id, eliminada_por))
        
        resultado = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if resultado[0] == 'EXITO':
            return {
                "resultado": "EXITO",
                "id_regla": resultado[1],
                "mensaje": "Regla archivada exitosamente",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Error: {resultado[1]}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al eliminar regla: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 6: Obtener Auditoría
# ============================================================================

@router.get("/audit", summary="Historial de evaluaciones")
async def obtener_auditoria(
    id_regla: Optional[str] = Query(None, description="ID de regla para filtrar"),
    id_empresa: Optional[int] = Query(None, description="ID de empresa para filtrar"),
    dias: int = Query(30, description="Últimos N días"),
    limite: int = Query(100, description="Máximo de registros")
) -> Dict[str, Any]:
    """
    Obtener historial de evaluaciones de reglas (auditoría).
    
    **Filtros disponibles:**
    - `id_regla`: Filtrar por regla específica
    - `id_empresa`: Filtrar por empresa específica
    - `dias`: Último N días (default: 30)
    - `limite`: Máximo de registros retornados (default: 100)
    
    **Información en auditoría:**
    - ID de la evaluación
    - Decisión tomada (permitida, bloqueada, etc)
    - Condiciones que se cumplieron
    - Valores calculados
    - Tiempo de ejecución
    - Quién evaluó
    
    **Ejemplo:**
    ```
    GET /api/v1/rules/audit?id_empresa=523&dias=30&limite=50
    ```
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            EXEC sp_obtener_auditoria
                @id_regla_param = ?,
                @id_empresa_param = ?,
                @dias_param = ?,
                @limite_param = ?
        """, (id_regla, id_empresa, dias, limite))
        
        auditorias = []
        for row in cursor.fetchall():
            auditorias.append({
                "id_auditoria": row[0],
                "id_regla": row[1],
                "nivel_alcance": row[2],
                "linea_negocio": row[3],
                "id_empresa": row[4],
                "condiciones_cumplidas": bool(row[5]),
                "decision": row[6],
                "valores_calculados": json.loads(row[7]) if row[7] else {},
                "fecha_evaluacion": row[8].isoformat() if row[8] else None,
                "evaluada_por": row[9],
                "tiempo_ejecucion_ms": row[10]
            })
        
        cursor.close()
        conn.close()
        
        return {
            "resultado": "EXITO",
            "total": len(auditorias),
            "auditorias": auditorias,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al obtener auditoría: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 7: Estado del Agente
# ============================================================================

@router.get("/status", summary="Estado operacional del agente")
async def status_agente() -> Dict[str, Any]:
    """
    Obtener estado operacional del BusinessRulesAgent.
    
    **Información:**
    - Total de reglas activas
    - Reglas por nivel (global, línea negocio, empresa)
    - Evaluaciones en últimas 24 horas
    - Performance promedio
    - Última evaluación
    
    **Respuesta:**
    ```json
    {
      "resultado": "EXITO",
      "agente": "BusinessRulesAgent",
      "estado": "operacional",
      "total_reglas_activas": 11,
      "reglas_por_nivel": {
        "global": 3,
        "linea_negocio": 4,
        "empresa": 4
      },
      "evaluaciones_24h": 45,
      "performance_promedio_ms": 6.8
    }
    ```
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Total reglas activas
        cursor.execute("SELECT COUNT(*) FROM reglas_negocio WHERE estado = 'activa'")
        total_activas = cursor.fetchone()[0]
        
        # Por nivel
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN nivel_alcance = 'global' THEN 1 ELSE 0 END) AS global,
                SUM(CASE WHEN nivel_alcance = 'linea_negocio' THEN 1 ELSE 0 END) AS linea_negocio,
                SUM(CASE WHEN nivel_alcance = 'empresa' THEN 1 ELSE 0 END) AS empresa
            FROM reglas_negocio WHERE estado = 'activa'
        """)
        row = cursor.fetchone()
        reglas_por_nivel = {
            "global": row[0] or 0,
            "linea_negocio": row[1] or 0,
            "empresa": row[2] or 0
        }
        
        # Evaluaciones en últimas 24h
        cursor.execute("""
            SELECT COUNT(*) FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= DATEADD(HOUR, -24, GETUTCDATE())
        """)
        evaluaciones_24h = cursor.fetchone()[0]
        
        # Performance promedio
        cursor.execute("""
            SELECT AVG(CAST(tiempo_ejecucion_ms AS FLOAT)) FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= DATEADD(HOUR, -24, GETUTCDATE())
        """)
        perf = cursor.fetchone()[0]
        performance_promedio_ms = float(perf) if perf else 0
        
        cursor.close()
        conn.close()
        
        return {
            "resultado": "EXITO",
            "agente": "BusinessRulesAgent",
            "estado": "operacional",
            "total_reglas_activas": total_activas,
            "reglas_por_nivel": reglas_por_nivel,
            "evaluaciones_24h": evaluaciones_24h,
            "performance_promedio_ms": round(performance_promedio_ms, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al obtener estado: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 8: Health Check
# ============================================================================

@router.get("/health", summary="Health check del agente")
async def health_check() -> Dict[str, Any]:
    """
    Health check del BusinessRulesAgent.
    
    Verifica que:
    - El agente está activo
    - La conexión a SQL Server está OK
    - Las tablas existen
    - Los SPs están disponibles
    
    **Respuesta:**
    ```json
    {
      "resultado": "OK",
      "agente": "BusinessRulesAgent",
      "sql_server": "conectado",
      "tablas": "presentes",
      "stored_procedures": "presentes",
      "uptime": "12h 34m"
    }
    ```
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Verificar tablas
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' 
            AND TABLE_NAME IN ('reglas_negocio', 'condiciones_regla', 'acciones_regla', 
                               'auditoria_evaluacion_reglas', 'cache_evaluacion_reglas', 'herencia_reglas')
        """)
        tablas_ok = cursor.fetchone()[0] == 6
        
        # Verificar SPs
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.ROUTINES
            WHERE ROUTINE_SCHEMA = 'dbo' AND ROUTINE_TYPE = 'PROCEDURE' 
            AND ROUTINE_NAME LIKE 'sp_%'
        """)
        sps_ok = cursor.fetchone()[0] == 6
        
        # Verificar vistas
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.VIEWS
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME LIKE 'vw_%'
        """)
        vistas_ok = cursor.fetchone()[0] == 3
        
        cursor.close()
        conn.close()
        
        status = "HEALTHY" if (tablas_ok and sps_ok and vistas_ok) else "DEGRADED"
        
        return {
            "resultado": "OK",
            "agente": "BusinessRulesAgent",
            "estado": status,
            "sql_server": "conectado",
            "tablas": "presentes" if tablas_ok else "faltantes",
            "stored_procedures": "presentes" if sps_ok else "faltantes",
            "vistas": "presentes" if vistas_ok else "faltantes",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check falló: {e}")
        return {
            "resultado": "ERROR",
            "agente": "BusinessRulesAgent",
            "estado": "NO_DISPONIBLE",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
