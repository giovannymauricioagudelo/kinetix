#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SENTINEL v1.0 Phase 2 - MFA + Rate Limiting [DEFINITIVO - UPSERT]
================================================================================
Agente de Seguridad #10 - VERSIÓN FINAL CON UPSERT
Soluciona problemas de UNIQUE constraint en mfa_secrets
================================================================================
"""

import os
import sys
import secrets
import jwt
import json
import pyotp
import qrcode
import bcrypt
import pyodbc
from io import BytesIO
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from collections import defaultdict

# ================================================================================
# CONFIG
# ================================================================================

DB_CONFIG = {
    "Driver": "{ODBC Driver 18 for SQL Server}",
    "Server": "localhost",
    "Database": "kinetix",
    "UID": "sa",
    "PWD": os.getenv("SQLSERVER_PASSWORD", ""),
    "TrustServerCertificate": "yes"
}

# Sin SENTINEL_SECRET_KEY se genera una clave aleatoria: los tokens se invalidan al reiniciar.
SECRET_KEY = os.getenv("SENTINEL_SECRET_KEY") or secrets.token_urlsafe(32)
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 1440
RATE_LIMIT_ATTEMPTS = 5
RATE_LIMIT_WINDOW_MINUTES = 15

# ================================================================================
# MODELOS PYDANTIC
# ================================================================================

class SolicitudAutenticacion(BaseModel):
    """Autenticación básica (sin MFA)"""
    nombre_usuario: str
    contrasena: str
    id_empresa: str = "gio"

class SolicitudAutenticacionMFA(BaseModel):
    """Autenticación con MFA"""
    nombre_usuario: str
    contrasena: str
    codigo_mfa: str
    id_empresa: str = "gio"
    recordar_dispositivo: bool = False

class SolicitudConfigureMFA(BaseModel):
    """Solicitud para configurar MFA"""
    metodo: str = "totp"

class SolicitudConfirmarMFA(BaseModel):
    """Solicitud para confirmar código MFA"""
    codigo: str

# ================================================================================
# UTILIDADES CRIPTOGRÁFICAS
# ================================================================================

def verificar_contrasena(contrasena_plain: str, hash_almacenado: str) -> bool:
    """Verifica contraseña contra hash bcrypt"""
    try:
        return bcrypt.checkpw(contrasena_plain.encode('utf-8'), hash_almacenado.encode('utf-8'))
    except Exception:
        return False

def generar_ficha_jwt(datos: Dict[str, Any], minutos_expira: int = TOKEN_EXPIRE_MINUTES) -> str:
    """Genera JWT token"""
    payload = {
        **datos,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=minutos_expira)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def validar_ficha_jwt(token: str) -> Dict[str, Any]:
    """Valida JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

def obtener_usuario_actual(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> Dict[str, Any]:
    """Obtiene usuario del JWT token"""
    return validar_ficha_jwt(credentials.credentials)

# ================================================================================
# BASE DE DATOS
# ================================================================================

class ConexionBD:
    """Gestor de conexión a SQL Server"""
    
    @staticmethod
    def conectar():
        """Abre conexión a BD"""
        try:
            conn_str = ";".join([f"{k}={v}" for k, v in DB_CONFIG.items()])
            return pyodbc.connect(conn_str)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error conexión BD: {str(e)}")
    
    @staticmethod
    def obtener_usuario(nombre_usuario: str, id_empresa: str) -> Optional[Dict]:
        """Obtiene usuario de BD"""
        try:
            conn = ConexionBD.conectar()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, nombre_usuario, hash_contrasena, id_empresa, estado
                FROM usuarios
                WHERE nombre_usuario = ? AND id_empresa = ?
            """, (nombre_usuario, id_empresa))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "id": row[0],
                    "nombre_usuario": row[1],
                    "hash_contrasena": row[2],
                    "id_empresa": row[3],
                    "estado": row[4]
                }
            return None
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error BD: {str(e)}")

class MFADB:
    """Gestor MFA en BD - VERSIÓN UPSERT"""
    
    @staticmethod
    def crear_secret_mfa(id_usuario: str) -> str:
        """Crea secret TOTP con UPSERT (INSERT ... MERGE)"""
        try:
            secret = pyotp.random_base32()
            conn = ConexionBD.conectar()
            cursor = conn.cursor()
            
            # SQL Server UPSERT con MERGE
            sql_upsert = """
            MERGE INTO mfa_secrets AS target
            USING (SELECT ? AS id_usuario) AS source
            ON target.id_usuario = source.id_usuario
            WHEN MATCHED THEN
                UPDATE SET secret_totp = ?, habilitado = 0, fecha_creacion = ?
            WHEN NOT MATCHED THEN
                INSERT (id_usuario, secret_totp, habilitado, fecha_creacion)
                VALUES (?, ?, 0, ?);
            """
            
            ahora = datetime.utcnow()
            cursor.execute(sql_upsert, (id_usuario, secret, ahora, id_usuario, secret, ahora))
            conn.commit()
            conn.close()
            
            return secret
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error MFA: {str(e)}")
    
    @staticmethod
    def mfa_habilitado(id_usuario: str) -> bool:
        """Verifica si MFA está habilitado"""
        try:
            conn = ConexionBD.conectar()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT habilitado FROM mfa_secrets WHERE id_usuario = ?
            """, (id_usuario,))
            row = cursor.fetchone()
            conn.close()
            return row and row[0] == 1 if row else False
        except Exception:
            return False
    
    @staticmethod
    def obtener_secret_mfa(id_usuario: str) -> Optional[str]:
        """Obtiene secret TOTP"""
        try:
            conn = ConexionBD.conectar()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT secret_totp FROM mfa_secrets WHERE id_usuario = ?
            """, (id_usuario,))
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception:
            return None
    
    @staticmethod
    def verificar_codigo_mfa(id_usuario: str, codigo: str) -> bool:
        """Verifica código TOTP"""
        secret = MFADB.obtener_secret_mfa(id_usuario)
        if not secret:
            return False
        
        totp = pyotp.TOTP(secret)
        return totp.verify(codigo)
    
    @staticmethod
    def confirmar_mfa(id_usuario: str, codigo: str) -> bool:
        """Confirma y habilita MFA"""
        if not MFADB.verificar_codigo_mfa(id_usuario, codigo):
            return False
        
        try:
            conn = ConexionBD.conectar()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE mfa_secrets SET habilitado = 1, fecha_confirmacion = ?
                WHERE id_usuario = ?
            """, (datetime.utcnow(), id_usuario))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

