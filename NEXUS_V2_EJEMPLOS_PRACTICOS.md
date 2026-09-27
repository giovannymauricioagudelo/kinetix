# 📚 NEXUS v2.0 - Ejemplos Prácticos

## 1️⃣ Crear Procedimiento de SELECT

### Caso: Obtener usuario por ID

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/create-stored-procedure
Content-Type: application/json

{
  "table_name": "users",
  "operation": "SELECT",
  "id_column": "user_id",
  "database": "mssql"
}
```

**Respuesta:**
```json
{
  "name": "sp_SELECT_users",
  "description": "SELECT procedure for users",
  "parameters": [
    {
      "name": "user_id",
      "type": "INT",
      "direction": "INPUT"
    }
  ],
  "sql_create": "CREATE PROCEDURE [dbo].[sp_SELECT_users]\n    @user_id INT\nAS\nBEGIN\n    SET NOCOUNT ON;\n    SELECT * FROM [users] WHERE [user_id] = @user_id;\nEND;\nGO"
}
```

**SQL generado:**
```sql
CREATE PROCEDURE [dbo].[sp_SELECT_users]
    @user_id INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT * FROM [users] WHERE [user_id] = @user_id;
END;
GO
```

---

## 2️⃣ Crear Procedimiento de INSERT

### Caso: Crear nuevo usuario

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/create-stored-procedure
Content-Type: application/json

{
  "table_name": "users",
  "operation": "INSERT",
  "columns_types": {
    "username": "VARCHAR",
    "email": "VARCHAR",
    "password_hash": "VARCHAR",
    "created_at": "DATETIME2",
    "is_active": "BIT"
  },
  "database": "mssql"
}
```

**Respuesta:**
```json
{
  "name": "sp_INSERT_users",
  "description": "INSERT procedure for users",
  "parameters": [
    {"name": "username", "type": "VARCHAR", "direction": "INPUT"},
    {"name": "email", "type": "VARCHAR", "direction": "INPUT"},
    {"name": "password_hash", "type": "VARCHAR", "direction": "INPUT"},
    {"name": "created_at", "type": "DATETIME2", "direction": "INPUT"},
    {"name": "is_active", "type": "BIT", "direction": "INPUT"}
  ],
  "sql_create": "..."
}
```

**SQL generado:**
```sql
CREATE PROCEDURE [dbo].[sp_INSERT_users]
    @username VARCHAR(MAX),
    @email VARCHAR(MAX),
    @password_hash VARCHAR(MAX),
    @created_at DATETIME2,
    @is_active BIT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO [users] 
        ([username], [email], [password_hash], [created_at], [is_active])
    VALUES 
        (@username, @email, @password_hash, @created_at, @is_active);
    SELECT SCOPE_IDENTITY() AS id;
END;
GO
```

---

## 3️⃣ Crear Procedimiento de UPDATE

### Caso: Actualizar perfil de usuario

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/create-stored-procedure
Content-Type: application/json

{
  "table_name": "users",
  "operation": "UPDATE",
  "id_column": "user_id",
  "columns_types": {
    "username": "VARCHAR",
    "email": "VARCHAR",
    "profile_picture": "VARCHAR",
    "updated_at": "DATETIME2"
  },
  "database": "mssql"
}
```

**SQL generado:**
```sql
CREATE PROCEDURE [dbo].[sp_UPDATE_users]
    @user_id INT,
    @username VARCHAR(MAX),
    @email VARCHAR(MAX),
    @profile_picture VARCHAR(MAX),
    @updated_at DATETIME2
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE [users]
    SET 
        [username] = @username,
        [email] = @email,
        [profile_picture] = @profile_picture,
        [updated_at] = @updated_at
    WHERE [user_id] = @user_id;
    SELECT @@ROWCOUNT AS affected_rows;
END;
GO
```

---

## 4️⃣ Crear Procedimiento de DELETE

### Caso: Eliminar usuario

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/create-stored-procedure
Content-Type: application/json

{
  "table_name": "users",
  "operation": "DELETE",
  "id_column": "user_id",
  "database": "mssql"
}
```

**SQL generado:**
```sql
CREATE PROCEDURE [dbo].[sp_DELETE_users]
    @user_id INT
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM [users]
    WHERE [user_id] = @user_id;
    SELECT @@ROWCOUNT AS affected_rows;
END;
GO
```

---

## 5️⃣ Ejecutar Procedimiento (SELECT)

### Caso: Obtener usuario por ID

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/execute-stored-procedure
Content-Type: application/json

