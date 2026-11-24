# Seguridad por aplicación (plantilla fundamental)

Toda aplicación generada por Kinetix nace con controles OWASP para que el “vibe coding” no deje apps hackeables.

Regla operativa: `.cursor/rules/seguridad-por-aplicacion.mdc`  
Checklist canónico: `src/agents/security_checklist.py`

## Controles

Autenticación, claves API solo en servidor, HTTPS, contraseñas con hash, validación en servidor, XSS, CSRF, CORS, cabeceras, cookies HttpOnly/Secure/SameSite, límite de peticiones, subida de archivos, pagos en servidor, auditoría de dependencias, secretos fuera de Git.

## Agentes

| Práctica | Agente |
| --- | --- |
| Auth, hash, cookies, MFA | Sentinel |
| HTTPS, CORS, rate limit, cabeceras, API keys servidor | Synapse |
| Validación, XSS, CSRF, archivos, pagos | Vector |
| UI sin secretos | Aurora |
| Datos / RLS / procs | Nexus |
| Git sin secretos, deps CI, HTTPS deploy | Orbit |
| Pruebas e informe `docs/seguridad.md` | Prism |
| Alertas 401/403/429 | Argus |

## Cortex

Apps nuevas media/alta: sprint `seguridad` (antes de `rendimiento`) con `security_checklist.sprint_tasks()`.

## Relación con Llavia

Llavia ya implementa gran parte del modelo (`docs/seguridad.md` en su repo): bcrypt, JWT+MFA, cabeceras CSP, CORS, rate limit en auth/portal, pagos/webhooks en servidor, `.env` ignorado. El residual documentado: tokens en `sessionStorage` (mejorar a cookies HttpOnly en un sprint dedicado).