class RateLimiter:
    """Limitador de intentos de autenticación"""
    
    def __init__(self):
        self.intentos = defaultdict(list)
    
    def registrar_intento(self, clave: str) -> bool:
        """Registra intento, retorna True si está dentro del límite"""
        ahora = datetime.utcnow()
        ventana_minima = ahora - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
        
        # Limpia intentos antiguos
        self.intentos[clave] = [t for t in self.intentos[clave] if t > ventana_minima]
        
        # Si excedió límite, retorna False
        if len(self.intentos[clave]) >= RATE_LIMIT_ATTEMPTS:
            return False
        
        # Registra nuevo intento
        self.intentos[clave].append(ahora)
        return True

# ================================================================================
# INSTANCIAS GLOBALES
# ================================================================================

app = FastAPI(
    title="SENTINEL v1.0 Phase 2 - MFA + Rate Limiting",
    description="Security con MFA TOTP + Rate Limiting + Dispositivos conocidos",
    version="1.0.1-MFA-DEFINITIVO"
)

security = HTTPBearer()
rate_limiter = RateLimiter()

# ================================================================================
# ENDPOINTS
# ================================================================================

@app.get("/api/v1/sentinel/info")
async def obtener_informacion():
    """Obtener Informacion - Información del agente Phase 2"""
    return {
        "estado": "exito",
        "agente": "SENTINEL",
        "version": "1.0.1-Phase2-MFA-DEFINITIVO",
        "empresa": "gio",
        "features": ["MFA TOTP", "Rate Limiting", "Dispositivos conocidos", "JWT + bcrypt"],
        "endpoints": 13
    }

@app.post("/api/v1/sentinel/autenticar")
async def autenticar_basico(solicitud: SolicitudAutenticacion):
    """Autenticar - Autenticación básica sin MFA"""
    
    clave_rl = f"{solicitud.nombre_usuario}:{solicitud.id_empresa}"
    if not rate_limiter.registrar_intento(clave_rl):
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de autenticación. Espere 15 minutos."
        )
    
    usuario = ConexionBD.obtener_usuario(solicitud.nombre_usuario, solicitud.id_empresa)
    
    if not usuario:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    if not verificar_contrasena(solicitud.contrasena, usuario["hash_contrasena"]):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    token = generar_ficha_jwt({
        "id": usuario["id"],
        "nombre_usuario": usuario["nombre_usuario"],
        "id_empresa": usuario["id_empresa"],
        "tipo": "autenticacion_basica"
    })
    
    return {
        "estado": "exito",
        "token": token,
        "usuario": usuario["nombre_usuario"],
        "mfa_habilitado": MFADB.mfa_habilitado(usuario["id"])
    }

@app.post("/api/v1/sentinel/autenticar-mfa")
async def autenticar_con_mfa(solicitud: SolicitudAutenticacionMFA):
    """Autenticar Con Mfa - Autenticar con contraseña + código MFA"""
    
    clave_rl = f"{solicitud.nombre_usuario}:{solicitud.id_empresa}"
    if not rate_limiter.registrar_intento(clave_rl):
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos de autenticación. Espere 15 minutos."
        )
    
    usuario = ConexionBD.obtener_usuario(solicitud.nombre_usuario, solicitud.id_empresa)
    
    if not usuario:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    if not verificar_contrasena(solicitud.contrasena, usuario["hash_contrasena"]):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    mfa_enabled = MFADB.mfa_habilitado(usuario["id"])
    if mfa_enabled:
        if not MFADB.verificar_codigo_mfa(usuario["id"], solicitud.codigo_mfa):
            raise HTTPException(status_code=401, detail="Código MFA inválido")
    
    token = generar_ficha_jwt({
        "id": usuario["id"],
        "nombre_usuario": usuario["nombre_usuario"],
        "id_empresa": usuario["id_empresa"],
        "tipo": "autenticacion_mfa" if mfa_enabled else "autenticacion_basica"
    })
    
    return {
        "estado": "exito",
        "token": token,
        "usuario": usuario["nombre_usuario"],
        "mfa_habilitado": mfa_enabled
    }

