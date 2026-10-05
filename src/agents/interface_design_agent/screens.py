"""
Pantallas HTML de Aurora: prototipos navegables, responsivos y accesibles (WCAG 2.1 AA) generados desde los tokens.

Todas comparten un shell de aplicación (barra lateral contraíble, barra superior con búsqueda, selector de empresa,
notificaciones, tema claro/oscuro y menú de usuario, migas de pan) salvo login. Las opciones permiten adaptar la
entidad, los campos, las columnas, los módulos y el modo multiempresa. Todo texto del usuario se escapa.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.agents.interface_design_agent.design import DesignError
from src.agents.interface_design_agent.exporters import to_css

SCREEN_TYPES = ("login", "dashboard", "list", "form", "detail", "settings")
LANGUAGES = ("es", "en", "pt")
FIELD_TYPES = ("text", "email", "number", "date", "tel", "select", "textarea", "checkbox")
FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_FIELDS, MAX_MODULES, MAX_COMPANIES, MAX_KPIS, MAX_OPTIONS = 30, 12, 20, 8, 20
SAMPLE_ROWS = 24

_TEXTS: Dict[str, Dict[str, Any]] = {
    "es": {
        "skip": "Saltar al contenido", "menu": "Menú principal", "toggle_menu": "Mostrar u ocultar menú",
        "search": "Buscar", "search_hint": "Buscar… (atajo /)", "notifications": "Notificaciones",
        "new_notifications": "notificaciones nuevas", "theme": "Cambiar entre tema claro y oscuro", "company": "Empresa",
        "user_menu": "Menú de usuario", "profile": "Mi perfil", "logout": "Cerrar sesión", "home": "Inicio",
        "dashboard": "Panel", "reports": "Reportes", "settings": "Configuración", "record": "Registro",
        "records": "Registros", "new": "Nuevo", "export": "Exportar CSV", "status": "Estado", "all": "Todos",
        "active": "Activo", "inactive": "Inactivo", "pending": "Pendiente", "actions": "Acciones", "view": "Ver",
        "edit": "Editar", "delete": "Eliminar", "selected": "seleccionados", "select_all": "Seleccionar todos",
        "select_row": "Seleccionar", "rows_per_page": "Filas por página", "prev": "Anterior", "next": "Siguiente",
        "page": "Página", "of": "de", "results": "resultados", "density": "Vista compacta",
        "empty_title": "No hay resultados", "empty_text": "Ajusta la búsqueda o los filtros para ver registros.",
        "clear": "Limpiar filtros", "save": "Guardar", "cancel": "Cancelar",
        "required_hint": "Los campos marcados con * son obligatorios.", "required_error": "Este campo es obligatorio.",
        "email_error": "Ingresa un correo válido.", "saved": "Cambios guardados", "deleted": "Registros eliminados",
        "confirm_title": "¿Descartar los cambios?", "confirm_text": "Los cambios que no guardaste se perderán.",
        "discard": "Descartar", "keep": "Seguir editando", "delete_title": "¿Eliminar este registro?",
        "delete_text": "Esta acción no se puede deshacer.", "general": "Información general",
        "additional": "Información adicional", "login_title": "Iniciar sesión",
        "login_sub": "Ingresa tus credenciales para continuar.", "username": "Usuario o correo",
        "password": "Contraseña", "show_password": "Mostrar contraseña", "remember": "Recordarme en este equipo",
        "forgot": "¿Olvidaste tu contraseña?", "login_btn": "Entrar",
        "hero": "Gestiona toda tu operación desde un solo lugar, con datos seguros y siempre disponibles.",
        "features": ["Indicadores en tiempo real", "Acceso por roles y auditoría", "Disponible en web y móvil"],
        "welcome": "Hola de nuevo", "period": "Periodo", "periods": ["Últimos 7 días", "Últimos 30 días", "Este año"],
        "vs_prev": "frente al periodo anterior", "up": "Sube", "down": "Baja", "trend": "Evolución mensual",
        "chart_desc": "Gráfico de líneas con la evolución de los últimos 12 meses; tendencia creciente.",
        "show_data": "Ver los datos del gráfico", "month": "Mes", "value": "Valor", "activity": "Actividad reciente",
        "quick": "Acciones rápidas", "details": "Detalle", "history": "Historial", "created": "Creado",
        "updated": "Actualizado", "by": "por", "profile_tab": "Perfil", "security_tab": "Seguridad",
        "notif_tab": "Notificaciones", "appearance_tab": "Apariencia", "full_name": "Nombre completo",
        "email": "Correo", "language": "Idioma", "dark_mode": "Usar modo oscuro",
        "email_notif": "Recibir un resumen diario por correo", "push_notif": "Avisos en el navegador",
        "mfa": "Verificación en dos pasos", "mfa_text": "Pide un código adicional al iniciar sesión.",
        "sessions": "Cerrar las demás sesiones", "close": "Cerrar", "yes": "Sí", "no": "No",
        "kpis": ["Ventas", "Pedidos", "Clientes", "Incidencias"],
        "fields": ["Nombre", "Correo", "Teléfono", "Categoría", "Fecha", "Notas"],
        "choices": ["General", "Prioritario", "Corporativo"], "companies": ["Empresa principal", "Sucursal norte"],
        "user": "Usuario", "months": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
        "events": ["creó un registro", "actualizó un registro", "exportó un reporte", "aprobó una solicitud", "inició sesión"],
        "ago": ["hace 5 min", "hace 20 min", "hace 1 h", "hace 3 h", "ayer"],
    },
    "en": {
        "skip": "Skip to content", "menu": "Main menu", "toggle_menu": "Show or hide menu",
        "search": "Search", "search_hint": "Search… (shortcut /)", "notifications": "Notifications",
        "new_notifications": "new notifications", "theme": "Toggle light and dark theme", "company": "Company",
        "user_menu": "User menu", "profile": "My profile", "logout": "Sign out", "home": "Home",
        "dashboard": "Dashboard", "reports": "Reports", "settings": "Settings", "record": "Record",
        "records": "Records", "new": "New", "export": "Export CSV", "status": "Status", "all": "All",
        "active": "Active", "inactive": "Inactive", "pending": "Pending", "actions": "Actions", "view": "View",
        "edit": "Edit", "delete": "Delete", "selected": "selected", "select_all": "Select all",
        "select_row": "Select", "rows_per_page": "Rows per page", "prev": "Previous", "next": "Next",
        "page": "Page", "of": "of", "results": "results", "density": "Compact view",
        "empty_title": "No results", "empty_text": "Adjust your search or filters to see records.",
        "clear": "Clear filters", "save": "Save", "cancel": "Cancel",
        "required_hint": "Fields marked with * are required.", "required_error": "This field is required.",
        "email_error": "Enter a valid email address.", "saved": "Changes saved", "deleted": "Records deleted",
        "confirm_title": "Discard changes?", "confirm_text": "Changes you have not saved will be lost.",
        "discard": "Discard", "keep": "Keep editing", "delete_title": "Delete this record?",
        "delete_text": "This action cannot be undone.", "general": "General information",
        "additional": "Additional information", "login_title": "Sign in",
        "login_sub": "Enter your credentials to continue.", "username": "Username or email",
        "password": "Password", "show_password": "Show password", "remember": "Remember me on this device",
        "forgot": "Forgot your password?", "login_btn": "Sign in",
        "hero": "Run your whole operation from one place, with secure and always-available data.",
        "features": ["Real-time indicators", "Role-based access and audit trail", "Available on web and mobile"],
        "welcome": "Welcome back", "period": "Period", "periods": ["Last 7 days", "Last 30 days", "This year"],
        "vs_prev": "vs. previous period", "up": "Up", "down": "Down", "trend": "Monthly trend",
        "chart_desc": "Line chart showing the last 12 months; upward trend.",
        "show_data": "Show chart data", "month": "Month", "value": "Value", "activity": "Recent activity",
        "quick": "Quick actions", "details": "Details", "history": "History", "created": "Created",
        "updated": "Updated", "by": "by", "profile_tab": "Profile", "security_tab": "Security",
        "notif_tab": "Notifications", "appearance_tab": "Appearance", "full_name": "Full name",
        "email": "Email", "language": "Language", "dark_mode": "Use dark mode",
        "email_notif": "Receive a daily email summary", "push_notif": "Browser notifications",
        "mfa": "Two-step verification", "mfa_text": "Ask for an extra code when signing in.",
        "sessions": "Sign out other sessions", "close": "Close", "yes": "Yes", "no": "No",
        "kpis": ["Sales", "Orders", "Customers", "Incidents"],
        "fields": ["Name", "Email", "Phone", "Category", "Date", "Notes"],
        "choices": ["General", "Priority", "Corporate"], "companies": ["Main company", "North branch"],
        "user": "User", "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "events": ["created a record", "updated a record", "exported a report", "approved a request", "signed in"],
        "ago": ["5 min ago", "20 min ago", "1 h ago", "3 h ago", "yesterday"],
    },
    "pt": {
        "skip": "Pular para o conteúdo", "menu": "Menu principal", "toggle_menu": "Mostrar ou ocultar menu",
        "search": "Pesquisar", "search_hint": "Pesquisar… (atalho /)", "notifications": "Notificações",
        "new_notifications": "notificações novas", "theme": "Alternar tema claro e escuro", "company": "Empresa",
        "user_menu": "Menu do usuário", "profile": "Meu perfil", "logout": "Sair", "home": "Início",
        "dashboard": "Painel", "reports": "Relatórios", "settings": "Configurações", "record": "Registro",
        "records": "Registros", "new": "Novo", "export": "Exportar CSV", "status": "Status", "all": "Todos",
        "active": "Ativo", "inactive": "Inativo", "pending": "Pendente", "actions": "Ações", "view": "Ver",
        "edit": "Editar", "delete": "Excluir", "selected": "selecionados", "select_all": "Selecionar todos",
        "select_row": "Selecionar", "rows_per_page": "Linhas por página", "prev": "Anterior", "next": "Próxima",
        "page": "Página", "of": "de", "results": "resultados", "density": "Visualização compacta",
        "empty_title": "Nenhum resultado", "empty_text": "Ajuste a pesquisa ou os filtros para ver registros.",
        "clear": "Limpar filtros", "save": "Salvar", "cancel": "Cancelar",
        "required_hint": "Campos marcados com * são obrigatórios.", "required_error": "Este campo é obrigatório.",
        "email_error": "Informe um e-mail válido.", "saved": "Alterações salvas", "deleted": "Registros excluídos",
        "confirm_title": "Descartar as alterações?", "confirm_text": "As alterações não salvas serão perdidas.",
        "discard": "Descartar", "keep": "Continuar editando", "delete_title": "Excluir este registro?",
        "delete_text": "Esta ação não pode ser desfeita.", "general": "Informações gerais",
        "additional": "Informações adicionais", "login_title": "Entrar",
        "login_sub": "Informe suas credenciais para continuar.", "username": "Usuário ou e-mail",
        "password": "Senha", "show_password": "Mostrar senha", "remember": "Lembrar de mim neste dispositivo",
        "forgot": "Esqueceu sua senha?", "login_btn": "Entrar",
        "hero": "Gerencie toda a sua operação em um só lugar, com dados seguros e sempre disponíveis.",
        "features": ["Indicadores em tempo real", "Acesso por perfis e auditoria", "Disponível na web e no celular"],
        "welcome": "Olá de novo", "period": "Período", "periods": ["Últimos 7 dias", "Últimos 30 dias", "Este ano"],
        "vs_prev": "em relação ao período anterior", "up": "Sobe", "down": "Cai", "trend": "Evolução mensal",
        "chart_desc": "Gráfico de linhas com a evolução dos últimos 12 meses; tendência de alta.",
        "show_data": "Ver os dados do gráfico", "month": "Mês", "value": "Valor", "activity": "Atividade recente",
        "quick": "Ações rápidas", "details": "Detalhes", "history": "Histórico", "created": "Criado",
        "updated": "Atualizado", "by": "por", "profile_tab": "Perfil", "security_tab": "Segurança",
        "notif_tab": "Notificações", "appearance_tab": "Aparência", "full_name": "Nome completo",
        "email": "E-mail", "language": "Idioma", "dark_mode": "Usar modo escuro",
        "email_notif": "Receber um resumo diário por e-mail", "push_notif": "Avisos no navegador",
        "mfa": "Verificação em duas etapas", "mfa_text": "Solicita um código adicional ao entrar.",
        "sessions": "Encerrar as outras sessões", "close": "Fechar", "yes": "Sim", "no": "Não",
        "kpis": ["Vendas", "Pedidos", "Clientes", "Incidentes"],
        "fields": ["Nome", "E-mail", "Telefone", "Categoria", "Data", "Observações"],
        "choices": ["Geral", "Prioritário", "Corporativo"], "companies": ["Empresa principal", "Filial norte"],
        "user": "Usuário", "months": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
        "events": ["criou um registro", "atualizou um registro", "exportou um relatório", "aprovou uma solicitação", "entrou"],
        "ago": ["há 5 min", "há 20 min", "há 1 h", "há 3 h", "ontem"],
    },
}

_ICONS = {
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "list": '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>'
            '<line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    "chart": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "sliders": '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/>'
               '<line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
               '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "bell": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    "moon": '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    "menu": '<line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "user": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "briefcase": '<rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
    "trash": '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "up": '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    "down": '<polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "chevron": '<polyline points="6 9 12 15 18 9"/>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
}
_MODULE_ICONS = ("home", "list", "chart", "briefcase", "layers", "clock", "user", "sliders")
_CODE_HINTS = ("placa", "codigo", "code", "ref", "sku", "serial", "numero", "documento", "nit", "factura")
_PERSON_HINTS = ("nombre", "name", "cliente", "propietario", "paciente", "responsable", "contacto", "usuario", "tecnico",
                 "empleado", "proveedor")
_SAMPLE_NAMES = ("Ana Gómez", "Luis Pérez", "María Rojas", "Carlos Díaz", "Sofía Torres", "Andrés Ruiz",
                 "Valentina Castro", "Jorge Herrera", "Camila Vargas", "Diego Morales", "Laura Jiménez", "Felipe Ortiz")


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _icon(name: str, cls: str = "kx-ico") -> str:
    return f'<svg class="{cls}" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>'


def _sprite() -> str:
    symbols = "".join(f'<symbol id="i-{n}" viewBox="0 0 24 24">{p}</symbol>' for n, p in _ICONS.items())
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">{symbols}</svg>'


# ============================================================================ opciones


def _text(value: Any, default: str, limit: int, label: str) -> str:
    if value is None or value == "":
        return default
    if not isinstance(value, str) or len(value.strip()) > limit or not value.strip():
        raise DesignError(f"{label}: texto de 1 a {limit} caracteres")
    return value.strip()


def _texts(value: Any, default: List[str], limit: int, item_limit: int, label: str) -> List[str]:
    if not value:
        return list(default)
    if not isinstance(value, list) or len(value) > limit:
        raise DesignError(f"{label}: lista de máximo {limit} elementos")
    return [_text(v, "", item_limit, label) for v in value]


def _default_fields(t: Dict[str, Any]) -> List[Dict[str, Any]]:
    names = ("nombre", "correo", "telefono", "categoria", "fecha", "notas")
    kinds = ("text", "email", "tel", "select", "date", "textarea")
    return [{"nombre": n, "etiqueta": label, "tipo": k, "requerido": n in ("nombre", "correo"),
             "opciones": list(t["choices"]) if k == "select" else []}
            for n, label, k in zip(names, t["fields"], kinds)]


def _fields(raw: Any, t: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not raw:
        return _default_fields(t)
    if not isinstance(raw, list) or len(raw) > MAX_FIELDS:
        raise DesignError(f"campos: lista de máximo {MAX_FIELDS} elementos")
    fields, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise DesignError("campos: cada campo es un objeto {nombre, etiqueta, tipo, requerido, opciones}")
        name = str(item.get("nombre") or "")
        if not FIELD_NAME.match(name) or name in seen:
            raise DesignError(f"campo {name!r}: minúsculas, números o '_' (máx. 40) y sin repetir")
        kind = item.get("tipo", "text")
        if kind not in FIELD_TYPES:
            raise DesignError(f"campo {name}: tipo debe ser {', '.join(FIELD_TYPES)}")
        options = _texts(item.get("opciones"), list(t["choices"]) if kind == "select" else [], MAX_OPTIONS, 60,
                         f"opciones de {name}")
        seen.add(name)
        fields.append({"nombre": name, "etiqueta": _text(item.get("etiqueta"), name.replace("_", " ").capitalize(), 60,
                                                        f"etiqueta de {name}"),
                       "tipo": kind, "requerido": bool(item.get("requerido", False)), "opciones": options})
    return fields


def screen_options(raw: Optional[Dict[str, Any]], lang: str) -> Dict[str, Any]:
    if raw is not None and not isinstance(raw, dict):
        raise DesignError("opciones debe ser un objeto")
    raw = {k: v for k, v in (raw or {}).items() if v is not None}
    t = _TEXTS[lang]
    entity = _text(raw.get("entidad"), t["record"], 40, "entidad")
    plural = _text(raw.get("entidad_plural"), f"{entity}s" if raw.get("entidad") else t["records"], 40, "entidad_plural")
    fields = _fields(raw.get("campos"), t)
    names = [f["nombre"] for f in fields]
    columns = raw.get("columnas") or [f["nombre"] for f in fields if f["tipo"] not in ("textarea", "checkbox")][:4]
    if not isinstance(columns, list) or len(columns) > 8 or any(c not in names for c in columns):
        raise DesignError("columnas: hasta 8 nombres de campos existentes")
    modules = _texts(raw.get("modulos"), [t["dashboard"], plural, t["reports"], t["settings"]], MAX_MODULES, 30, "modulos")
    multi = raw.get("multiempresa", False)
    if not isinstance(multi, bool):
        raise DesignError("multiempresa debe ser true o false")
    return {
        "entidad": entity,
        "entidad_plural": plural,
        "campos": fields,
        "columnas": [next(f for f in fields if f["nombre"] == c) for c in columns],
        "modulos": modules,
        "multiempresa": multi,
        "empresas": _texts(raw.get("empresas"), t["companies"], MAX_COMPANIES, 60, "empresas"),
        "usuario": _text(raw.get("usuario"), t["user"], 60, "usuario"),
        "kpis": _texts(raw.get("kpis"), t["kpis"], MAX_KPIS, 40, "kpis"),
    }


# ============================================================================ estilos y scripts


def _styles() -> str:
    return """
