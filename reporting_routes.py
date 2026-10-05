"""
ReportingAgent - Router FastAPI
8 Endpoints para Reportes, Dashboards y KPIs del BusinessRulesEngine
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import pyodbc
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================================
# MODELOS PYDANTIC
# ============================================================================

class FiltroReporte(BaseModel):
    """Modelo para filtros de reporte"""
    fecha_inicio: Optional[str] = Field(None, description="YYYY-MM-DD")
    fecha_fin: Optional[str] = Field(None, description="YYYY-MM-DD")
    id_empresa: Optional[int] = None
    linea_negocio: Optional[str] = None
    id_regla: Optional[str] = None
    decision: Optional[str] = Field(None, description="permitida, bloqueada")


class FiltroKPI(BaseModel):
    """Modelo para filtros de KPI"""
    periodo: str = Field("30d", description="30d, 7d, 24h, custom")
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    id_empresa: Optional[int] = None


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
            'PWD=tu_contraseña'
        )
        conn = pyodbc.connect(connection_string)
        conn.autocommit = True
        return conn
    except pyodbc.Error as e:
        logger.error(f"Error de conexión SQL Server: {e}")
        raise HTTPException(status_code=500, detail=f"Error de conexión: {str(e)}")


# ============================================================================
# ENDPOINT 1: Reporte de Evaluaciones
# ============================================================================

@router.post("/evaluations", summary="Reporte de evaluaciones de reglas")
async def reporte_evaluaciones(
    filtros: FiltroReporte = None,
    agrupar_por: str = Query("regla", description="regla, empresa, decision, dia")
) -> Dict[str, Any]:
    """
    Generar reporte detallado de evaluaciones de reglas.
    
    **Filtros disponibles:**
    - fecha_inicio, fecha_fin (YYYY-MM-DD)
    - id_empresa, linea_negocio, id_regla
    - decision: permitida | bloqueada
    
    **Agrupar por:**
    - regla: Agrupar por ID de regla
    - empresa: Agrupar por empresa
    - decision: Permitida vs Bloqueada
    - dia: Tendencia diaria
    
    **Métricas en respuesta:**
    - Total evaluaciones
    - % aprobadas / bloqueadas
    - Reglas más usadas
    - Tendencia temporal
    
    **Ejemplo:**
    ```json
    {
      "fecha_inicio": "2026-09-15",
      "fecha_fin": "2026-09-22",
      "id_empresa": 523
    }
    ```
    """
    try:
        if not filtros:
            filtros = FiltroReporte()
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Construir query dinámico
        query = """
            SELECT 
                CASE 
                    WHEN ? = 'regla' THEN id_regla
                    WHEN ? = 'empresa' THEN CAST(id_empresa AS VARCHAR)
                    WHEN ? = 'decision' THEN decision
                    WHEN ? = 'dia' THEN CONVERT(VARCHAR(10), fecha_evaluacion, 23)
                END AS grupo,
                COUNT(*) AS total_evaluaciones,
                SUM(CASE WHEN decision = 'permitida' THEN 1 ELSE 0 END) AS permitidas,
                SUM(CASE WHEN decision = 'bloqueada' THEN 1 ELSE 0 END) AS bloqueadas,
                CAST(
                    SUM(CASE WHEN decision = 'permitida' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) 
                    AS DECIMAL(5,2)
                ) AS porcentaje_aprobadas,
                AVG(CAST(tiempo_ejecucion_ms AS FLOAT)) AS tiempo_promedio_ms
            FROM auditoria_evaluacion_reglas
            WHERE 1=1
        """
        
        params = [agrupar_por] * 4
        
        if filtros.fecha_inicio:
            query += " AND fecha_evaluacion >= ?"
            params.append(filtros.fecha_inicio)
        
        if filtros.fecha_fin:
            query += " AND fecha_evaluacion <= ?"
            params.append(filtros.fecha_fin)
        
        if filtros.id_empresa:
            query += " AND id_empresa = ?"
            params.append(filtros.id_empresa)
        
        if filtros.linea_negocio:
            query += " AND linea_negocio = ?"
            params.append(filtros.linea_negocio)
        
        if filtros.id_regla:
            query += " AND id_regla = ?"
            params.append(filtros.id_regla)
        
        if filtros.decision:
            query += " AND decision = ?"
            params.append(filtros.decision)
        
        query += f" GROUP BY "
        query += f"""
            CASE 
                WHEN ? = 'regla' THEN id_regla
                WHEN ? = 'empresa' THEN CAST(id_empresa AS VARCHAR)
                WHEN ? = 'decision' THEN decision
                WHEN ? = 'dia' THEN CONVERT(VARCHAR(10), fecha_evaluacion, 23)
            END
        """
        query += f" ORDER BY total_evaluaciones DESC"
        
        cursor.execute(query, params + [agrupar_por] * 4)
        
        filas = cursor.fetchall()
        
        # Procesar resultados
        datos = []
        total_general = 0
        permitidas_total = 0
        bloqueadas_total = 0
        
        for fila in filas:
            datos.append({
                "grupo": fila[0],
                "total_evaluaciones": fila[1],
                "permitidas": fila[2],
                "bloqueadas": fila[3],
                "porcentaje_aprobadas": float(fila[4]) if fila[4] else 0,
                "tiempo_promedio_ms": round(float(fila[5]), 2) if fila[5] else 0
            })
            total_general += fila[1]
            permitidas_total += fila[2]
            bloqueadas_total += fila[3]
        
        cursor.close()
        conn.close()
        
        return {
            "resultado": "EXITO",
            "reporte": "evaluaciones",
            "agrupado_por": agrupar_por,
            "periodo": {
                "inicio": filtros.fecha_inicio or "N/A",
                "fin": filtros.fecha_fin or "N/A"
            },
            "resumen": {
                "total_evaluaciones": total_general,
                "permitidas": permitidas_total,
                "bloqueadas": bloqueadas_total,
                "porcentaje_aprobadas": round(permitidas_total * 100 / total_general, 2) if total_general > 0 else 0
            },
            "datos": datos,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al generar reporte: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 2: KPIs del Motor de Reglas
# ============================================================================

@router.get("/kpis", summary="KPIs principales del BusinessRulesEngine")
async def kpis_motor(
    periodo: str = Query("30d", description="30d, 7d, 24h")
) -> Dict[str, Any]:
    """
    Obtener KPIs principales del motor de reglas.
    
    **KPIs incluidos:**
    - Tasa de aprobación
    - Reglas más usadas
    - Empresas más activas
    - Performance promedio
    - Tendencia de evaluaciones
    - Reglas con alto rechazo
    
    **Períodos:**
    - 24h: Últimas 24 horas
    - 7d: Últimos 7 días (default)
    - 30d: Últimos 30 días
    
    **Ejemplo:**
    ```
    GET /api/v1/reporting/kpis?periodo=7d
    ```
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Calcular fecha de inicio
        dias = {"24h": 1, "7d": 7, "30d": 30}.get(periodo, 30)
        fecha_inicio = (datetime.utcnow() - timedelta(days=dias)).isoformat()
        
        # KPI 1: Tasa de aprobación
        cursor.execute("""
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN decision = 'permitida' THEN 1 ELSE 0 END) AS permitidas,
                SUM(CASE WHEN decision = 'bloqueada' THEN 1 ELSE 0 END) AS bloqueadas
            FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= ?
        """, (fecha_inicio,))
        row = cursor.fetchone()
        total_eval = row[0] or 0
        permitidas = row[1] or 0
        bloqueadas = row[2] or 0
        tasa_aprobacion = (permitidas * 100 / total_eval) if total_eval > 0 else 0
        
        # KPI 2: Reglas más usadas
        cursor.execute("""
            SELECT TOP 5 id_regla, COUNT(*) AS uso
            FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= ?
            GROUP BY id_regla
            ORDER BY uso DESC
        """, (fecha_inicio,))
        reglas_top = [{"id_regla": row[0], "evaluaciones": row[1]} for row in cursor.fetchall()]
        
        # KPI 3: Empresas más activas
        cursor.execute("""
            SELECT TOP 5 id_empresa, COUNT(*) AS evaluaciones
            FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= ? AND id_empresa IS NOT NULL
            GROUP BY id_empresa
            ORDER BY evaluaciones DESC
        """, (fecha_inicio,))
        empresas_top = [{"id_empresa": row[0], "evaluaciones": row[1]} for row in cursor.fetchall()]
        
        # KPI 4: Performance promedio
        cursor.execute("""
            SELECT 
                AVG(CAST(tiempo_ejecucion_ms AS FLOAT)) AS promedio,
                MIN(tiempo_ejecucion_ms) AS minimo,
                MAX(tiempo_ejecucion_ms) AS maximo
            FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= ?
        """, (fecha_inicio,))
        row = cursor.fetchone()
        performance = {
            "promedio_ms": round(float(row[0]), 2) if row[0] else 0,
            "minimo_ms": row[1] or 0,
            "maximo_ms": row[2] or 0
        }
        
        # KPI 5: Reglas con alto rechazo
        cursor.execute("""
            SELECT TOP 5 id_regla, 
                COUNT(*) AS total,
                SUM(CASE WHEN decision = 'bloqueada' THEN 1 ELSE 0 END) AS bloqueadas
            FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= ?
            GROUP BY id_regla
            HAVING SUM(CASE WHEN decision = 'bloqueada' THEN 1 ELSE 0 END) > 0
            ORDER BY bloqueadas DESC
        """, (fecha_inicio,))
        reglas_rechazo = [
            {
                "id_regla": row[0],
                "total": row[1],
                "bloqueadas": row[2],
                "tasa_rechazo": round(row[2] * 100 / row[1], 2)
            }
            for row in cursor.fetchall()
        ]
        
        cursor.close()
        conn.close()
        
        return {
            "resultado": "EXITO",
            "periodo": periodo,
            "dias": dias,
            "kpis": {
                "evaluaciones": {
                    "total": total_eval,
                    "permitidas": permitidas,
                    "bloqueadas": bloqueadas,
                    "tasa_aprobacion": round(tasa_aprobacion, 2)
                },
                "performance": performance,
                "reglas_top_5": reglas_top,
                "empresas_top_5": empresas_top,
                "reglas_alto_rechazo": reglas_rechazo
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al generar KPIs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 3: Reporte de Auditoría
# ============================================================================

@router.get("/audit-report", summary="Reporte detallado de auditoría")
async def reporte_auditoria(
    filtro: FiltroReporte = None,
    limite: int = Query(100, description="Máximo de registros"),
    ordenar_por: str = Query("fecha", description="fecha, decision, empresa")
) -> Dict[str, Any]:
    """
    Reporte detallado con historial completo de auditoría.
    
    **Información incluida:**
    - ID de auditoria, regla, empresa
    - Decisión tomada
    - Condiciones cumplidas
    - Valores calculados
    - Tiempo de ejecución
    - Quién evaluó
    - Timestamp exacto
    """
    try:
        if not filtro:
            filtro = FiltroReporte()
        
        conn = get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT TOP ? 
                id_auditoria, id_regla, nivel_alcance, linea_negocio, id_empresa,
                condiciones_cumplidas, decision, valores_calculados,
                fecha_evaluacion, evaluada_por, tiempo_ejecucion_ms
            FROM auditoria_evaluacion_reglas
            WHERE 1=1
        """
        
        params = [limite]
        
        if filtro.fecha_inicio:
            query += " AND fecha_evaluacion >= ?"
            params.append(filtro.fecha_inicio)
        
        if filtro.fecha_fin:
            query += " AND fecha_evaluacion <= ?"
            params.append(filtro.fecha_fin)
        
        if filtro.id_empresa:
            query += " AND id_empresa = ?"
            params.append(filtro.id_empresa)
        
        if filtro.id_regla:
            query += " AND id_regla = ?"
            params.append(filtro.id_regla)
        
        if filtro.decision:
            query += " AND decision = ?"
            params.append(filtro.decision)
        
        # Ordenar
        order_map = {
            "fecha": "fecha_evaluacion DESC",
            "decision": "decision ASC",
            "empresa": "id_empresa ASC"
        }
        query += f" ORDER BY {order_map.get(ordenar_por, 'fecha_evaluacion DESC')}"
        
        cursor.execute(query, params)
        
        registros = []
        for row in cursor.fetchall():
            registros.append({
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
            "total": len(registros),
            "registros": registros,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al generar reporte de auditoría: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 4: Dashboard de Reglas
# ============================================================================

@router.get("/dashboard/rules", summary="Dashboard de estado de reglas")
async def dashboard_reglas() -> Dict[str, Any]:
    """
    Dashboard ejecutivo con estado de todas las reglas.
    
    **Información:**
    - Total de reglas por nivel
    - Reglas activas vs inactivas
    - Última evaluación por regla
    - Estado de salud
    - Cambios recientes
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Total por nivel
        cursor.execute("""
            SELECT 
                nivel_alcance,
                COUNT(*) AS total,
                SUM(CASE WHEN estado = 'activa' THEN 1 ELSE 0 END) AS activas,
                SUM(CASE WHEN estado = 'inactiva' THEN 1 ELSE 0 END) AS inactivas
            FROM reglas_negocio
            GROUP BY nivel_alcance
        """)
        
        reglas_por_nivel = {}
        for row in cursor.fetchall():
            reglas_por_nivel[row[0]] = {
                "total": row[1],
                "activas": row[2],
                "inactivas": row[3]
            }
        
        # Última evaluación por regla
        cursor.execute("""
            SELECT TOP 10
                r.id_regla,
                r.nombre,
                MAX(a.fecha_evaluacion) AS ultima_evaluacion,
                COUNT(a.id_auditoria) AS total_evaluaciones_24h
            FROM reglas_negocio r
            LEFT JOIN auditoria_evaluacion_reglas a 
                ON r.id_regla = a.id_regla 
                AND a.fecha_evaluacion >= DATEADD(HOUR, -24, GETUTCDATE())
            WHERE r.estado = 'activa'
            GROUP BY r.id_regla, r.nombre
            ORDER BY MAX(a.fecha_evaluacion) DESC
        """)
        
        reglas_activas = [
            {
                "id_regla": row[0],
                "nombre": row[1],
                "ultima_evaluacion": row[2].isoformat() if row[2] else None,
                "evaluaciones_24h": row[3] or 0
            }
            for row in cursor.fetchall()
        ]
        
        # Cambios recientes
        cursor.execute("""
            SELECT TOP 5
                id_regla,
                nombre,
                estado,
                fecha_modificacion
            FROM reglas_negocio
            ORDER BY fecha_modificacion DESC
        """)
        
        cambios_recientes = [
            {
                "id_regla": row[0],
                "nombre": row[1],
                "estado": row[2],
                "fecha": row[3].isoformat() if row[3] else None
            }
            for row in cursor.fetchall()
        ]
        
        cursor.close()
        conn.close()
        
        return {
            "resultado": "EXITO",
            "resumen": {
                "reglas_por_nivel": reglas_por_nivel,
                "total_general": sum(v["total"] for v in reglas_por_nivel.values()),
                "total_activas": sum(v["activas"] for v in reglas_por_nivel.values())
            },
            "reglas_activas_top_10": reglas_activas,
            "cambios_recientes": cambios_recientes,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al generar dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 5: Análisis de Tendencias
# ============================================================================

@router.get("/trends", summary="Análisis de tendencias")
async def analisis_tendencias(
    dias: int = Query(30, description="Últimos N días"),
    granularidad: str = Query("dia", description="hora, dia, semana")
) -> Dict[str, Any]:
    """
    Análisis de tendencias de evaluaciones a lo largo del tiempo.
    
    **Granularidades:**
    - hora: Por hora
    - dia: Por día (default)
    - semana: Por semana
    
    **Métricas:**
    - Evaluaciones por período
    - Tasa de aprobación
    - Performance promedio
    - Crecimiento
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Determinar formato de fecha según granularidad
        if granularidad == "hora":
            formato = "CONVERT(VARCHAR(13), fecha_evaluacion, 120)"
        elif granularidad == "semana":
            formato = "CONVERT(VARCHAR(10), DATEADD(WEEK, -DATEDIFF(WEEK, 0, fecha_evaluacion), fecha_evaluacion), 23)"
        else:  # dia
            formato = "CONVERT(VARCHAR(10), fecha_evaluacion, 23)"
        
        query = f"""
            SELECT 
                {formato} AS periodo,
                COUNT(*) AS evaluaciones,
                SUM(CASE WHEN decision = 'permitida' THEN 1 ELSE 0 END) AS permitidas,
                SUM(CASE WHEN decision = 'bloqueada' THEN 1 ELSE 0 END) AS bloqueadas,
                AVG(CAST(tiempo_ejecucion_ms AS FLOAT)) AS performance_promedio
            FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= DATEADD(DAY, ?, GETUTCDATE())
            GROUP BY {formato}
            ORDER BY periodo ASC
        """
        
        cursor.execute(query, (-dias,))
        
        datos = []
        for row in cursor.fetchall():
            total = row[1]
            datos.append({
                "periodo": row[0],
                "evaluaciones": total,
                "permitidas": row[2],
                "bloqueadas": row[3],
                "tasa_aprobacion": round(row[2] * 100 / total, 2) if total > 0 else 0,
                "performance_promedio_ms": round(float(row[4]), 2) if row[4] else 0
            })
        
        cursor.close()
        conn.close()
        
        # Calcular crecimiento
        crecimiento = 0
        if len(datos) > 1:
            primer_periodo = datos[0]["evaluaciones"]
            ultimo_periodo = datos[-1]["evaluaciones"]
            if primer_periodo > 0:
                crecimiento = round((ultimo_periodo - primer_periodo) / primer_periodo * 100, 2)
        
        return {
            "resultado": "EXITO",
            "periodo_dias": dias,
            "granularidad": granularidad,
            "crecimiento_total": crecimiento,
            "datos": datos,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al generar tendencias: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 6: Análisis de Decisiones
# ============================================================================

@router.get("/decisions-analysis", summary="Análisis profundo de decisiones")
async def analisis_decisiones(
    id_regla: Optional[str] = Query(None, description="Filtrar por regla específica"),
    id_empresa: Optional[int] = Query(None, description="Filtrar por empresa específica")
) -> Dict[str, Any]:
    """
    Análisis detallado de decisiones tomadas por las reglas.
    
    **Análisis incluido:**
    - Distribución de decisiones
    - Decisiones por regla
    - Reglas que generan conflictos
    - Patrones de rechazo
    - Comparativa entre empresas
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Decisiones por regla
        query = """
            SELECT 
                id_regla,
                decision,
                COUNT(*) AS cantidad,
                AVG(CAST(tiempo_ejecucion_ms AS FLOAT)) AS tiempo_promedio
            FROM auditoria_evaluacion_reglas
            WHERE 1=1
        """
        
        params = []
        
        if id_regla:
            query += " AND id_regla = ?"
            params.append(id_regla)
        
        if id_empresa:
            query += " AND id_empresa = ?"
            params.append(id_empresa)
        
        query += " GROUP BY id_regla, decision ORDER BY id_regla, decision"
        
        cursor.execute(query, params)
        
        analisis = {}
        for row in cursor.fetchall():
            regla = row[0]
            if regla not in analisis:
                analisis[regla] = {
                    "total": 0,
                    "decisiones": {}
                }
            
            decision = row[1]
            cantidad = row[2]
            analisis[regla]["total"] += cantidad
            analisis[regla]["decisiones"][decision] = {
                "cantidad": cantidad,
                "tiempo_promedio_ms": round(float(row[3]), 2) if row[3] else 0
            }
        
        # Procesar para agregar porcentajes
        resultado_analisis = []
        for regla, datos in analisis.items():
            total = datos["total"]
            decisiones_con_pct = {}
            for decision, info in datos["decisiones"].items():
                decisiones_con_pct[decision] = {
                    **info,
                    "porcentaje": round(info["cantidad"] * 100 / total, 2)
                }
            
            resultado_analisis.append({
                "id_regla": regla,
                "total_evaluaciones": total,
                "decisiones": decisiones_con_pct
            })
        
        cursor.close()
        conn.close()
        
        return {
            "resultado": "EXITO",
            "filtros": {
                "id_regla": id_regla,
                "id_empresa": id_empresa
            },
            "analisis": sorted(resultado_analisis, key=lambda x: x["total_evaluaciones"], reverse=True),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al analizar decisiones: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 7: Exportar Reporte (CSV/JSON)
# ============================================================================

@router.post("/export", summary="Exportar reporte a CSV o JSON")
async def exportar_reporte(
    tipo_reporte: str = Query("evaluaciones", description="evaluaciones, auditoria, kpis"),
    formato: str = Query("json", description="json, csv"),
    filtro: FiltroReporte = None
) -> Dict[str, Any]:
    """
    Exportar reporte en formato JSON o CSV.
    
    **Tipos de reporte:**
    - evaluaciones: Reporte de evaluaciones
    - auditoria: Historial de auditoría
    - kpis: Principales KPIs
    
    **Formatos:**
    - json: Formato JSON
    - csv: Formato CSV (texto)
    
    **Nota:** Para descargar, incluir en URL:
    ```
    ?download=true
    ```
    """
    try:
        if not filtro:
            filtro = FiltroReporte()
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Obtener datos según tipo de reporte
        if tipo_reporte == "evaluaciones":
            query = """
                SELECT 
                    fecha_evaluacion, id_regla, id_empresa, 
                    decision, tiempo_ejecucion_ms
                FROM auditoria_evaluacion_reglas
                WHERE 1=1
            """
        elif tipo_reporte == "auditoria":
            query = """
                SELECT 
                    id_auditoria, fecha_evaluacion, id_regla, 
                    id_empresa, decision, evaluada_por
                FROM auditoria_evaluacion_reglas
                WHERE 1=1
            """
        else:  # kpis
            query = """
                SELECT 
                    CONVERT(VARCHAR(10), fecha_evaluacion, 23) AS fecha,
                    COUNT(*) AS evaluaciones,
                    SUM(CASE WHEN decision = 'permitida' THEN 1 ELSE 0 END) AS permitidas
                FROM auditoria_evaluacion_reglas
                WHERE 1=1
                GROUP BY CONVERT(VARCHAR(10), fecha_evaluacion, 23)
            """
        
        params = []
        
        if filtro.fecha_inicio:
            query += " AND fecha_evaluacion >= ?"
            params.append(filtro.fecha_inicio)
        
        if filtro.fecha_fin:
            query += " AND fecha_evaluacion <= ?"
            params.append(filtro.fecha_fin)
        
        cursor.execute(query, params)
        
        # Convertir a formato solicitado
        if formato == "csv":
            # Obtener nombres de columnas
            columnas = [desc[0] for desc in cursor.description]
            
            # Crear CSV
            lineas = [",".join(columnas)]
            for row in cursor.fetchall():
                lineas.append(",".join(str(v) for v in row))
            
            contenido = "\n".join(lineas)
            tipo_contenido = "text/csv"
        else:  # json
            datos = []
            columnas = [desc[0] for desc in cursor.description]
            for row in cursor.fetchall():
                datos.append(dict(zip(columnas, row)))
            
            contenido = json.dumps(datos, default=str, indent=2)
            tipo_contenido = "application/json"
        
        cursor.close()
        conn.close()
        
        return {
            "resultado": "EXITO",
            "tipo_reporte": tipo_reporte,
            "formato": formato,
            "contenido": contenido,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error al exportar reporte: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINT 8: Health Check Reporting
# ============================================================================

@router.get("/health", summary="Health check del Reporting Agent")
async def health_check() -> Dict[str, Any]:
    """
    Verificar que ReportingAgent está operacional.
    
    Verifica:
    - Conexión a SQL Server
    - Tablas de auditoría presentes
    - Datos recientes disponibles
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Verificar tabla de auditoría
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'auditoria_evaluacion_reglas'
        """)
        tabla_existe = cursor.fetchone()[0] == 1
        
        # Verificar datos recientes (últimas 24h)
        cursor.execute("""
            SELECT COUNT(*) FROM auditoria_evaluacion_reglas
            WHERE fecha_evaluacion >= DATEADD(HOUR, -24, GETUTCDATE())
        """)
        datos_recientes = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        estado = "HEALTHY" if tabla_existe and datos_recientes > 0 else "DEGRADED"
        
        return {
            "resultado": "OK",
            "agente": "ReportingAgent",
            "estado": estado,
            "sql_server": "conectado",
            "tabla_auditoria": "presente" if tabla_existe else "ausente",
            "datos_24h": datos_recientes,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check falló: {e}")
        return {
            "resultado": "ERROR",
            "agente": "ReportingAgent",
            "estado": "NO_DISPONIBLE",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