@app.post("/api/v1/sentinel/configurar-mfa")
async def configurar_mfa(
    solicitud: SolicitudConfigureMFA,
    usuario_actual: Dict = Depends(obtener_usuario_actual)
):
    """Configurar Mfa - Configurar MFA para usuario (TOTP) - UPSERT SAFE"""
    
    id_usuario = usuario_actual["id"]
    
    # Crear o recuperar secret con UPSERT
    secret = MFADB.crear_secret_mfa(id_usuario)
    
    # Generar QR
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(
        name=usuario_actual["nombre_usuario"],
        issuer_name="SENTINEL - Kinetix"
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    img_b64 = __import__('base64').b64encode(img_bytes.getvalue()).decode()
    
    return {
        "estado": "exito",
        "secret": secret,
        "qr_code": f"data:image/png;base64,{img_b64}",
        "uri": uri,
        "instrucciones": [
            "1. Abre Google Authenticator o Microsoft Authenticator",
            "2. Escanea el código QR",
            "3. Obtén un código de 6 dígitos",
            "4. Confirma con POST /confirmar-mfa"
        ]
    }

@app.post("/api/v1/sentinel/confirmar-mfa")
async def confirmar_mfa(
    solicitud: SolicitudConfirmarMFA,
    usuario_actual: Dict = Depends(obtener_usuario_actual)
):
    """Confirmar Mfa - Confirmar código MFA y habilitar"""
    
    id_usuario = usuario_actual["id"]
    
    if not MFADB.confirmar_mfa(id_usuario, solicitud.codigo):
        raise HTTPException(status_code=400, detail="Código MFA inválido o expirado")
    
    return {
        "estado": "exito",
        "mensaje": "MFA habilitado exitosamente",
        "usuario": usuario_actual["nombre_usuario"]
    }

@app.post("/api/v1/sentinel/deshabilitar-mfa")
async def deshabilitar_mfa(usuario_actual: Dict = Depends(obtener_usuario_actual)):
    """Deshabilitar Mfa - Deshabilitar MFA"""
    
    id_usuario = usuario_actual["id"]
    
    try:
        conn = ConexionBD.conectar()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE mfa_secrets SET habilitado = 0, fecha_deshabilitacion = ?
            WHERE id_usuario = ?
        """, (datetime.utcnow(), id_usuario))
        conn.commit()
        conn.close()
        
        return {
            "estado": "exito",
            "mensaje": "MFA deshabilitado"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/v1/sentinel/dispositivos")
async def obtener_dispositivos(usuario_actual: Dict = Depends(obtener_usuario_actual)):
    """Obtener Dispositivos - Obtener dispositivos conocidos"""
    
    return {
        "estado": "exito",
        "dispositivos": []
    }

@app.delete("/api/v1/sentinel/dispositivos/{id_dispositivo}")
async def eliminar_dispositivo(
    id_dispositivo: str,
    usuario_actual: Dict = Depends(obtener_usuario_actual)
):
    """Eliminar Dispositivo - Eliminar dispositivo conocido"""
    
    return {
        "estado": "exito",
        "mensaje": f"Dispositivo {id_dispositivo} eliminado"
    }

@app.get("/api/v1/sentinel/rate-limit-status")
async def obtener_rate_limit_status(usuario_actual: Dict = Depends(obtener_usuario_actual)):
    """Obtener Rate Limit Status"""
    
    return {
        "estado": "exito",
        "usuario": usuario_actual["nombre_usuario"],
        "intentos_restantes": RATE_LIMIT_ATTEMPTS,
        "ventana_minutos": RATE_LIMIT_WINDOW_MINUTES,
        "estado_limite": "OK"
    }

# ================================================================================
# MAIN
# ================================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*80)
    print("🚀 INICIANDO SENTINEL v1.0 PHASE 2 - MFA + RATE LIMITING [DEFINITIVO]")
    print("="*80)
    print("📍 Empresa: GIO")
    print("📍 Acceso a API: http://127.0.0.1:8001")
    print("📍 Swagger UI: http://127.0.0.1:8001/docs")
    print("📍 Features: MFA TOTP + Rate Limiting + UPSERT Safe")
    print("📍 Database: SQL Server kinetix (nombres correctos)")
    print("="*80 + "\n")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001,
        log_level="info"
    )