*, *::before, *::after { box-sizing: border-box; }
[hidden] { display: none !important; }
html { color-scheme: light dark; }
html[data-theme=light] { color-scheme: light; }
html[data-theme=dark] { color-scheme: dark; }
body { margin: 0; font-family: var(--font-family); font-size: var(--font-size-base); line-height: var(--line-height-normal);
  color: var(--color-text); background: var(--color-background); -webkit-font-smoothing: antialiased; }
h1 { font-size: var(--font-size-2xl); line-height: var(--line-height-tight); margin: 0; }
h2 { font-size: var(--font-size-lg); line-height: var(--line-height-tight); margin: 0 0 var(--space-md); }
h3 { font-size: var(--font-size-base); margin: 0 0 var(--space-sm); }
p { margin: 0 0 var(--space-sm); }
a { color: var(--color-link); }
:focus-visible { outline: 3px solid var(--color-focus); outline-offset: 2px; border-radius: var(--radius-sm); }
.kx-ico { width: 20px; height: 20px; flex: none; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
.kx-skip { position: absolute; left: var(--space-sm); top: -100px; z-index: 100; padding: var(--space-sm) var(--space-md);
  background: var(--color-primary); color: var(--color-on-primary); border-radius: var(--radius-md); }
.kx-skip:focus { top: var(--space-sm); }
.kx-muted { color: var(--color-text-muted); }
.kx-btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-xs); min-height: 44px; min-width: 44px;
  padding: var(--space-sm) var(--space-md); font: inherit; font-weight: var(--font-weight-medium); text-decoration: none;
  border: 1px solid transparent; border-radius: var(--radius-md); cursor: pointer; background: var(--color-primary);
  color: var(--color-on-primary); transition: filter var(--duration-fast), background var(--duration-fast); }