{
  "procedure_name": "sp_SELECT_users",
  "parameters": {
    "user_id": 42
  },
  "database": "mssql"
}
```

**Respuesta:**
```json
{
  "status": "success",
  "rows": 1,
  "columns": ["user_id", "username", "email", "is_active"],
  "data": [
    {
      "user_id": 42,
      "username": "johndoe",
      "email": "john@example.com",
      "is_active": true
    }
  ],
  "procedure_used": "sp_SELECT_users",
  "execution_time_ms": 12.5,
  "timestamp": "2026-09-27T15:30:45Z"
}
```

---

## 6️⃣ CRUD Automático - INSERT

### Caso: Crear nuevo usuario (el más simple)

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/crud
Content-Type: application/json

{
  "table_name": "users",
  "operation": "INSERT",
  "data": {
    "username": "newuser",
    "email": "newuser@example.com",
    "password_hash": "$2b$12$...",
    "created_at": "2026-09-27T15:30:45Z",
    "is_active": true
  },
  "database": "mssql"
}
```

**Respuesta:**
```json
{
  "status": "success",
  "operation": "INSERT",
  "table_name": "users",
  "affected_rows": 1,
  "procedure_name": "sp_INSERT_users",
  "execution_time_ms": 18.3,
  "timestamp": "2026-09-27T15:30:45Z"
}
```

### Qué sucede internamente:
1. ✅ Valida `table_name` = "users" (válido)
2. ✅ Valida cada clave en `data`: username, email, password_hash, created_at, is_active (todas válidas)
3. ✅ Genera/obtiene procedimiento `sp_INSERT_users`
4. ✅ Ejecuta con parámetros seguros (nunca concatena SQL)
5. ✅ Retorna número de filas afectadas

---

## 7️⃣ CRUD Automático - UPDATE

### Caso: Actualizar email de usuario

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/crud
Content-Type: application/json

{
  "table_name": "users",
  "operation": "UPDATE",
  "id": 42,
  "data": {
    "email": "newemail@example.com",
    "updated_at": "2026-09-27T15:35:00Z"
  },
  "database": "mssql"
}
```

**Respuesta:**
```json
{
  "status": "success",
  "operation": "UPDATE",
  "table_name": "users",
  "affected_rows": 1,
  "procedure_name": "sp_UPDATE_users",
  "execution_time_ms": 15.7,
  "timestamp": "2026-09-27T15:35:00Z"
}
```

---

## 8️⃣ CRUD Automático - DELETE

### Caso: Eliminar usuario

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/crud
Content-Type: application/json

{
  "table_name": "users",
  "operation": "DELETE",
  "id": 42,
  "database": "mssql"
}
```

**Respuesta:**
```json
{
  "status": "success",
  "operation": "DELETE",
  "table_name": "users",
  "affected_rows": 1,
  "procedure_name": "sp_DELETE_users",
  "execution_time_ms": 8.2,
  "timestamp": "2026-09-27T15:35:30Z"
}
```

---

## 9️⃣ Listar Procedimientos Disponibles

**Solicitud:**
```bash
GET http://localhost:8000/api/v1/nexus/stored-procedures?database=mssql
```

**Respuesta:**
```json
{
  "status": "success",
  "database": "mssql",
  "total": 4,
  "procedures": [
    {
      "name": "sp_SELECT_users",
      "type": "SELECT",
      "table": "users",
      "parameters": ["@user_id"],
      "created": "2026-09-27T10:00:00Z"
    },
    {
      "name": "sp_INSERT_users",
      "type": "INSERT",
      "table": "users",
      "parameters": ["@username", "@email", "@password_hash", "@created_at", "@is_active"],
      "created": "2026-09-27T10:05:00Z"
    },
    {
      "name": "sp_UPDATE_users",
      "type": "UPDATE",
      "table": "users",
      "parameters": ["@user_id", "@username", "@email", "@updated_at"],
      "created": "2026-09-27T10:10:00Z"
    },
    {
      "name": "sp_DELETE_users",
      "type": "DELETE",
      "table": "users",
      "parameters": ["@user_id"],
      "created": "2026-09-27T10:15:00Z"
    }
  ],
  "timestamp": "2026-09-27T15:40:00Z"
}
```

---

## 🔟 Prueba de SQL Injection Prevention

### Caso 1: Intento simple de inyección

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/test-sql-injection
?table_name=users&malicious_input='; DROP TABLE users; --
```

**Respuesta:**
```json
{
  "status": "completed",
  "message": "SQL Injection Test FAILED",
  "safe": false,
  "validation_results": {
    "table_name_valid": true,
    "input_length_ok": true,
    "contains_semicolon": true,
    "contains_quotes": true,
    "contains_comment": true,
    "contains_or": false,
    "contains_union": false,
    "contains_drop": true,
    "contains_delete": false
  },
  "timestamp": "2026-09-27T15:45:00Z"
}
```

### Caso 2: Intento OR 1=1

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/test-sql-injection
?table_name=users&malicious_input=1 OR 1=1
```

