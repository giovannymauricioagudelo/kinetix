# ============================================================================
# SENTINEL v1.0 - SQL Server Database Module
# Fecha: Oct 1-6, 2026 (Week 1 Integration)
# ============================================================================

import os
import pyodbc
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import logging

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# SQL Server Connection String
SERVER = 'localhost'
DATABASE = 'kinetix'
USERNAME = 'sa'
PASSWORD = os.getenv('SQLSERVER_PASSWORD', '')
DRIVER = 'ODBC Driver 18 for SQL Server'

# Connection string con TrustServerCertificate
CONNECTION_STRING = f"""
Driver={DRIVER};
Server={SERVER};
Database={DATABASE};
UID={USERNAME};
PWD={PASSWORD};
TrustServerCertificate=yes;
"""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

class DatabaseConnection:
    """Gestor de conexiones a SQL Server"""
    
    @staticmethod
    def conectar():
        """Crear conexión a SQL Server"""
        try:
            conn = pyodbc.connect(CONNECTION_STRING)
            logger.info("✅ Conexión a SQL Server exitosa")
            return conn
        except pyodbc.Error as e:
            logger.error(f"❌ Error conectando a SQL Server: {e}")
            raise

    @staticmethod
    def ejecutar_query(query: str, params: tuple = ()) -> List[Tuple]:
        """Ejecutar SELECT query"""
        conn = DatabaseConnection.conectar()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            resultados = cursor.fetchall()
            return resultados
        finally:
            conn.close()

    @staticmethod
    def ejecutar_comando(query: str, params: tuple = ()) -> int:
        """Ejecutar INSERT/UPDATE/DELETE y retornar filas afectadas"""
        conn = DatabaseConnection.conectar()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

# ============================================================================
# USUARIO FUNCTIONS
# ============================================================================

class UsuariosDB:
    """Funciones para gestionar usuarios en BD"""
    
    @staticmethod
    def obtener_usuario(nombre_usuario: str, id_empresa: str) -> Optional[Dict]:
        """Obtener usuario desde BD"""
        query = """
        SELECT id, nombre_usuario, correo, hash_contrasena, id_empresa, estado, mfa_habilitado
        FROM dbo.usuarios
        WHERE nombre_usuario = ? AND id_empresa = ?
        """
        resultados = DatabaseConnection.ejecutar_query(query, (nombre_usuario, id_empresa))
        
        if resultados:
            fila = resultados[0]
            return {
                "id": fila[0],
                "nombre_usuario": fila[1],
                "correo": fila[2],
                "hash_contrasena": fila[3],
                "id_empresa": fila[4],
                "estado": fila[5],
                "mfa_habilitado": fila[6]
            }
        return None

    @staticmethod
    def obtener_usuario_por_id(id_usuario: str) -> Optional[Dict]:
        """Obtener usuario por ID"""
        query = """
        SELECT id, nombre_usuario, correo, id_empresa, estado
        FROM dbo.usuarios
        WHERE id = ?
        """
        resultados = DatabaseConnection.ejecutar_query(query, (id_usuario,))
        
        if resultados:
            fila = resultados[0]
            return {
                "id": fila[0],
                "nombre_usuario": fila[1],
                "correo": fila[2],
                "id_empresa": fila[3],
                "estado": fila[4]
            }
        return None

    @staticmethod
    def crear_usuario(id_usuario: str, nombre_usuario: str, correo: str, 
                     contrasena: str, id_empresa: str) -> bool:
        """Crear nuevo usuario"""
        # Hashear contraseña con bcrypt
        hash_pwd = bcrypt.hashpw(contrasena.encode(), bcrypt.gensalt(rounds=12)).decode()
        
        query = """
        INSERT INTO dbo.usuarios 
        (id, nombre_usuario, correo, hash_contrasena, id_empresa, estado)
        VALUES (?, ?, ?, ?, ?, 'activo')
        """
        filas = DatabaseConnection.ejecutar_comando(query, 
            (id_usuario, nombre_usuario, correo, hash_pwd, id_empresa))
        return filas > 0

    @staticmethod
    def actualizar_ultimo_acceso(id_usuario: str):
        """Actualizar timestamp último acceso"""
        query = "UPDATE dbo.usuarios SET ultimo_acceso = GETUTCDATE() WHERE id = ?"
        DatabaseConnection.ejecutar_comando(query, (id_usuario,))

# ============================================================================
# ROLES Y PERMISOS FUNCTIONS
# ============================================================================