.kx-btn:hover { filter: brightness(0.94); }
.kx-btn:disabled { opacity: 0.55; cursor: not-allowed; filter: none; }
.kx-btn--secondary { background: var(--color-surface); color: var(--color-text); border-color: var(--color-input-border); }
.kx-btn--ghost { background: transparent; color: var(--color-text); }
.kx-btn--ghost:hover { background: var(--color-surface); filter: none; }
.kx-btn--danger { background: var(--color-error); color: var(--color-on-error); }
.kx-btn--icon { padding: var(--space-sm); }
.kx-card { background: var(--color-background); border: 1px solid var(--color-border); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm); padding: var(--space-lg); }
.kx-badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px var(--space-sm); border-radius: var(--radius-full);
  font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); border: 1px solid var(--color-border); background: var(--color-surface); }
.kx-badge::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--color-text-muted); }
.kx-badge--active::before { background: var(--color-success); }
.kx-badge--pending::before { background: var(--color-warning); }
.kx-badge--inactive::before { background: var(--color-error); }
.kx-field { display: flex; flex-direction: column; gap: var(--space-xs); }
.kx-field label { font-weight: var(--font-weight-medium); }
.kx-field input:not([type=checkbox]), .kx-field select, .kx-field textarea, .kx-input {
  min-height: 44px; padding: var(--space-sm) var(--space-md); font: inherit; color: var(--color-text); background: var(--color-background);
  border: 1px solid var(--color-input-border); border-radius: var(--radius-md); width: 100%; }
.kx-field textarea { min-height: 112px; resize: vertical; }
.kx-field [aria-invalid=true] { border-color: var(--color-error); box-shadow: 0 0 0 1px var(--color-error); }
.kx-help { font-size: var(--font-size-sm); color: var(--color-text-muted); }
.kx-error { font-size: var(--font-size-sm); color: var(--color-error-text); min-height: 1em; }
.kx-check { display: flex; align-items: center; gap: var(--space-sm); min-height: 44px; }
.kx-check input { width: 20px; height: 20px; accent-color: var(--color-primary); }
.kx-switch { appearance: none; width: 44px !important; height: 24px !important; border-radius: var(--radius-full); background: var(--color-input-border);
  position: relative; cursor: pointer; transition: background var(--duration-fast); flex: none; }
.kx-switch::after { content: ""; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%;
  background: var(--color-background); transition: transform var(--duration-fast); }
.kx-switch:checked { background: var(--color-primary); }
.kx-switch:checked::after { transform: translateX(20px); }
/* shell */
.kx-shell { display: grid; grid-template-columns: 264px minmax(0, 1fr); min-height: 100vh; }
.kx-shell.is-collapsed { grid-template-columns: 76px minmax(0, 1fr); }
.kx-sidebar { position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; gap: var(--space-md);
  padding: var(--space-md) var(--space-sm); background: var(--color-surface); border-right: 1px solid var(--color-border); overflow-y: auto; }
.kx-brand { display: flex; align-items: center; gap: var(--space-sm); padding: var(--space-xs) var(--space-sm); font-weight: var(--font-weight-bold);
  font-size: var(--font-size-lg); color: var(--color-text); text-decoration: none; }
.kx-logo { display: grid; place-items: center; width: 36px; height: 36px; flex: none; border-radius: var(--radius-md);
  background: var(--color-primary); color: var(--color-on-primary); font-size: var(--font-size-base); }
.kx-nav ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.kx-nav a { display: flex; align-items: center; gap: var(--space-sm); min-height: 44px; padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md); color: var(--color-text); text-decoration: none; }
.kx-nav a:hover { background: var(--color-background); }
.kx-nav a[aria-current=page] { background: var(--color-primary); color: var(--color-on-primary); font-weight: var(--font-weight-medium); }
.kx-sidebar-foot { margin-top: auto; }
.is-collapsed .kx-label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.is-collapsed .kx-nav a, .is-collapsed .kx-brand { justify-content: center; padding-inline: 0; }
.kx-main { display: flex; flex-direction: column; min-width: 0; }
.kx-topbar { position: sticky; top: 0; z-index: 30; display: flex; align-items: center; gap: var(--space-sm); min-height: 64px;
  padding: var(--space-sm) var(--space-lg); background: var(--color-background); border-bottom: 1px solid var(--color-border); }
.kx-search { position: relative; flex: 1; max-width: 480px; }
.kx-search .kx-ico { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--color-text-muted); pointer-events: none; }
.kx-search input { padding-left: 40px; }
.kx-top-actions { margin-left: auto; display: flex; align-items: center; gap: var(--space-xs); }
.kx-company { display: flex; align-items: center; gap: var(--space-xs); }
.kx-company select { min-height: 44px; max-width: 220px; }
.kx-dot { position: absolute; top: 6px; right: 6px; min-width: 18px; height: 18px; padding: 0 4px; border-radius: var(--radius-full);
  background: var(--color-error); color: var(--color-on-error); font-size: 11px; line-height: 18px; text-align: center; }
.kx-menu-wrap { position: relative; }
.kx-menu { position: absolute; right: 0; top: calc(100% + 6px); min-width: 240px; z-index: 50; margin: 0; padding: var(--space-xs);
  list-style: none; background: var(--color-background); border: 1px solid var(--color-border); border-radius: var(--radius-md); box-shadow: var(--shadow-lg); }
.kx-menu a, .kx-menu button { display: flex; align-items: center; gap: var(--space-sm); width: 100%; min-height: 44px; padding: var(--space-sm) var(--space-md);
  border: 0; border-radius: var(--radius-sm); background: none; font: inherit; color: var(--color-text); text-decoration: none; text-align: left; cursor: pointer; }
.kx-menu a:hover, .kx-menu button:hover { background: var(--color-surface); }
.kx-menu small { display: block; color: var(--color-text-muted); }
.kx-avatar { display: inline-grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; background: var(--color-secondary);
  color: var(--color-on-secondary); font-weight: var(--font-weight-bold); font-size: var(--font-size-sm); }
.kx-content { padding: var(--space-lg); display: flex; flex-direction: column; gap: var(--space-lg); max-width: 1440px; width: 100%; margin-inline: auto; }
.kx-content > * { min-width: 0; }
.kx-crumbs ol { display: flex; flex-wrap: wrap; gap: var(--space-xs); list-style: none; margin: 0; padding: 0; font-size: var(--font-size-sm); }
.kx-crumbs li + li::before { content: "/"; margin-right: var(--space-xs); color: var(--color-text-muted); }
.kx-crumbs a { color: var(--color-text-muted); }
.kx-crumbs [aria-current] { color: var(--color-text); font-weight: var(--font-weight-medium); }
.kx-pagehead { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-md); }
.kx-pagehead p { margin: var(--space-xs) 0 0; }
.kx-toolbar { display: flex; flex-wrap: wrap; gap: var(--space-sm); align-items: center; }
@media (max-width: 1023px) {
  .kx-shell, .kx-shell.is-collapsed { grid-template-columns: minmax(0, 1fr); }
  .kx-sidebar { position: fixed; inset: 0 auto 0 0; width: 280px; z-index: 60; transform: translateX(-100%); visibility: hidden;
    transition: transform var(--duration-normal), visibility var(--duration-normal); box-shadow: var(--shadow-lg); }
  .kx-shell.is-open .kx-sidebar { transform: none; visibility: visible; }
  .kx-shell.is-open::after { content: ""; position: fixed; inset: 0; z-index: 55; background: rgba(0, 0, 0, 0.4); }
  .is-collapsed .kx-label { position: static; width: auto; height: auto; clip: auto; }
  .kx-company select { max-width: 140px; }
}
@media (max-width: 767px) {
  .kx-topbar, .kx-content { padding-inline: var(--space-sm); }
  .kx-topbar { gap: 2px; }
  .kx-search, .kx-company .kx-ico, .kx-user-chevron { display: none; }
  .kx-company select { max-width: 120px; }
  .kx-filters .kx-field, .kx-filters .kx-grow { min-width: 0; flex: 1 1 100%; }
  .kx-actionbar .kx-muted { display: none; }
}
/* tablero */
.kx-kpis { display: grid; gap: var(--space-md); grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.kx-kpi h2 { font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); color: var(--color-text-muted); margin: 0; }
.kx-kpi-value { font-size: var(--font-size-3xl); font-weight: var(--font-weight-bold); line-height: var(--line-height-tight); margin: var(--space-sm) 0; }
.kx-trend { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); }
.kx-delta { white-space: nowrap; }
.kx-trend--up { color: var(--color-success); }
.kx-trend--down { color: var(--color-error-text); }
.kx-grid-2 { display: grid; gap: var(--space-md); grid-template-columns: minmax(0, 1fr); }
@media (min-width: 1024px) { .kx-grid-2 { grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); } }
.kx-chart { width: 100%; height: auto; display: block; }
.kx-chart .grid { stroke: var(--color-border); stroke-width: 1; }
.kx-chart .line { fill: none; stroke: var(--color-primary); stroke-width: 3; stroke-linejoin: round; stroke-linecap: round; }
.kx-chart .area { fill: var(--color-primary); opacity: 0.12; }
.kx-chart .dot { fill: var(--color-background); stroke: var(--color-primary); stroke-width: 2; }
.kx-chart text { fill: var(--color-text-muted); font-size: 12px; }
.kx-feed { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-md); }
.kx-feed li { display: flex; gap: var(--space-sm); align-items: flex-start; }
.kx-feed time { display: block; font-size: var(--font-size-sm); color: var(--color-text-muted); }
.kx-quick { display: grid; gap: var(--space-sm); grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.kx-head-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-sm); margin-bottom: var(--space-md); }
.kx-head-row h2 { margin: 0; }
/* tabla */
.kx-table-card { padding: 0; overflow: hidden; }
.kx-filters { display: flex; flex-wrap: wrap; gap: var(--space-sm); align-items: flex-end; padding: var(--space-md); border-bottom: 1px solid var(--color-border); }
.kx-filters .kx-field { min-width: 180px; }
.kx-filters .kx-grow { flex: 1; min-width: 220px; }
.kx-bulk { display: flex; align-items: center; gap: var(--space-sm); padding: var(--space-sm) var(--space-md);
  background: var(--color-surface); border-bottom: 1px solid var(--color-border); }