**Respuesta:**
```json
{
  "status": "completed",
  "message": "SQL Injection Test FAILED",
  "safe": false,
  "validation_results": {
    ...
    "contains_or": true,
    ...
  },
  "timestamp": "2026-09-27T15:45:30Z"
}
```

### Caso 3: Input válido

**Solicitud:**
```bash
POST http://localhost:8000/api/v1/nexus/test-sql-injection
?table_name=users&malicious_input=John Doe
```

**Respuesta:**
```json
{
  "status": "completed",
  "message": "SQL Injection Test PASSED",
  "safe": true,
  "validation_results": {
    "table_name_valid": true,
    "input_length_ok": true,
    "contains_semicolon": false,
    "contains_quotes": false,
    "contains_comment": false,
    "contains_or": false,
    "contains_union": false,
    "contains_drop": false,
    "contains_delete": false
  },
  "timestamp": "2026-09-27T15:46:00Z"
}
```

---

## 1️⃣1️⃣ Obtener Definición de Procedimiento

**Solicitud:**
```bash
GET http://localhost:8000/api/v1/nexus/procedure-definition
?procedure_name=sp_SELECT_users&database=mssql
```

**Respuesta:**
```json
{
  "status": "success",
  "procedure_name": "sp_SELECT_users",
  "database": "mssql",
  "definition_query": "SELECT OBJECT_DEFINITION(OBJECT_ID('sp_SELECT_users')) AS definition;",
  "note": "En PROD ejecutaría esta query contra la BD",
  "timestamp": "2026-09-27T15:50:00Z"
}
```

---

## 🔄 Casos de Uso Complejos

### Caso: Sistema de E-Commerce

**Tabla:** `orders`

**1. Crear SP de INSERT:**
```json
{
  "table_name": "orders",
  "operation": "INSERT",
  "columns_types": {
    "user_id": "INT",
    "total_amount": "DECIMAL",
    "status": "VARCHAR",
    "created_at": "DATETIME2"
  }
}
```

**2. Crear SP de UPDATE (cambiar estado):**
```json
{
  "table_name": "orders",
  "operation": "UPDATE",
  "id_column": "order_id",
  "columns_types": {
    "status": "VARCHAR",
    "updated_at": "DATETIME2"
  }
}
```

**3. Crear nueva orden:**
```json
{
  "table_name": "orders",
  "operation": "INSERT",
  "data": {
    "user_id": 123,
    "total_amount": 499.99,
    "status": "PENDING",
    "created_at": "2026-09-27T16:00:00Z"
  }
}
```

**4. Actualizar estado a "SHIPPED":**
```json
{
  "table_name": "orders",
  "operation": "UPDATE",
  "id": 5,
  "data": {
    "status": "SHIPPED",
    "updated_at": "2026-09-27T16:30:00Z"
  }
}
```

---

## 💡 Comparación: Antes vs Después

### ❌ ANTES (v1.0 - SQL Directo)

```python
# INSEGURO
async def create_order(user_id, total_amount, status):
    sql = f"""
    INSERT INTO orders (user_id, total_amount, status, created_at)
    VALUES ({user_id}, {total_amount}, '{status}', GETDATE())
    """
    # Si status = "'; DELETE FROM orders; --"
    # ¡DESASTRE!
    await execute(sql)
```

### ✅ DESPUÉS (v2.0 - Procedimiento Almacenado)

```python
# SEGURO
async def create_order(user_id, total_amount, status):
    result = await execute_procedure(
        "sp_INSERT_orders",
        parameters={
            "user_id": user_id,
            "total_amount": total_amount,
            "status": status,
            "created_at": datetime.utcnow()
        }
    )
    # Si status = "'; DELETE FROM orders; --"
    # Se trata como un parámetro literal, NO SQL
    # SEGURO 100%
    return result
```

---

## 🎓 Resumen

| Aspecto | v1.0 | v2.0 |
|--------|------|------|
| **SQL Directo** | Sí (vulnerable) | No |
| **Procedimientos** | No | Sí |
| **SQL Injection** | Posible | Imposible |
| **Parámetros** | Concatenados | Nombrados (@param) |
| **Tipado** | Débil | Fuerte |
| **Performance** | Bueno | Excelente |
| **Enterprise** | No | Sí |

---

## 📖 Documentación Completa

Ver: **NEXUS_V2_SECURITY_GUIDE.md**

---

¡NEXUS v2.0 está listo para producción! 🚀🔒