class RolesPermisosDB:
    """Funciones para gestionar roles y permisos"""
    
    @staticmethod
    def obtener_roles_usuario(id_usuario: str) -> List[str]:
        """Obtener nombres de roles del usuario"""
        query = """
        SELECT r.nombre_rol
        FROM dbo.usuarios_roles ur
        JOIN dbo.roles r ON ur.id_rol = r.id
        WHERE ur.id_usuario = ?
        """
        resultados = DatabaseConnection.ejecutar_query(query, (id_usuario,))
        return [fila[0] for fila in resultados]

    @staticmethod
    def obtener_permisos_usuario(id_usuario: str, id_empresa: str) -> List[Dict]:
        """Obtener permisos del usuario (por roles)"""
        query = """
        SELECT DISTINCT p.nombre_permiso, p.recurso, p.accion, p.id
        FROM dbo.usuarios_roles ur
        JOIN dbo.roles r ON ur.id_rol = r.id
        JOIN dbo.roles_permisos rp ON r.id = rp.id_rol
        JOIN dbo.permisos p ON rp.id_permiso = p.id
        WHERE ur.id_usuario = ? AND r.id_empresa = ?
        """
        resultados = DatabaseConnection.ejecutar_query(query, (id_usuario, id_empresa))
        
        permisos = []
        for fila in resultados:
            permisos.append({
                "nombre": fila[0],
                "recurso": fila[1],
                "accion": fila[2],
                "id": fila[3]
            })
        return permisos

    @staticmethod
    def verificar_permiso(id_usuario: str, id_empresa: str, 
                         recurso: str, accion: str) -> bool:
        """Verificar si usuario tiene permiso específico"""
        query = """
        SELECT COUNT(*)
        FROM dbo.usuarios_roles ur
        JOIN dbo.roles r ON ur.id_rol = r.id
        JOIN dbo.roles_permisos rp ON r.id = rp.id_rol
        JOIN dbo.permisos p ON rp.id_permiso = p.id
        WHERE ur.id_usuario = ? AND r.id_empresa = ? 
              AND p.recurso = ? AND p.accion = ?
        """
        resultados = DatabaseConnection.ejecutar_query(query, 
            (id_usuario, id_empresa, recurso, accion))
        return resultados[0][0] > 0

    @staticmethod
    def asignar_rol(id_usuario: str, id_rol: str) -> bool:
        """Asignar rol a usuario"""
        query = """
        INSERT INTO dbo.usuarios_roles (id_usuario, id_rol)
        VALUES (?, ?)
        """
        filas = DatabaseConnection.ejecutar_comando(query, (id_usuario, id_rol))
        return filas > 0

    @staticmethod
    def revocar_rol(id_usuario: str, id_rol: str) -> bool:
        """Revocar rol de usuario"""
        query = """
        DELETE FROM dbo.usuarios_roles
        WHERE id_usuario = ? AND id_rol = ?
        """
        filas = DatabaseConnection.ejecutar_comando(query, (id_usuario, id_rol))
        return filas > 0

# ============================================================================
# AUDITORÍA FUNCTIONS
# ============================================================================