.kx-table-wrap { overflow-x: auto; }
.kx-table { width: 100%; border-collapse: collapse; }
.kx-table th, .kx-table td { text-align: left; padding: var(--space-md); border-bottom: 1px solid var(--color-border); white-space: nowrap; }
.kx-table.is-compact th, .kx-table.is-compact td { padding: var(--space-xs) var(--space-md); }
.kx-table thead th { position: sticky; top: 0; background: var(--color-surface); font-size: var(--font-size-sm); color: var(--color-text-muted); font-weight: var(--font-weight-medium); }
.kx-table tbody tr:hover { background: var(--color-surface); }
.kx-table .kx-col-check { width: 48px; }
.kx-sort { display: inline-flex; align-items: center; gap: 4px; min-height: 32px; padding: 0; border: 0; background: none; font: inherit; color: inherit; cursor: pointer; }
.kx-sort .kx-ico { width: 16px; height: 16px; opacity: 0.4; transition: transform var(--duration-fast); }
th[aria-sort=ascending] .kx-sort .kx-ico { opacity: 1; transform: rotate(180deg); }
th[aria-sort=descending] .kx-sort .kx-ico { opacity: 1; }
.kx-row-actions { display: flex; gap: 2px; }
.kx-pager { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-sm); padding: var(--space-sm) var(--space-md); }
.kx-pager .kx-field { flex-direction: row; align-items: center; gap: var(--space-sm); }
.kx-pager select { width: auto; }
.kx-empty { text-align: center; padding: var(--space-2xl) var(--space-md); }
.kx-empty .kx-ico { width: 48px; height: 48px; color: var(--color-text-muted); }
/* formularios */
.kx-form { display: flex; flex-direction: column; gap: var(--space-lg); padding-bottom: 96px; }
.kx-form fieldset { border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-lg); margin: 0; background: var(--color-background); }
.kx-form legend { padding: 0 var(--space-xs); font-weight: var(--font-weight-bold); font-size: var(--font-size-lg); }
.kx-form-grid { display: grid; gap: var(--space-md); grid-template-columns: minmax(0, 1fr); }
@media (min-width: 768px) { .kx-form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .kx-span-2 { grid-column: 1 / -1; } }
.kx-req { color: var(--color-error-text); }
.kx-actionbar { position: fixed; bottom: 0; right: 0; left: 0; z-index: 20; display: flex; justify-content: flex-end; gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg); background: var(--color-background); border-top: 1px solid var(--color-border); box-shadow: var(--shadow-md); }
.kx-actionbar .kx-muted { margin-right: auto; align-self: center; }
@media (min-width: 1024px) { .kx-shell .kx-actionbar { left: 264px; } .kx-shell.is-collapsed .kx-actionbar { left: 76px; } }
/* detalle y configuración */
.kx-dl { display: grid; gap: var(--space-md); grid-template-columns: minmax(0, 1fr); margin: 0; }
@media (min-width: 768px) { .kx-dl { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.kx-dl dt { font-size: var(--font-size-sm); color: var(--color-text-muted); }
.kx-dl dd { margin: 2px 0 0; font-weight: var(--font-weight-medium); word-break: break-word; }
.kx-tabs { display: flex; gap: var(--space-xs); border-bottom: 1px solid var(--color-border); overflow-x: auto; }
.kx-tab { min-height: 44px; padding: var(--space-sm) var(--space-md); border: 0; border-bottom: 3px solid transparent; background: none;
  font: inherit; color: var(--color-text-muted); cursor: pointer; white-space: nowrap; }
.kx-tab[aria-selected=true] { color: var(--color-text); border-bottom-color: var(--color-primary); font-weight: var(--font-weight-medium); }
.kx-panel { padding-top: var(--space-lg); }
.kx-timeline { list-style: none; margin: 0; padding: 0 0 0 var(--space-lg); border-left: 2px solid var(--color-border); display: flex; flex-direction: column; gap: var(--space-lg); }
.kx-timeline li { position: relative; }
.kx-timeline li::before { content: ""; position: absolute; left: calc(-1 * var(--space-lg) - 7px); top: 6px; width: 12px; height: 12px;
  border-radius: 50%; background: var(--color-primary); border: 2px solid var(--color-background); }
.kx-setting { display: flex; align-items: center; justify-content: space-between; gap: var(--space-md); padding: var(--space-md) 0; border-bottom: 1px solid var(--color-border); }
.kx-setting:last-child { border-bottom: 0; }
/* login */
.kx-auth { display: grid; min-height: 100vh; grid-template-columns: minmax(0, 1fr); }
@media (min-width: 1024px) { .kx-auth { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } }
.kx-hero { display: none; flex-direction: column; justify-content: space-between; padding: var(--space-3xl);
  background: linear-gradient(140deg, var(--color-primary), var(--color-secondary)); color: var(--color-on-primary); }
@media (min-width: 1024px) { .kx-hero { display: flex; } }
.kx-hero h2 { font-size: var(--font-size-3xl); max-width: 22ch; margin: 0 0 var(--space-lg); }
.kx-hero ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--space-sm); }
.kx-hero li { display: flex; gap: var(--space-sm); align-items: center; }
.kx-hero .kx-logo { background: var(--color-on-primary); color: var(--color-primary); }
.kx-auth-main { display: grid; place-items: center; padding: var(--space-xl) var(--space-md); }
.kx-auth-card { width: 100%; max-width: 420px; display: flex; flex-direction: column; gap: var(--space-md); }
.kx-password { position: relative; }
.kx-password input { padding-right: 52px; }
.kx-password button { position: absolute; right: 0; top: 0; }
.kx-row-between { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-sm); }
/* diálogos y avisos */
dialog.kx-dialog { border: 0; border-radius: var(--radius-lg); padding: var(--space-lg); max-width: 440px; width: calc(100% - 32px);
  background: var(--color-background); color: var(--color-text); box-shadow: var(--shadow-lg); }
dialog.kx-dialog::backdrop { background: rgba(0, 0, 0, 0.45); }
.kx-dialog-actions { display: flex; justify-content: flex-end; gap: var(--space-sm); margin-top: var(--space-lg); }
.kx-toasts { position: fixed; right: var(--space-md); bottom: var(--space-md); z-index: 90; display: flex; flex-direction: column; gap: var(--space-sm); }
.kx-toast { display: flex; align-items: center; gap: var(--space-sm); min-width: 260px; padding: var(--space-md); border-radius: var(--radius-md);
  background: var(--color-text); color: var(--color-background); box-shadow: var(--shadow-lg); animation: kx-in var(--duration-normal) ease-out; }
