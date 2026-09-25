"""
PostgreSQL Integration - Kinetix Studio
Capa de persistencia centralizada en PostgreSQL (Advance)
Síncrono con SQL Server para reglas de negocio
"""

import os

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "advance_db"),
    "user": os.getenv("POSTGRES_USER", "advance_user"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# ============================================================================
# CONEXIÓN A POSTGRESQL
# ============================================================================

class PostgresConnection:
    """Gestor de conexión a PostgreSQL"""
    
    @staticmethod
    def get_connection():
        """Obtener conexión a PostgreSQL"""
        try:
            conn = psycopg2.connect(
                host=POSTGRES_CONFIG["host"],
                port=POSTGRES_CONFIG["port"],
                database=POSTGRES_CONFIG["database"],
                user=POSTGRES_CONFIG["user"],
                password=POSTGRES_CONFIG["password"]
            )
            return conn
        except psycopg2.Error as e:
            logger.error(f"Error de conexión PostgreSQL: {e}")
            raise Exception(f"No se pudo conectar a PostgreSQL: {str(e)}")
    
    @staticmethod
    def test_connection():
        """Probar conexión a PostgreSQL"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Test de conexión falló: {e}")
            return False


# ============================================================================
# TABLAS EN POSTGRESQL
# ============================================================================

class PostgresSchemas:
    """SQL para crear esquema en PostgreSQL"""
    
    # Tabla para registros de evaluaciones (copia de SQL Server)
    TABLA_EVALUACIONES_SYNC = """
    CREATE TABLE IF NOT EXISTS kinetix_evaluaciones_sync (
        id_sync SERIAL PRIMARY KEY,
        id_auditoria INT NOT NULL UNIQUE,
        id_regla VARCHAR(100) NOT NULL,
        nivel_alcance VARCHAR(20),
        linea_negocio VARCHAR(50),
        id_empresa INT,
        decision VARCHAR(20) NOT NULL,
        condiciones_cumplidas BOOLEAN,
        valores_calculados JSONB,
        fecha_evaluacion TIMESTAMP,
        evaluada_por VARCHAR(100),
        tiempo_ejecucion_ms DECIMAL(10,2),
        fecha_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(id_auditoria)
    );
    
    CREATE INDEX IF NOT EXISTS idx_id_regla_sync ON kinetix_evaluaciones_sync(id_regla);
    CREATE INDEX IF NOT EXISTS idx_id_empresa_sync ON kinetix_evaluaciones_sync(id_empresa);
    CREATE INDEX IF NOT EXISTS idx_fecha_sync ON kinetix_evaluaciones_sync(fecha_evaluacion);
    """
    
    # Tabla para cache de decisiones
    TABLA_CACHE_DECISIONES = """
    CREATE TABLE IF NOT EXISTS kinetix_cache_decisiones (
        id_cache SERIAL PRIMARY KEY,
        hash_contexto VARCHAR(64) UNIQUE NOT NULL,
        id_regla VARCHAR(100) NOT NULL,
        id_empresa INT,
        decision VARCHAR(20),
        valores_calculados JSONB,
        ttl_seconds INT DEFAULT 3600,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_expiracion TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_hash_contexto ON kinetix_cache_decisiones(hash_contexto);
    CREATE INDEX IF NOT EXISTS idx_expiracion ON kinetix_cache_decisiones(fecha_expiracion);
    """
    
    # Tabla para auditoria centralizada
    TABLA_AUDITORIA_CENTRALIZADA = """
    CREATE TABLE IF NOT EXISTS kinetix_auditoria_centralizada (
        id_auditoria_central SERIAL PRIMARY KEY,
        id_regla VARCHAR(100) NOT NULL,
        id_empresa INT,
        accion VARCHAR(50) NOT NULL,
        usuario VARCHAR(100),
        datos_antes JSONB,
        datos_despues JSONB,
        descripcion TEXT,
        fecha_accion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_id_regla_aud ON kinetix_auditoria_centralizada(id_regla);
    CREATE INDEX IF NOT EXISTS idx_fecha_accion ON kinetix_auditoria_centralizada(fecha_accion);
    """
    
    # Tabla para cache distribuido
    TABLA_CACHE_DISTRIBUIDO = """
    CREATE TABLE IF NOT EXISTS kinetix_cache_distribuido (
        id_cache SERIAL PRIMARY KEY,
        clave VARCHAR(255) UNIQUE NOT NULL,
        valor JSONB NOT NULL,
        ttl INT DEFAULT 3600,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_acceso_ultimo TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_clave_cache ON kinetix_cache_distribuido(clave);
    """
    
    # Tabla de metricas
    TABLA_METRICAS = """
    CREATE TABLE IF NOT EXISTS kinetix_metricas (
        id_metrica SERIAL PRIMARY KEY,
        id_regla VARCHAR(100),
        id_empresa INT,
        metrica_nombre VARCHAR(100),
        metrica_valor DECIMAL(20,4),
        fecha_metrica TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_id_regla_met ON kinetix_metricas(id_regla);
    CREATE INDEX IF NOT EXISTS idx_fecha_metrica ON kinetix_metricas(fecha_metrica);
    """


# ============================================================================
# GESTOR DE EVALUACIONES
# ============================================================================

class EvaluacionesPostgres:
    """Operaciones de evaluaciones en PostgreSQL"""
    
    @staticmethod
    def crear_tablas():
        """Crear todas las tablas necesarias"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor()
            
            # Ejecutar scripts de creación
            schemas = [
                PostgresSchemas.TABLA_EVALUACIONES_SYNC,
                PostgresSchemas.TABLA_CACHE_DECISIONES,
                PostgresSchemas.TABLA_AUDITORIA_CENTRALIZADA,
                PostgresSchemas.TABLA_CACHE_DISTRIBUIDO,
                PostgresSchemas.TABLA_METRICAS
            ]
            
            for schema in schemas:
                cursor.execute(schema)
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info("✅ Tablas creadas exitosamente en PostgreSQL")
            return True
        except Exception as e:
            logger.error(f"Error al crear tablas: {e}")
            return False
    
    @staticmethod
    def sincronizar_evaluacion(
        id_auditoria: int,
        id_regla: str,
        id_empresa: int,
        decision: str,
        valores_calculados: Dict,
        metadata: Dict = None
    ) -> bool:
        """
        Sincronizar evaluación desde SQL Server a PostgreSQL
        """
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO kinetix_evaluaciones_sync (
                    id_auditoria, id_regla, id_empresa, decision, 
                    valores_calculados, evaluada_por
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id_auditoria) DO UPDATE SET
                    decision = EXCLUDED.decision,
                    valores_calculados = EXCLUDED.valores_calculados,
                    fecha_sync = CURRENT_TIMESTAMP
            """, (
                id_auditoria,
                id_regla,
                id_empresa,
                decision,
                json.dumps(valores_calculados),
                metadata.get("evaluada_por", "sistema") if metadata else "sistema"
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        except Exception as e:
            logger.error(f"Error al sincronizar evaluación: {e}")
            return False
    
    @staticmethod
    def obtener_evaluaciones_recientes(
        dias: int = 30,
        id_empresa: Optional[int] = None,
        id_regla: Optional[str] = None,
        limite: int = 1000
    ) -> List[Dict]:
        """
        Obtener evaluaciones recientes de PostgreSQL
        """
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT * FROM kinetix_evaluaciones_sync
                WHERE fecha_evaluacion >= CURRENT_DATE - INTERVAL '%s days'
            """
            params = [dias]
            
            if id_empresa:
                query += " AND id_empresa = %s"
                params.append(id_empresa)
            
            if id_regla:
                query += " AND id_regla = %s"
                params.append(id_regla)
            
            query += " ORDER BY fecha_evaluacion DESC LIMIT %s"
            params.append(limite)
            
            cursor.execute(query, tuple(params))
            resultados = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in resultados]
        except Exception as e:
            logger.error(f"Error al obtener evaluaciones: {e}")
            return []


# ============================================================================
# GESTOR DE CACHE DISTRIBUIDO
# ============================================================================

class CacheDistribuido:
    """Cache distribuido en PostgreSQL"""
    
    @staticmethod
    def set(clave: str, valor: Dict, ttl: int = 3600) -> bool:
        """Guardar en cache"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor()
            
            fecha_expiracion = "CURRENT_TIMESTAMP + INTERVAL '%s seconds'" % ttl
            
            cursor.execute("""
                INSERT INTO kinetix_cache_distribuido (clave, valor, ttl, fecha_acceso_ultimo)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (clave) DO UPDATE SET
                    valor = EXCLUDED.valor,
                    ttl = EXCLUDED.ttl,
                    fecha_acceso_ultimo = CURRENT_TIMESTAMP
            """, (clave, json.dumps(valor), ttl))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        except Exception as e:
            logger.error(f"Error al guardar en cache: {e}")
            return False
    
    @staticmethod
    def get(clave: str) -> Optional[Dict]:
        """Obtener del cache"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT valor FROM kinetix_cache_distribuido
                WHERE clave = %s 
                AND (fecha_acceso_ultimo + INTERVAL '1 second' * ttl > CURRENT_TIMESTAMP)
            """, (clave,))
            
            resultado = cursor.fetchone()
            
            if resultado:
                # Actualizar último acceso
                cursor.execute("""
                    UPDATE kinetix_cache_distribuido
                    SET fecha_acceso_ultimo = CURRENT_TIMESTAMP
                    WHERE clave = %s
                """, (clave,))
                conn.commit()
            
            cursor.close()
            conn.close()
            
            return json.loads(resultado["valor"]) if resultado else None
        except Exception as e:
            logger.error(f"Error al obtener del cache: {e}")
            return None
    
    @staticmethod
    def limpiar_expirados() -> int:
        """Limpiar cache expirado"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM kinetix_cache_distribuido
                WHERE fecha_acceso_ultimo + INTERVAL '1 second' * ttl < CURRENT_TIMESTAMP
            """)
            
            filas_eliminadas = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()
            
            return filas_eliminadas
        except Exception as e:
            logger.error(f"Error al limpiar cache: {e}")
            return 0


# ============================================================================
# GESTOR DE AUDITORIA CENTRALIZADA
# ============================================================================

class AuditoriaCentralizada:
    """Auditoría centralizada en PostgreSQL"""
    
    @staticmethod
    def registrar_accion(
        id_regla: str,
        accion: str,
        usuario: str,
        datos_antes: Dict = None,
        datos_despues: Dict = None,
        descripcion: str = None,
        id_empresa: int = None
    ) -> bool:
        """Registrar acción en auditoría centralizada"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO kinetix_auditoria_centralizada (
                    id_regla, accion, usuario, datos_antes, datos_despues, 
                    descripcion, id_empresa
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                id_regla,
                accion,
                usuario,
                json.dumps(datos_antes) if datos_antes else None,
                json.dumps(datos_despues) if datos_despues else None,
                descripcion,
                id_empresa
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        except Exception as e:
            logger.error(f"Error al registrar auditoría: {e}")
            return False
    
    @staticmethod
    def obtener_auditoria(
        id_regla: str = None,
        dias: int = 30,
        limite: int = 100
    ) -> List[Dict]:
        """Obtener registros de auditoría"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT * FROM kinetix_auditoria_centralizada
                WHERE fecha_accion >= CURRENT_DATE - INTERVAL '%s days'
            """
            params = [dias]
            
            if id_regla:
                query += " AND id_regla = %s"
                params.append(id_regla)
            
            query += " ORDER BY fecha_accion DESC LIMIT %s"
            params.append(limite)
            
            cursor.execute(query, tuple(params))
            resultados = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in resultados]
        except Exception as e:
            logger.error(f"Error al obtener auditoría: {e}")
            return []


# ============================================================================
# GESTOR DE METRICAS
# ============================================================================

class MetricasPostgres:
    """Almacenar y recuperar métricas en PostgreSQL"""
    
    @staticmethod
    def registrar_metrica(
        id_regla: str,
        metrica_nombre: str,
        metrica_valor: float,
        id_empresa: int = None
    ) -> bool:
        """Registrar métrica"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO kinetix_metricas (
                    id_regla, metrica_nombre, metrica_valor, id_empresa
                ) VALUES (%s, %s, %s, %s)
            """, (id_regla, metrica_nombre, metrica_valor, id_empresa))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        except Exception as e:
            logger.error(f"Error al registrar métrica: {e}")
            return False
    
    @staticmethod
    def obtener_metricas(
        id_regla: str = None,
        metrica_nombre: str = None,
        dias: int = 30
    ) -> List[Dict]:
        """Obtener métricas"""
        try:
            conn = PostgresConnection.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT * FROM kinetix_metricas
                WHERE fecha_metrica >= CURRENT_DATE - INTERVAL '%s days'
            """
            params = [dias]
            
            if id_regla:
                query += " AND id_regla = %s"
                params.append(id_regla)
            
            if metrica_nombre:
                query += " AND metrica_nombre = %s"
                params.append(metrica_nombre)
            
            query += " ORDER BY fecha_metrica DESC"
            
            cursor.execute(query, tuple(params))
            resultados = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return [dict(row) for row in resultados]
        except Exception as e:
            logger.error(f"Error al obtener métricas: {e}")
            return []


# ============================================================================
# INICIALIZACIÓN
# ============================================================================

def inicializar_postgres():
    """
    Inicializar PostgreSQL para Kinetix Studio
    Crear tablas y verificar conectividad
    """
    logger.info("🚀 Inicializando PostgreSQL...")
    
    # Verificar conexión
    if not PostgresConnection.test_connection():
        logger.error("❌ No se pudo conectar a PostgreSQL")
        return False
    
    logger.info("✅ Conexión a PostgreSQL OK")
    
    # Crear tablas
    if not EvaluacionesPostgres.crear_tablas():
        logger.error("❌ Error al crear tablas")
        return False
    
    logger.info("✅ Tablas creadas/verificadas")
    
    # Limpiar cache expirado
    filas = CacheDistribuido.limpiar_expirados()
    logger.info(f"✅ Cache limpiado ({filas} registros expirados)")
    
    logger.info("✅ PostgreSQL inicializado exitosamente")
    return True


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def sincronizar_evaluacion_completa(
    id_auditoria: int,
    evaluacion_data: Dict
) -> bool:
    """
    Sincronizar evaluación completa:
    1. Guardar en cache distribuido
    2. Sincronizar a PostgreSQL
    3. Registrar en auditoría centralizada
    """
    try:
        # Crear hash del contexto para cache
        contexto = evaluacion_data.get("contexto", {})
        hash_contexto = str(hash(json.dumps(contexto, sort_keys=True, default=str)))[:64]
        
        # 1. Guardar en cache
        CacheDistribuido.set(
            clave=f"eval_{hash_contexto}",
            valor=evaluacion_data,
            ttl=3600
        )
        
        # 2. Sincronizar a PostgreSQL
        EvaluacionesPostgres.sincronizar_evaluacion(
            id_auditoria=id_auditoria,
            id_regla=evaluacion_data.get("id_regla"),
            id_empresa=evaluacion_data.get("id_empresa"),
            decision=evaluacion_data.get("decision"),
            valores_calculados=evaluacion_data.get("valores_calculados", {}),
            metadata={"evaluada_por": evaluacion_data.get("evaluada_por")}
        )
        
        # 3. Registrar en auditoría
        AuditoriaCentralizada.registrar_accion(
            id_regla=evaluacion_data.get("id_regla"),
            accion="evaluacion",
            usuario=evaluacion_data.get("evaluada_por", "sistema"),
            datos_despues=evaluacion_data,
            descripcion=f"Evaluación de {evaluacion_data.get('id_regla')}",
            id_empresa=evaluacion_data.get("id_empresa")
        )
        
        # 4. Registrar métricas
        MetricasPostgres.registrar_metrica(
            id_regla=evaluacion_data.get("id_regla"),
            metrica_nombre="evaluaciones_totales",
            metrica_valor=1,
            id_empresa=evaluacion_data.get("id_empresa")
        )
        
        return True
    except Exception as e:
        logger.error(f"Error al sincronizar evaluación: {e}")
        return False