class AuditoriaDB:
    """Funciones para gestionar bitácora de auditoría"""
    
    @staticmethod
    def registrar_accion(id_usuario: str, id_empresa: str, accion: str,
                        recurso: str, resultado: str, detalles: str = None,
                        direccion_ip: str = None) -> bool:
        """Registrar acción en bitácora"""
        query = """
        INSERT INTO dbo.bitacora_auditoria 
        (id_usuario, id_empresa, accion, recurso, resultado, detalles, direccion_ip)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        filas = DatabaseConnection.ejecutar_comando(query,
            (id_usuario, id_empresa, accion, recurso, resultado, detalles, direccion_ip))
        return filas > 0

    @staticmethod
    def obtener_bitacora(id_empresa: str, limite: int = 20) -> List[Dict]:
        """Obtener bitácora de auditoría por empresa"""
        query = """
        SELECT TOP (?) id, id_usuario, id_empresa, accion, recurso, resultado, 
               detalles, fecha_auditoria, direccion_ip
        FROM dbo.bitacora_auditoria
        WHERE id_empresa = ?
        ORDER BY fecha_auditoria DESC
        """
        resultados = DatabaseConnection.ejecutar_query(query, (limite, id_empresa))
        
        bitacora = []
        for fila in resultados:
            bitacora.append({
                "id": fila[0],
                "id_usuario": fila[1],
                "id_empresa": fila[2],
                "accion": fila[3],
                "recurso": fila[4],
                "resultado": fila[5],
                "detalles": fila[6],
                "fecha_auditoria": fila[7],
                "direccion_ip": fila[8]
            })
        return bitacora

    @staticmethod
    def obtener_bitacora_usuario(id_usuario: str, limite: int = 20) -> List[Dict]:
        """Obtener bitácora filtrada por usuario"""
        query = """
        SELECT TOP (?) id, id_usuario, id_empresa, accion, recurso, resultado,
               detalles, fecha_auditoria
        FROM dbo.bitacora_auditoria
        WHERE id_usuario = ?
        ORDER BY fecha_auditoria DESC
        """
        resultados = DatabaseConnection.ejecutar_query(query, (limite, id_usuario))
        
        bitacora = []
        for fila in resultados:
            bitacora.append({
                "id": fila[0],
                "id_usuario": fila[1],
                "id_empresa": fila[2],
                "accion": fila[3],
                "recurso": fila[4],
                "resultado": fila[5],
                "detalles": fila[6],
                "fecha_auditoria": fila[7]
            })
        return bitacora

# ============================================================================
# FICHAS DE ACCESO (TOKEN MANAGEMENT)
# ============================================================================

class FichasAccesoDB:
    """Funciones para gestionar fichas/tokens"""
    
    @staticmethod
    def registrar_ficha(id: str, id_usuario: str, tipo_ficha: str,
                       ficha_hash: str, expira_en: datetime) -> bool:
        """Registrar nueva ficha"""
        query = """
        INSERT INTO dbo.fichas_acceso (id, id_usuario, tipo_ficha, ficha_hash, expira_en)
        VALUES (?, ?, ?, ?, ?)
        """
        filas = DatabaseConnection.ejecutar_comando(query,
            (id, id_usuario, tipo_ficha, ficha_hash, expira_en))
        return filas > 0

    @staticmethod
    def revocar_ficha(id: str) -> bool:
        """Revocar una ficha"""
        query = """
        UPDATE dbo.fichas_acceso
        SET revocada = 1, revocada_en = GETUTCDATE()
        WHERE id = ?
        """
        filas = DatabaseConnection.ejecutar_comando(query, (id,))
        return filas > 0

    @staticmethod
    def ficha_revocada(id: str) -> bool:
        """Verificar si ficha está revocada"""
        query = "SELECT revocada FROM dbo.fichas_acceso WHERE id = ?"
        resultados = DatabaseConnection.ejecutar_query(query, (id,))
        if resultados:
            return resultados[0][0] == 1
        return False

    @staticmethod
    def limpiar_fichas_expiradas():
        """Limpiar fichas expiradas (ejecutar periódicamente)"""
        query = "DELETE FROM dbo.fichas_acceso WHERE expira_en < GETUTCDATE()"
        DatabaseConnection.ejecutar_comando(query)

# ============================================================================
# DISPOSITIVOS MFA
# ============================================================================

class DispositivosMFADB:
    """Funciones para gestionar dispositivos MFA"""
    
    @staticmethod
    def registrar_dispositivo(id: str, id_usuario: str, tipo: str,
                             codigo_secreto: str) -> bool:
        """Registrar nuevo dispositivo MFA"""
        query = """
        INSERT INTO dbo.dispositivos_mfa (id, id_usuario, tipo_dispositivo, codigo_secreto)
        VALUES (?, ?, ?, ?)
        """
        filas = DatabaseConnection.ejecutar_comando(query,
            (id, id_usuario, tipo, codigo_secreto))
        return filas > 0

    @staticmethod
    def obtener_dispositivos(id_usuario: str) -> List[Dict]:
        """Obtener dispositivos MFA del usuario"""
        query = """
        SELECT id, tipo_dispositivo, verificado, creado_en, ultimo_uso
        FROM dbo.dispositivos_mfa
        WHERE id_usuario = ?
        ORDER BY creado_en DESC
        """
        resultados = DatabaseConnection.ejecutar_query(query, (id_usuario,))
        
        dispositivos = []
        for fila in resultados:
            dispositivos.append({
                "id": fila[0],
                "tipo": fila[1],
                "verificado": fila[2],
                "creado_en": fila[3],
                "ultimo_uso": fila[4]
            })
        return dispositivos

# ============================================================================
# FUNCIONES DE PRUEBA
# ============================================================================

def probar_conexion():
    """Prueba rápida de conexión"""
    try:
        resultado = DatabaseConnection.ejecutar_query("SELECT @@VERSION")
        print("✅ Conexión SQL Server exitosa")
        print(f"SQL Server Version: {resultado[0][0][:50]}...")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def probar_usuario_demo():
    """Prueba usuario demo"""
    usuario = UsuariosDB.obtener_usuario("giovanny@imvesa.com", "imvesa")
    if usuario:
        print(f"✅ Usuario encontrado: {usuario['nombre_usuario']}")
        print(f"   ID: {usuario['id']}")
        print(f"   Empresa: {usuario['id_empresa']}")
        return True
    print("❌ Usuario no encontrado")
    return False

def probar_permisos():
    """Prueba permisos"""
    usuario = UsuariosDB.obtener_usuario("giovanny@imvesa.com", "imvesa")
    if usuario:
        roles = RolesPermisosDB.obtener_roles_usuario(usuario['id'])
        permisos = RolesPermisosDB.obtener_permisos_usuario(usuario['id'], "imvesa")
        print(f"✅ Roles: {roles}")
        print(f"✅ Permisos ({len(permisos)}): {[p['nombre'] for p in permisos[:3]]}...")
        return True
    return False

if __name__ == "__main__":
    print("=" * 80)
    print("SENTINEL v1.0 - DATABASE MODULE TEST")
    print("=" * 80)
    
    probar_conexion()
    print()
    probar_usuario_demo()
    print()
    probar_permisos()
    
    print("\n" + "=" * 80)
    print("✅ Todos los tests completados")