@keyframes kx-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; } }
@media print { .kx-sidebar, .kx-topbar, .kx-actionbar, .kx-toolbar, .kx-filters, .kx-pager { display: none !important; } .kx-shell { display: block; } }
"""


_SCRIPT = r"""
(function () {
  var root = document.documentElement, T = JSON.parse(document.getElementById('kx-i18n').textContent);
  function $(s, c) { return (c || document).querySelector(s); }
  function $$(s, c) { return [].slice.call((c || document).querySelectorAll(s)); }
  try { var saved = localStorage.getItem('kx-theme'); if (saved) root.setAttribute('data-theme', saved); } catch (e) {}
  function isDark() { var t = root.getAttribute('data-theme'); return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; }
  $$('[data-kx-theme]').forEach(function (b) {
    b.setAttribute('aria-pressed', String(isDark()));
    b.addEventListener('click', function () {
      var next = isDark() ? 'light' : 'dark'; root.setAttribute('data-theme', next);
      $$('[data-kx-theme]').forEach(function (x) { x.setAttribute('aria-pressed', String(next === 'dark')); });
      try { localStorage.setItem('kx-theme', next); } catch (e) {}
    });
  });
  var shell = $('.kx-shell'), mobile = matchMedia('(max-width: 1023px)');
  function syncMenu() { $$('[data-kx-sidebar]').forEach(function (b) {
    b.setAttribute('aria-expanded', String(mobile.matches ? shell.classList.contains('is-open') : !shell.classList.contains('is-collapsed'))); }); }
  if (shell) {
    $$('[data-kx-sidebar]').forEach(function (b) { b.addEventListener('click', function () {
      shell.classList.toggle(mobile.matches ? 'is-open' : 'is-collapsed'); syncMenu(); }); });
    shell.addEventListener('click', function (e) { if (mobile.matches && e.target === shell) { shell.classList.remove('is-open'); syncMenu(); } });
    (mobile.addEventListener ? mobile.addEventListener('change', syncMenu) : mobile.addListener(syncMenu)); syncMenu();
  }
  function closeMenus(except) { $$('[data-kx-menu][aria-expanded="true"]').forEach(function (b) {
    if (b !== except) { b.setAttribute('aria-expanded', 'false'); document.getElementById(b.getAttribute('aria-controls')).hidden = true; } }); }
  $$('[data-kx-menu]').forEach(function (b) { b.addEventListener('click', function (e) {
    e.stopPropagation(); var menu = document.getElementById(b.getAttribute('aria-controls')), open = b.getAttribute('aria-expanded') !== 'true';
    closeMenus(b); b.setAttribute('aria-expanded', String(open)); menu.hidden = !open;
    if (open) { var first = $('a,button', menu); if (first) first.focus(); } }); });
  document.addEventListener('click', function () { closeMenus(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { var open = $('[data-kx-menu][aria-expanded="true"]'); closeMenus(); if (open) open.focus();
      if (shell && shell.classList.contains('is-open')) { shell.classList.remove('is-open'); syncMenu(); } }
    if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { var s = $('#kx-global-search'); if (s) { e.preventDefault(); s.focus(); } }
  });
  window.kxToast = function (message) { var box = $('#kx-toasts'); if (!box) return; var t = document.createElement('div');
    t.className = 'kx-toast'; t.setAttribute('role', 'status'); t.textContent = message; box.appendChild(t); setTimeout(function () { t.remove(); }, 5000); };
  $$('[data-kx-reveal]').forEach(function (b) { b.addEventListener('click', function () {
    var input = document.getElementById(b.getAttribute('data-kx-reveal')), show = input.type === 'password';
    input.type = show ? 'text' : 'password'; b.setAttribute('aria-pressed', String(show)); }); });
  $$('[role="tablist"]').forEach(function (list) { var tabs = $$('[role="tab"]', list);
    function select(tab) { tabs.forEach(function (t) { var on = t === tab; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')).hidden = !on; }); tab.focus(); }
    tabs.forEach(function (t, i) { t.addEventListener('click', function () { select(t); });
      t.addEventListener('keydown', function (e) { var d = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        if (e.key === 'Home') d = -i; if (e.key === 'End') d = tabs.length - 1 - i;
        if (d !== undefined) { e.preventDefault(); select(tabs[(i + d + tabs.length) % tabs.length]); } }); }); });
  $$('[data-kx-confirm]').forEach(function (b) { b.addEventListener('click', function () {
    var dlg = document.getElementById(b.getAttribute('data-kx-confirm')); if (dlg && dlg.showModal) dlg.showModal(); }); });
  $$('form[data-kx-validate]').forEach(function (form) { var dirty = false;
    function check(el) { var err = document.getElementById(el.id + '-err'); if (!err) return true; var msg = '';
      if (el.required && !(el.type === 'checkbox' ? el.checked : el.value.trim())) msg = T.required_error;
      else if (el.type === 'email' && el.value && !el.checkValidity()) msg = T.email_error;
      err.textContent = msg; if (msg) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid'); return !msg; }
    form.addEventListener('input', function (e) { dirty = true; if (e.target.getAttribute('aria-invalid')) check(e.target); });
    $$('input,select,textarea', form).forEach(function (el) { el.addEventListener('blur', function () { if (el.value) check(el); }); });
    form.addEventListener('submit', function (e) { var first = null;
      $$('input,select,textarea', form).forEach(function (el) { if (!check(el) && !first) first = el; });
      if (first) { e.preventDefault(); first.focus(); return; }
      if (form.getAttribute('data-kx-validate') !== 'native') { e.preventDefault(); dirty = false; kxToast(T.saved); } });
    var cancel = $('[data-kx-cancel]', form), dlg = $('#kx-discard');
    if (cancel && dlg) { cancel.addEventListener('click', function () { if (dirty && dlg.showModal) dlg.showModal(); });
      dlg.addEventListener('close', function () { if (dlg.returnValue !== 'discard') return; form.reset(); dirty = false;
        $$('[aria-invalid]', form).forEach(function (el) { el.removeAttribute('aria-invalid'); });
        $$('.kx-error', form).forEach(function (x) { x.textContent = ''; }); }); }
    window.addEventListener('beforeunload', function (e) { if (dirty) { e.preventDefault(); e.returnValue = ''; } }); });
  $$('[data-kx-table]').forEach(function (wrap) {
    var table = $('table', wrap), tbody = table.tBodies[0], rows = $$('tr', tbody), page = 1, sortCol = -1, asc = true;
    var q = $('#kx-q'), status = $('#kx-status'), size = $('#kx-size'), all = $('#kx-all'), bulk = $('#kx-bulk');
    function visible() { return rows.filter(function (r) { return !r.hidden; }); }
    function filtered() { var term = (q && q.value || '').trim().toLowerCase(), st = status && status.value || '';
      return rows.filter(function (r) { return (!term || r.textContent.toLowerCase().indexOf(term) >= 0) && (!st || r.getAttribute('data-status') === st); }); }
    function key(r) { var c = r.cells[sortCol]; return c.getAttribute('data-sort') || c.textContent.trim(); }
    function render() { var list = filtered(), n = +(size ? size.value : 10), pages = Math.max(1, Math.ceil(list.length / n));
      if (sortCol >= 0) { list.sort(function (a, b) { var x = key(a), y = key(b), nx = parseFloat(x), ny = parseFloat(y);
        return (isNaN(nx) || isNaN(ny) ? x.localeCompare(y) : nx - ny) * (asc ? 1 : -1); }); list.forEach(function (r) { tbody.appendChild(r); }); }
      page = Math.min(page, pages); rows.forEach(function (r) { r.hidden = true; });
      list.slice((page - 1) * n, page * n).forEach(function (r) { r.hidden = false; });
      $('#kx-page-info').textContent = T.page + ' ' + page + ' ' + T.of + ' ' + pages + ' · ' + list.length + ' ' + T.results;
      $('[data-kx-prev]', wrap).disabled = page <= 1; $('[data-kx-next]', wrap).disabled = page >= pages;
      $('#kx-empty').hidden = list.length > 0; table.hidden = list.length === 0; selection(); }
    function selection() { var checked = rows.filter(function (r) { return $('.kx-row-check', r).checked; });
      bulk.hidden = checked.length === 0; $('#kx-count').textContent = checked.length + ' ' + T.selected;
      var vis = visible(); all.checked = vis.length > 0 && vis.every(function (r) { return $('.kx-row-check', r).checked; });
      all.indeterminate = !all.checked && vis.some(function (r) { return $('.kx-row-check', r).checked; }); }
    [q, status].forEach(function (el) { if (el) el.addEventListener('input', function () { page = 1; render(); }); });
    if (size) size.addEventListener('change', function () { page = 1; render(); });
    $('[data-kx-prev]', wrap).addEventListener('click', function () { page--; render(); });
    $('[data-kx-next]', wrap).addEventListener('click', function () { page++; render(); });
    $$('[data-kx-sort]', table).forEach(function (b) { b.addEventListener('click', function () {
      var col = +b.getAttribute('data-kx-sort'); asc = sortCol === col ? !asc : true; sortCol = col;
      $$('th[aria-sort]', table).forEach(function (th) { th.setAttribute('aria-sort', 'none'); });
      b.parentNode.setAttribute('aria-sort', asc ? 'ascending' : 'descending'); render(); }); });
    all.addEventListener('change', function () { visible().forEach(function (r) { $('.kx-row-check', r).checked = all.checked; }); selection(); });
    tbody.addEventListener('change', function (e) { if (e.target.classList.contains('kx-row-check')) selection(); });
    $$('[data-kx-clear]').forEach(function (b) { b.addEventListener('click', function () { if (q) q.value = ''; if (status) status.value = ''; page = 1; render(); }); });
    var del = $('#kx-delete'); if (del) del.addEventListener('close', function () { if (del.returnValue !== 'delete') return;
      rows = rows.filter(function (r) { if ($('.kx-row-check', r).checked) { r.remove(); return false; } return true; }); render(); kxToast(T.deleted); });
    var density = $('[data-kx-density]'); if (density) density.addEventListener('click', function () {
      density.setAttribute('aria-pressed', String(table.classList.toggle('is-compact'))); });
    var exp = $('[data-kx-export]'); if (exp) exp.addEventListener('click', function () {
      function cell(v) { v = v.trim(); if (/^[=+\-@]/.test(v)) v = "'" + v; return '"' + v.replace(/"/g, '""') + '"'; }
      var heads = $$('thead th[data-kx-col]', table).map(function (th) { return cell(th.textContent); }), idx = $$('thead th', table).map(function (th, i) { return th.hasAttribute('data-kx-col') ? i : -1; }).filter(function (i) { return i >= 0; });
      var lines = [heads.join(',')].concat(filtered().map(function (r) { return idx.map(function (i) { return cell(r.cells[i].textContent); }).join(','); }));
      var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
      a.download = exp.getAttribute('data-kx-export') + '.csv'; document.body.appendChild(a); a.click(); a.remove(); });
    render(); });
})();
"""


# ============================================================================ piezas compartidas


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name) if p]
    return "".join(p[0] for p in parts[:2]).upper() or "U"


def _dialog(dialog_id: str, title: str, text: str, confirm: str, cancel: str, value: str, danger: bool = True) -> str:
    return (
        f'<dialog class="kx-dialog" id="{dialog_id}" aria-labelledby="{dialog_id}-t" aria-describedby="{dialog_id}-d">'
        f'<form method="dialog"><h2 id="{dialog_id}-t">{_esc(title)}</h2><p id="{dialog_id}-d" class="kx-muted">{_esc(text)}</p>'
        f'<div class="kx-dialog-actions"><button class="kx-btn kx-btn--secondary" value="cancel" autofocus>{_esc(cancel)}</button>'
        f'<button class="kx-btn{" kx-btn--danger" if danger else ""}" value="{value}">{_esc(confirm)}</button></div></form></dialog>'
    )


def _crumbs(t: Dict[str, Any], trail: List[str]) -> str:
    items = [f'<li><a href="#">{_esc(t["home"])}</a></li>']
    items += [f'<li><a href="#">{_esc(x)}</a></li>' for x in trail[:-1]]
    items.append(f'<li><span aria-current="page">{_esc(trail[-1])}</span></li>')
    return f'<nav class="kx-crumbs" aria-label="Breadcrumb"><ol>{"".join(items)}</ol></nav>'


def _pagehead(title: str, subtitle: str, actions: str = "") -> str:
    sub = f'<p class="kx-muted">{_esc(subtitle)}</p>' if subtitle else ""
    return f'<div class="kx-pagehead"><div><h1>{_esc(title)}</h1>{sub}</div><div class="kx-toolbar">{actions}</div></div>'


def _shell(t: Dict[str, Any], app: str, opts: Dict[str, Any], active: int, content: str) -> str:
    current = ' aria-current="page"'
    nav = "".join(
        f'<li><a href="#"{current if i == active else ""}>{_icon(_MODULE_ICONS[i % len(_MODULE_ICONS)])}'
        f'<span class="kx-label">{_esc(m)}</span></a></li>'
        for i, m in enumerate(opts["modulos"])
    )
    company = ""
    if opts["multiempresa"]:
        options = "".join(f"<option>{_esc(c)}</option>" for c in opts["empresas"])
        company = (f'<div class="kx-company">{_icon("briefcase")}<label class="sr-only" for="kx-company">{_esc(t["company"])}</label>'
                   f'<select id="kx-company" class="kx-input">{options}</select></div>')
    notes = "".join(f'<li role="none"><a role="menuitem" href="#">{_icon("bell")}<span>{_esc(_SAMPLE_NAMES[i])} {_esc(t["events"][i])}'
                    f'<small>{_esc(t["ago"][i])}</small></span></a></li>' for i in range(3))
    user = _esc(opts["usuario"])
    return (
        '<div class="kx-shell">'
        f'<aside class="kx-sidebar" id="kx-sidebar"><a class="kx-brand" href="#"><span class="kx-logo" aria-hidden="true">{_esc(_initials(app))}</span>'
        f'<span class="kx-label">{_esc(app)}</span></a>'
        f'<nav class="kx-nav" aria-label="{_esc(t["menu"])}"><ul>{nav}</ul></nav>'
        f'<div class="kx-sidebar-foot kx-nav"><ul><li><a href="#">{_icon("logout")}<span class="kx-label">{_esc(t["logout"])}</span></a></li></ul></div></aside>'
        '<div class="kx-main"><header class="kx-topbar">'
        f'<button class="kx-btn kx-btn--ghost kx-btn--icon" type="button" data-kx-sidebar aria-controls="kx-sidebar" aria-label="{_esc(t["toggle_menu"])}">{_icon("menu")}</button>'
        f'<form class="kx-search" role="search" onsubmit="return false"><label class="sr-only" for="kx-global-search">{_esc(t["search"])}</label>{_icon("search")}'
        f'<input id="kx-global-search" class="kx-input" type="search" placeholder="{_esc(t["search_hint"])}" autocomplete="off"></form>'
        f'<div class="kx-top-actions">{company}'
        f'<button class="kx-btn kx-btn--ghost kx-btn--icon" type="button" data-kx-theme aria-label="{_esc(t["theme"])}">{_icon("moon")}</button>'
        f'<div class="kx-menu-wrap"><button class="kx-btn kx-btn--ghost kx-btn--icon" type="button" data-kx-menu aria-haspopup="menu" aria-expanded="false" '
        f'aria-controls="kx-notes" aria-label="{_esc(t["notifications"])}: 3 {_esc(t["new_notifications"])}">{_icon("bell")}<span class="kx-dot" aria-hidden="true">3</span></button>'
        f'<ul class="kx-menu" id="kx-notes" role="menu" hidden>{notes}</ul></div>'
        f'<div class="kx-menu-wrap"><button class="kx-btn kx-btn--ghost" type="button" data-kx-menu aria-haspopup="menu" aria-expanded="false" '
        f'aria-controls="kx-user" aria-label="{_esc(t["user_menu"])}: {user}"><span class="kx-avatar" aria-hidden="true">{_esc(_initials(opts["usuario"]))}</span>{_icon("chevron", "kx-ico kx-user-chevron")}</button>'
        f'<ul class="kx-menu" id="kx-user" role="menu" hidden>'
        f'<li role="none"><a role="menuitem" href="#">{_icon("user")}<span>{user}<small>{_esc(t["profile"])}</small></span></a></li>'
        f'<li role="none"><a role="menuitem" href="#">{_icon("sliders")}{_esc(t["settings"])}</a></li>'
        f'<li role="none"><a role="menuitem" href="#">{_icon("logout")}{_esc(t["logout"])}</a></li></ul></div>'
        '</div></header>'
        f'<main id="contenido" class="kx-content" tabindex="-1">{content}</main></div></div>'
    )


def _document(t: Dict[str, Any], lang: str, title: str, app: str, css: str, body: str) -> str:
    i18n = json.dumps({k: v for k, v in t.items() if isinstance(v, str)}, ensure_ascii=False).replace("<", "\\u003c")
    return (
        f'<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f"<title>{_esc(title)} · {_esc(app)}</title>\n<style>\n{css}{_styles()}</style>\n</head>\n<body>\n"
        f'<a class="kx-skip" href="#contenido">{_esc(t["skip"])}</a>\n{_sprite()}\n{body}\n'
        '<div class="kx-toasts" id="kx-toasts" aria-live="polite"></div>\n'
        f'<script type="application/json" id="kx-i18n">{i18n}</script>\n<script>{_SCRIPT}</script>\n</body>\n</html>\n'
    )


def _sample(field: Dict[str, Any], i: int, t: Dict[str, Any]) -> Tuple[str, str]:
    """(texto visible, clave de orden) de un valor de ejemplo determinista."""
    kind = field["tipo"]
    name = _SAMPLE_NAMES[i % len(_SAMPLE_NAMES)]
    if kind == "email":
        user = re.sub(r"[^a-z]", "", name.split()[0].lower().translate(str.maketrans("áéíóú", "aeiou")))
        return f"{user}{i + 1}@ejemplo.com", ""
    if kind == "tel":
        return f"+57 300 {100 + i * 7:03d} {1000 + i * 37:04d}", ""
    if kind == "date":
        value = f"2026-{(i % 12) + 1:02d}-{(i * 3) % 27 + 1:02d}"
        return value, value
    if kind == "number":
        value = (i * 137 + 50) % 1000
        return str(value), str(value)
    if kind == "select":
        return (field["opciones"] or ["—"])[i % max(len(field["opciones"]), 1)], ""
    if kind == "checkbox":
        return (t["yes"] if i % 2 == 0 else t["no"]), ""
    if kind == "textarea":
        return "—", ""
    key = field["nombre"]
    if key.startswith("id_") or any(h in key for h in _CODE_HINTS):
        letters = "".join(chr(65 + (i * step + offset) % 26) for step, offset in ((1, 10), (7, 3), (3, 17)))
        return f"{letters}-{(100 + i * 37) % 900 + 100}", ""
    if any(h in key for h in _PERSON_HINTS):
        return (name if i < len(_SAMPLE_NAMES) else f"{name} {i // len(_SAMPLE_NAMES) + 1}"), ""
    return f'{field["etiqueta"]} {i + 1}', f"{i + 1:05d}"


_STATUSES = ("active", "pending", "inactive")


def _status_badge(t: Dict[str, Any], i: int) -> Tuple[str, str]:
    status = _STATUSES[0] if i % 5 < 3 else _STATUSES[1 + i % 2]
    return status, f'<span class="kx-badge kx-badge--{status}">{_esc(t[status])}</span>'


def _input(field: Dict[str, Any], t: Dict[str, Any], value: str = "") -> str:
    fid, name, label = f"f-{field['nombre']}", field["nombre"], _esc(field["etiqueta"])
    required = field["requerido"]
    req_attr = ' required aria-required="true"' if required else ""
    star = ' <span class="kx-req" aria-hidden="true">*</span>' if required else ""
    described = f'aria-describedby="{fid}-err"'
    kind = field["tipo"]
    if kind == "checkbox":
        return (f'<div class="kx-field"><div class="kx-check"><input id="{fid}" name="{name}" type="checkbox"{req_attr} {described}>'
                f'<label for="{fid}">{label}{star}</label></div><span id="{fid}-err" class="kx-error"></span></div>')
    if kind == "select":
        options = "".join(f'<option{" selected" if o == value else ""}>{_esc(o)}</option>' for o in field["opciones"])
        control = f'<select id="{fid}" name="{name}"{req_attr} {described}><option value="">—</option>{options}</select>'
    elif kind == "textarea":
        control = f'<textarea id="{fid}" name="{name}"{req_attr} {described}>{_esc(value)}</textarea>'
    else:
        auto = {"email": ' autocomplete="email"', "tel": ' autocomplete="tel"'}.get(kind, "")
        control = f'<input id="{fid}" name="{name}" type="{kind}" value="{_esc(value)}"{auto}{req_attr} {described}>'
    span = " kx-span-2" if kind == "textarea" else ""
    return (f'<div class="kx-field{span}"><label for="{fid}">{label}{star}</label>{control}'
            f'<span id="{fid}-err" class="kx-error" aria-live="polite"></span></div>')


# ============================================================================ pantallas


def _login(t, app, opts):
    features = "".join(f"<li>{_icon('check')}<span>{_esc(f)}</span></li>" for f in t["features"])
    body = (
        '<div class="kx-auth">'
        f'<section class="kx-hero" aria-hidden="true"><div class="kx-brand" style="color:inherit"><span class="kx-logo">{_esc(_initials(app))}</span>{_esc(app)}</div>'
        f'<div><h2>{_esc(t["hero"])}</h2><ul>{features}</ul></div><p>© 2026 {_esc(app)}</p></section>'
        '<main id="contenido" class="kx-auth-main" tabindex="-1"><div class="kx-auth-card">'
        f'<div class="kx-brand"><span class="kx-logo" aria-hidden="true">{_esc(_initials(app))}</span>{_esc(app)}</div>'
        f'<div><h1>{_esc(t["login_title"])}</h1><p class="kx-muted">{_esc(t["login_sub"])}</p></div>'
        '<form method="post" novalidate data-kx-validate="native" class="kx-auth-card">'
        f'<div class="kx-field"><label for="f-usuario">{_esc(t["username"])}</label>'
        '<input id="f-usuario" name="usuario" autocomplete="username" required aria-required="true" aria-describedby="f-usuario-err" autofocus>'
        '<span id="f-usuario-err" class="kx-error" aria-live="polite"></span></div>'
        f'<div class="kx-field"><label for="f-contrasena">{_esc(t["password"])}</label><div class="kx-password">'
        '<input id="f-contrasena" name="contrasena" type="password" autocomplete="current-password" required aria-required="true" aria-describedby="f-contrasena-err">'
        f'<button class="kx-btn kx-btn--ghost kx-btn--icon" type="button" data-kx-reveal="f-contrasena" aria-pressed="false" aria-label="{_esc(t["show_password"])}">{_icon("eye")}</button>'
        '</div><span id="f-contrasena-err" class="kx-error" aria-live="polite"></span></div>'
        f'<div class="kx-row-between"><div class="kx-check"><input id="f-recordar" name="recordar" type="checkbox"><label for="f-recordar">{_esc(t["remember"])}</label></div>'
        f'<a href="#">{_esc(t["forgot"])}</a></div>'
        f'<button class="kx-btn" type="submit" style="width:100%">{_esc(t["login_btn"])}</button></form></div></main></div>'
    )
    return body, ["Card", "TextField", "Checkbox", "Button", "IconButton"]


def _chart(t: Dict[str, Any]) -> str:
    values = [42, 48, 45, 53, 58, 55, 62, 68, 64, 72, 78, 84]
    width, height, pad = 640, 220, 28
    low, high = min(values) - 5, max(values) + 5
    xs = [pad + i * (width - 2 * pad) / (len(values) - 1) for i in range(len(values))]
    ys = [height - pad - (v - low) / (high - low) * (height - 2 * pad) for v in values]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"{line} L{xs[-1]:.1f},{height - pad} L{xs[0]:.1f},{height - pad} Z"
    grid = "".join(f'<line class="grid" x1="{pad}" x2="{width - pad}" y1="{pad + k * (height - 2 * pad) / 3:.1f}" '
                   f'y2="{pad + k * (height - 2 * pad) / 3:.1f}"/>' for k in range(4))
    dots = "".join(f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="4"/>' for x, y in zip(xs, ys))
    labels = "".join(f'<text x="{x:.1f}" y="{height - 6}" text-anchor="middle">{_esc(m)}</text>' for x, m in zip(xs, t["months"]))
    rows = "".join(f"<tr><td>{_esc(m)}</td><td>{v}</td></tr>" for m, v in zip(t["months"], values))
    return (
        f'<svg class="kx-chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="kx-chart-t kx-chart-d">'
        f'<title id="kx-chart-t">{_esc(t["trend"])}</title><desc id="kx-chart-d">{_esc(t["chart_desc"])}</desc>'
        f'{grid}<path class="area" d="{area}"/><path class="line" d="{line}"/>{dots}{labels}</svg>'
        f'<details><summary>{_esc(t["show_data"])}</summary><table class="kx-table"><thead><tr><th scope="col">{_esc(t["month"])}</th>'
        f'<th scope="col">{_esc(t["value"])}</th></tr></thead><tbody>{rows}</tbody></table></details>'
    )


def _dashboard(t, app, opts, lang):
    sep = "," if lang == "en" else "."
    cards = []
    for i, label in enumerate(opts["kpis"]):
        value = f"{(128450 // (i + 1)) - i * 917:,}".replace(",", sep)
        up = i % 4 != 3
        delta = f"{'+' if up else '-'}{(12.5 - i * 2.75) if up else 3.2:.1f} %".replace(".", "," if lang != "en" else ".")
        cards.append(
            f'<article class="kx-card kx-kpi" aria-labelledby="kpi-{i}"><h2 id="kpi-{i}">{_esc(label)}</h2>'
            f'<p class="kx-kpi-value">{value}</p><p class="kx-trend kx-trend--{"up" if up else "down"}">{_icon("up" if up else "down")}'
            f'<span class="kx-delta"><span class="sr-only">{_esc(t["up"] if up else t["down"])} </span>{delta}</span>'
            f' <span class="kx-muted">{_esc(t["vs_prev"])}</span></p></article>'
        )
    feed = "".join(
        f'<li><span class="kx-avatar" aria-hidden="true">{_esc(_initials(_SAMPLE_NAMES[i]))}</span><div><strong>{_esc(_SAMPLE_NAMES[i])}</strong> '
        f'{_esc(t["events"][i])}<time>{_esc(t["ago"][i])}</time></div></li>' for i in range(5)
    )
    periods = "".join(f'<option{" selected" if i == 1 else ""}>{_esc(p)}</option>' for i, p in enumerate(t["periods"]))
    actions = (f'<label class="sr-only" for="kx-period">{_esc(t["period"])}</label>'
               f'<select id="kx-period" class="kx-input" style="width:auto">{periods}</select>'
               f'<button class="kx-btn kx-btn--secondary" type="button">{_icon("download")}{_esc(t["export"])}</button>'
               f'<a class="kx-btn" href="#">{_icon("plus")}{_esc(t["new"])} {_esc(opts["entidad"].lower())}</a>')
    quick = "".join(
        f'<a class="kx-btn kx-btn--secondary" href="#">{_icon(icon)}{_esc(label)}</a>'
        for icon, label in (("plus", f'{t["new"]} {opts["entidad"].lower()}'), ("list", opts["entidad_plural"]),
                            ("chart", t["reports"]), ("sliders", t["settings"]))
    )
    content = (
        _crumbs(t, [opts["modulos"][0]])
        + _pagehead(f'{t["welcome"]}, {opts["usuario"].split()[0]}', f'{app} · {t["periods"][1]}', actions)
        + f'<section class="kx-kpis" aria-label="KPI">{"".join(cards)}</section>'
        + '<div class="kx-grid-2">'
        + f'<section class="kx-card" aria-labelledby="kx-trend-h"><div class="kx-head-row"><h2 id="kx-trend-h">{_esc(t["trend"])}</h2></div>{_chart(t)}</section>'
        + f'<section class="kx-card" aria-labelledby="kx-act-h"><h2 id="kx-act-h">{_esc(t["activity"])}</h2><ul class="kx-feed">{feed}</ul></section>'
        + '</div>'
        + f'<section class="kx-card" aria-labelledby="kx-quick-h"><h2 id="kx-quick-h">{_esc(t["quick"])}</h2><div class="kx-quick">{quick}</div></section>'
    )
    return _shell(t, app, opts, 0, content), ["Sidebar", "Navbar", "SearchField", "Dropdown", "Breadcrumbs", "Kpi", "Chart",
                                              "Card", "Avatar", "Button", "Select"]


def _list(t, app, opts):
    columns = opts["columnas"]
    heads = (f'<th scope="col" class="kx-col-check"><input type="checkbox" id="kx-all" aria-label="{_esc(t["select_all"])}"></th>'
             + "".join(f'<th scope="col" aria-sort="none" data-kx-col><button class="kx-sort" type="button" data-kx-sort="{i + 1}">'
                       f'{_esc(c["etiqueta"])}{_icon("chevron")}</button></th>' for i, c in enumerate(columns))
             + f'<th scope="col" aria-sort="none" data-kx-col><button class="kx-sort" type="button" data-kx-sort="{len(columns) + 1}">'
               f'{_esc(t["status"])}{_icon("chevron")}</button></th><th scope="col"><span class="sr-only">{_esc(t["actions"])}</span></th>')
    rows = []
    for i in range(SAMPLE_ROWS):
        values = [_sample(c, i, t) for c in columns]
        status, badge = _status_badge(t, i)
        label = _esc(values[0][0] if values else f'{opts["entidad"]} {i + 1}')
        cells = "".join(f'<td data-sort="{_esc(key)}">{_esc(text)}</td>' if key else f"<td>{_esc(text)}</td>"
                        for text, key in values)
        rows.append(
            f'<tr data-status="{status}"><td><input type="checkbox" class="kx-row-check" aria-label="{_esc(t["select_row"])} {label}"></td>'
            f'{cells}<td data-sort="{status}">{badge}</td><td><div class="kx-row-actions">'
            f'<a class="kx-btn kx-btn--ghost kx-btn--icon" href="#" aria-label="{_esc(t["view"])} {label}">{_icon("eye")}</a>'
            f'<a class="kx-btn kx-btn--ghost kx-btn--icon" href="#" aria-label="{_esc(t["edit"])} {label}">{_icon("edit")}</a>'
            '</div></td></tr>'
        )
    statuses = "".join(f'<option value="{s}">{_esc(t[s])}</option>' for s in _STATUSES)
    plural = opts["entidad_plural"]
    actions = (f'<button class="kx-btn kx-btn--secondary" type="button" data-kx-export="{_esc(plural.lower())}">{_icon("download")}{_esc(t["export"])}</button>'
               f'<a class="kx-btn" href="#">{_icon("plus")}{_esc(t["new"])} {_esc(opts["entidad"].lower())}</a>')
    sizes = "".join(f'<option{" selected" if n == 10 else ""}>{n}</option>' for n in (10, 25, 50))
    content = (
        _crumbs(t, [plural])
        + _pagehead(plural, f"{SAMPLE_ROWS} {t['results']}", actions)
        + '<section class="kx-card kx-table-card" data-kx-table aria-labelledby="kx-list-cap">'
        + '<div class="kx-filters">'
        + f'<div class="kx-field kx-grow"><label for="kx-q">{_esc(t["search"])}</label><input id="kx-q" type="search" autocomplete="off"></div>'
        + f'<div class="kx-field"><label for="kx-status">{_esc(t["status"])}</label><select id="kx-status"><option value="">{_esc(t["all"])}</option>{statuses}</select></div>'
        + f'<button class="kx-btn kx-btn--ghost" type="button" data-kx-density aria-pressed="false">{_icon("list")}{_esc(t["density"])}</button></div>'
        + f'<div class="kx-bulk" id="kx-bulk" hidden><strong id="kx-count" aria-live="polite"></strong>'
        + f'<button class="kx-btn kx-btn--secondary" type="button" data-kx-confirm="kx-delete">{_icon("trash")}{_esc(t["delete"])}</button></div>'
        + f'<div class="kx-table-wrap"><table class="kx-table"><caption id="kx-list-cap" class="sr-only">{_esc(plural)}</caption>'
        + f'<thead><tr>{heads}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
        + f'<div class="kx-empty" id="kx-empty" hidden>{_icon("search")}<h2>{_esc(t["empty_title"])}</h2><p class="kx-muted">{_esc(t["empty_text"])}</p>'
        + f'<button class="kx-btn kx-btn--secondary" type="button" data-kx-clear>{_esc(t["clear"])}</button></div></div>'
        + f'<nav class="kx-pager" aria-label="{_esc(t["page"])}"><div class="kx-field"><label for="kx-size">{_esc(t["rows_per_page"])}</label>'
        + f'<select id="kx-size">{sizes}</select></div><span id="kx-page-info" class="kx-muted" aria-live="polite"></span><div class="kx-toolbar">'
        + f'<button class="kx-btn kx-btn--secondary" type="button" data-kx-prev>{_esc(t["prev"])}</button>'
        + f'<button class="kx-btn kx-btn--secondary" type="button" data-kx-next>{_esc(t["next"])}</button></div></nav></section>'
        + _dialog("kx-delete", t["delete_title"], t["delete_text"], t["delete"], t["cancel"], "delete")
    )
    return _shell(t, app, opts, 1, content), ["Sidebar", "Navbar", "SearchField", "Breadcrumbs", "DataTable", "Checkbox",
                                              "Badge", "IconButton", "Pagination", "EmptyState", "Modal", "Toast", "Button"]


def _form(t, app, opts):
    fields = opts["campos"]
    half = (len(fields) + 1) // 2 if len(fields) > 3 else len(fields)
    sections = [(t["general"], fields[:half]), (t["additional"], fields[half:])]
    fieldsets = "".join(
        f'<fieldset><legend>{_esc(title)}</legend><div class="kx-form-grid">{"".join(_input(f, t) for f in group)}</div></fieldset>'
        for title, group in sections if group
    )
    entity = opts["entidad"]
    content = (
        _crumbs(t, [opts["entidad_plural"], f'{t["new"]} {entity.lower()}'])
        + _pagehead(f'{t["new"]} {entity.lower()}', t["required_hint"])
        + f'<form class="kx-form" method="post" novalidate data-kx-validate>{fieldsets}'
        + f'<div class="kx-actionbar"><span class="kx-muted kx-help">{_esc(t["required_hint"])}</span>'
        + f'<button class="kx-btn kx-btn--secondary" type="button" data-kx-cancel>{_esc(t["cancel"])}</button>'
        + f'<button class="kx-btn" type="submit">{_icon("check")}{_esc(t["save"])}</button></div></form>'
        + _dialog("kx-discard", t["confirm_title"], t["confirm_text"], t["discard"], t["keep"], "discard")
    )
    used = {"TextField", "Button", "Modal", "Toast", "Sidebar", "Navbar", "Breadcrumbs"}
    used |= {{"select": "Select", "textarea": "TextArea", "checkbox": "Checkbox"}.get(f["tipo"], "TextField") for f in fields}
    return _shell(t, app, opts, 1, content), sorted(used)


def _detail(t, app, opts):
    fields = opts["campos"]
    values = [_sample(f, 0, t)[0] for f in fields]
    title = values[0] if values else f'{opts["entidad"]} 1'
    items = "".join(f'<div><dt>{_esc(f["etiqueta"])}</dt><dd>{_esc(v)}</dd></div>' for f, v in zip(fields, values))
    history = "".join(
        f'<li><strong>{_esc(_SAMPLE_NAMES[i])}</strong> {_esc(t["events"][i])}<time class="kx-muted" style="display:block">{_esc(t["ago"][i])}</time></li>'
        for i in range(4)
    )
    _, badge = _status_badge(t, 0)
    actions = (f'<a class="kx-btn kx-btn--secondary" href="#">{_icon("edit")}{_esc(t["edit"])}</a>'
               f'<button class="kx-btn kx-btn--danger" type="button" data-kx-confirm="kx-delete">{_icon("trash")}{_esc(t["delete"])}</button>')
    content = (
        _crumbs(t, [opts["entidad_plural"], title])
        + f'<div class="kx-pagehead"><div><h1>{_esc(title)}</h1><p class="kx-muted">{badge} · {_esc(t["created"])} 2026-01-15 {_esc(t["by"])} '
        + f'{_esc(_SAMPLE_NAMES[1])}</p></div><div class="kx-toolbar">{actions}</div></div>'
        + '<section class="kx-card">'
        + f'<div class="kx-tabs" role="tablist" aria-label="{_esc(opts["entidad"])}">'
        + f'<button class="kx-tab" role="tab" id="tab-d" aria-controls="panel-d" aria-selected="true" type="button">{_esc(t["details"])}</button>'
        + f'<button class="kx-tab" role="tab" id="tab-h" aria-controls="panel-h" aria-selected="false" tabindex="-1" type="button">{_esc(t["history"])}</button></div>'
        + f'<div class="kx-panel" role="tabpanel" id="panel-d" aria-labelledby="tab-d" tabindex="0"><dl class="kx-dl">{items}</dl></div>'
        + f'<div class="kx-panel" role="tabpanel" id="panel-h" aria-labelledby="tab-h" tabindex="0" hidden><ol class="kx-timeline">{history}</ol></div>'
        + '</section>'
        + _dialog("kx-delete", t["delete_title"], t["delete_text"], t["delete"], t["cancel"], "delete")
    )
    return _shell(t, app, opts, 1, content), ["Sidebar", "Navbar", "Breadcrumbs", "Tabs", "Badge", "Card", "Button", "Modal"]


def _settings(t, app, opts, lang):
    def switch(sid: str, label: str, help_text: str = "", checked: bool = False) -> str:
        help_html = f'<span id="{sid}-h" class="kx-help">{_esc(help_text)}</span>' if help_text else ""
        described = f' aria-describedby="{sid}-h"' if help_text else ""
        return (f'<div class="kx-setting"><div><label for="{sid}">{_esc(label)}</label>{help_html}</div>'
                f'<input id="{sid}" class="kx-switch" type="checkbox" role="switch"{described}{" checked" if checked else ""}></div>')

    languages = "".join(f'<option value="{code}"{" selected" if code == lang else ""}>{name}</option>'
                        for code, name in (("es", "Español"), ("en", "English"), ("pt", "Português")))
    tabs = [("p", t["profile_tab"]), ("s", t["security_tab"]), ("n", t["notif_tab"]), ("a", t["appearance_tab"])]
    unfocused = ' tabindex="-1"'
    tab_buttons = "".join(
        f'<button class="kx-tab" role="tab" id="tab-{k}" aria-controls="panel-{k}" aria-selected="{"true" if i == 0 else "false"}"'
        f'{"" if i == 0 else unfocused} type="button">{_esc(label)}</button>' for i, (k, label) in enumerate(tabs)
    )
    email = f'{re.sub(r"[^a-z]", "", opts["usuario"].split()[0].lower()) or "usuario"}@ejemplo.com'
    panels = {
        "p": (f'<div class="kx-form-grid"><div class="kx-field"><label for="s-nombre">{_esc(t["full_name"])}</label>'
              f'<input id="s-nombre" value="{_esc(opts["usuario"])}" autocomplete="name"></div>'
              f'<div class="kx-field"><label for="s-correo">{_esc(t["email"])}</label><input id="s-correo" type="email" value="{_esc(email)}" autocomplete="email"></div>'
              f'<div class="kx-field"><label for="s-idioma">{_esc(t["language"])}</label><select id="s-idioma">{languages}</select></div></div>'),
        "s": switch("s-mfa", t["mfa"], t["mfa_text"], True)
             + f'<div class="kx-setting"><span>{_esc(t["sessions"])}</span><button class="kx-btn kx-btn--secondary" type="button">{_icon("logout")}{_esc(t["sessions"])}</button></div>',
        "n": switch("s-correo-diario", t["email_notif"], checked=True) + switch("s-push", t["push_notif"]),
        "a": f'<div class="kx-setting"><span>{_esc(t["dark_mode"])}</span><button class="kx-btn kx-btn--secondary" type="button" data-kx-theme>{_icon("moon")}{_esc(t["dark_mode"])}</button></div>',
    }
    panel_html = "".join(
        f'<div class="kx-panel" role="tabpanel" id="panel-{k}" aria-labelledby="tab-{k}" tabindex="0"{"" if i == 0 else " hidden"}>{panels[k]}</div>'
        for i, (k, _) in enumerate(tabs)
    )
    content = (
        _crumbs(t, [t["settings"]])
        + _pagehead(t["settings"], app)
        + f'<form class="kx-card" novalidate data-kx-validate onsubmit="return false"><div class="kx-tabs" role="tablist" aria-label="{_esc(t["settings"])}">{tab_buttons}</div>'
        + f'{panel_html}<div class="kx-dialog-actions"><button class="kx-btn" type="submit">{_icon("check")}{_esc(t["save"])}</button></div></form>'
    )
    return _shell(t, app, opts, len(opts["modulos"]) - 1, content), ["Sidebar", "Navbar", "Breadcrumbs", "Tabs", "TextField",
                                                                    "Select", "Checkbox", "Button", "Toast"]


def screen_html(tokens: Dict[str, Any], screen: str, app_name: str, lang: str = "es",
                options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if screen not in SCREEN_TYPES:
        raise DesignError(f"Tipo de pantalla no soportado: {screen!r} (opciones: {', '.join(SCREEN_TYPES)})")
    if lang not in LANGUAGES:
        raise DesignError("idioma debe ser es, en o pt")
    t = _TEXTS[lang]
    opts = screen_options(options, lang)
    if screen == "login":
        body, components = _login(t, app_name, opts)
        title = t["login_title"]
    elif screen == "dashboard":
        body, components = _dashboard(t, app_name, opts, lang)
        title = opts["modulos"][0]
    elif screen == "list":
        body, components = _list(t, app_name, opts)
        title = opts["entidad_plural"]
    elif screen == "form":
        body, components = _form(t, app_name, opts)
        title = f'{t["new"]} {opts["entidad"].lower()}'
    elif screen == "detail":
        body, components = _detail(t, app_name, opts)
        title = opts["entidad"]
    else:
        body, components = _settings(t, app_name, opts, lang)
        title = t["settings"]
    document = _document(t, lang, title, app_name, to_css(tokens), body)
    return {
        "pantalla": screen,
        "idioma": lang,
        "componentes_usados": components,
        "opciones_aplicadas": {k: opts[k] for k in ("entidad", "entidad_plural", "modulos", "multiempresa")}
                              | {"campos": [f["nombre"] for f in opts["campos"]],
                                 "columnas": [c["nombre"] for c in opts["columnas"]]},
        "funcionalidades": FEATURES[screen],
        "html": document,
        "bytes": len(document.encode("utf-8")),
    }


_SHELL_FEATURES = ["barra lateral contraíble (menú móvil)", "búsqueda global con atajo /", "tema claro/oscuro persistente",
                   "notificaciones", "menú de usuario", "migas de pan", "selector de empresa (multiempresa)"]
FEATURES: Dict[str, List[str]] = {
    "login": ["diseño dividido con panel de marca", "mostrar u ocultar contraseña", "recordarme", "recuperar contraseña",
              "validación accesible en línea"],
    "dashboard": [*_SHELL_FEATURES, "KPI con tendencia", "gráfico SVG con tabla de datos accesible", "actividad reciente",
                  "acciones rápidas", "selector de periodo"],
    "list": [*_SHELL_FEATURES, "búsqueda y filtro por estado", "orden por columna", "selección múltiple y acciones en lote",
             "paginación con tamaño de página", "exportar CSV (protegido contra inyección de fórmulas)", "vista compacta",
             "estado vacío", "confirmación antes de eliminar"],
    "form": [*_SHELL_FEATURES, "secciones", "validación en línea", "barra de acciones fija",
             "confirmación al descartar cambios", "aviso de cambios sin guardar", "toast de confirmación"],
    "detail": [*_SHELL_FEATURES, "pestañas con teclado", "lista de atributos", "historial", "editar y eliminar con confirmación"],
    "settings": [*_SHELL_FEATURES, "pestañas perfil/seguridad/notificaciones/apariencia", "interruptores accesibles",
                 "verificación en dos pasos", "idioma"],
}
