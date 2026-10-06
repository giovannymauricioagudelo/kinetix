"""
Cortex (OrchestratorAgent) — punto de entrada de la fábrica de aplicaciones.

Evalúa cada solicitud (aplicación nueva, escalabilidad, mejora o corrección),
calcula su complejidad, hace las preguntas que correspondan a ese nivel y solo
entonces propone un plan que reparte el trabajo entre los demás agentes.
Con complejidad media o alta el plan se ejecuta por sprints ("Sprint 1 de N",
identificados por aplicación): un humano decide cuándo iniciar cada uno.
Cortex no ejecuta tareas: ningún plan se delega sin aprobación humana.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from src.agents.agent_catalog import (
    ARGUS,
    AURORA,
    CORTEX,
    GENESIS,
    INSIGHT,
    MATRIX,
    NEXUS,
    ORBIT,
    PRISM,
    SENTINEL,
    SYNAPSE,
    VECTOR,
    AgentProfile,
)

logger = logging.getLogger(__name__)


class RequestType(str, Enum):
    NEW_APP = "nueva_aplicacion"
    SCALE = "escalabilidad"
    ENHANCEMENT = "mejora"
    BUGFIX = "correccion"


class Complexity(str, Enum):
    LOW = "baja"
    MEDIUM = "media"
    HIGH = "alta"


class RequestStatus(str, Enum):
    NEEDS_CLARIFICATION = "requiere_aclaraciones"
    PLAN_PROPOSED = "plan_propuesto"
    APPROVED = "aprobado"
    COMPLETED = "completada"


class TaskStatus(str, Enum):
    PENDING_APPROVAL = "pendiente_aprobacion"
    READY_TO_DELEGATE = "lista_para_delegar"
    BY_SPRINT = "por_sprint"
    WAITING_SPRINT = "espera_sprint"
    DONE = "completada"


class SprintStatus(str, Enum):
    PLANNED = "planificado"
    PENDING = "pendiente"
    IN_PROGRESS = "en_curso"
    DONE = "completado"


@dataclass(frozen=True)
class Question:
    id: str
    texto: str
    motivo: str

    def to_dict(self) -> Dict[str, str]:
        return {"id": self.id, "pregunta": self.texto, "motivo": self.motivo}


@dataclass
class PlanTask:
    id: str
    agent: AgentProfile
    accion: str
    depends_on: List[str]
    status: TaskStatus = TaskStatus.PENDING_APPROVAL

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "agente": self.agent.codename,
            "legacy_id": self.agent.legacy_id,
            "accion": self.accion,
            "depende_de": self.depends_on,
            "estado": self.status.value,
        }


@dataclass
class Sprint:
    """Etapa entregable del proyecto; un humano decide cuándo iniciarla y cuándo darla por completada."""

    numero: int
    total: int
    aplicacion: str
    clave: str
    nombre: str
    objetivo: str
    entregable: str
    tareas: List[PlanTask]
    status: SprintStatus = SprintStatus.PLANNED
    started_by: Optional[str] = None
    started_at: Optional[str] = None
    completed_by: Optional[str] = None
    completed_at: Optional[str] = None
    notas: Optional[str] = None

    @property
    def id(self) -> str:
        return sprint_id(self.aplicacion, self.numero)

    @property
    def etiqueta(self) -> str:
        return f"Sprint {self.numero} de {self.total}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "numero": self.numero,
            "total": self.total,
            "etiqueta": self.etiqueta,
            "aplicacion": self.aplicacion,
            "clave": self.clave,
            "nombre": self.nombre,
            "objetivo": self.objetivo,
            "entregable": self.entregable,
            "criterio_salida": SPRINT_EXIT_CRITERIA,
            "depende_de": sprint_id(self.aplicacion, self.numero - 1) if self.numero > 1 else None,
            "estado": self.status.value,
            "tareas": [t.to_dict() for t in self.tareas],
            "iniciado_por": self.started_by,
            "iniciado_en": self.started_at,
            "completado_por": self.completed_by,
            "completado_en": self.completed_at,
            "notas": self.notas,
        }


@dataclass
class OrchestrationRequest:
    id: str
    descripcion: str
    app_id: Optional[str] = None
    explicit_type: Optional[RequestType] = None
    request_type: Optional[RequestType] = None
    complexity: Optional[Complexity] = None
    capabilities: List[str] = field(default_factory=list)
    answers: Dict[str, str] = field(default_factory=dict)
    pending_questions: List[Question] = field(default_factory=list)
    plan: List[PlanTask] = field(default_factory=list)
    status: RequestStatus = RequestStatus.NEEDS_CLARIFICATION
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    data_model: Optional[str] = None
    db_engine: Optional[str] = None
    db_engine_reason: Optional[str] = None
    engine_change: Optional[str] = None
    new_app_id: Optional[str] = None
    sprints: List[Sprint] = field(default_factory=list)

    @property
    def aplicacion(self) -> Optional[str]:
        """Identificador que agrupa los sprints: la aplicación existente o la que se va a crear."""
        return self.app_id or self.new_app_id

    def current_sprint(self) -> Optional[Sprint]:
        return next((s for s in self.sprints if s.status == SprintStatus.IN_PROGRESS), None)

    def next_sprint(self) -> Optional[Sprint]:
        return next((s for s in self.sprints if s.status in (SprintStatus.PLANNED, SprintStatus.PENDING)), None)

    def _next_step(self) -> str:
        if self.status == RequestStatus.NEEDS_CLARIFICATION:
            return "Responde las preguntas pendientes para que Cortex pueda proponer un plan."
        if self.status == RequestStatus.PLAN_PROPOSED:
            if self.sprints:
                return (f"Revisa el plan por sprints ({len(self.sprints)} sprints) y apruébalo; "
                        "Cortex no delega nada sin aprobación humana.")
            return "Revisa el plan y apruébalo; Cortex no delega nada sin aprobación humana."
        if self.status == RequestStatus.COMPLETED:
            return f"Los {len(self.sprints)} sprints de {self.aplicacion} están completados."
        if not self.sprints:
            return "Plan aprobado: las tareas están listas para delegarse a cada agente."
        current = self.current_sprint()
        if current:
            return f"{current.etiqueta} ({current.id}) en curso: complétalo para habilitar el siguiente."
        upcoming = self.next_sprint()
        return f"Plan aprobado por sprints: inicia el {upcoming.etiqueta} ({upcoming.id}) cuando decidas continuar."

    def sprint_progress(self) -> Optional[Dict[str, object]]:
        if not self.sprints:
            return None
        current, upcoming = self.current_sprint(), self.next_sprint()
        return {
            "aplicacion": self.aplicacion,
            "total": len(self.sprints),
            "completados": sum(1 for s in self.sprints if s.status == SprintStatus.DONE),
            "actual": current.etiqueta if current else None,
            "siguiente": upcoming.etiqueta if upcoming else None,
        }

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "descripcion": self.descripcion,
            "app_id": self.app_id,
            "aplicacion": self.aplicacion,
            "tipo_solicitud": self.request_type.value if self.request_type else None,
            "complejidad": self.complexity.value if self.complexity else None,
            "capacidades_detectadas": self.capabilities,
            "modelo_datos": self.data_model,
            "motor_base_datos": self.db_engine,
            "motivo_motor": self.db_engine_reason,
            "cambio_motor": self.engine_change,
            "estado": self.status.value,
            "preguntas_pendientes": [q.to_dict() for q in self.pending_questions],
            "respuestas": self.answers,
            "plan": [t.to_dict() for t in self.plan],
            "ejecucion_por_sprints": bool(self.sprints),
            "progreso_sprints": self.sprint_progress(),
            "sprints": [s.to_dict() for s in self.sprints],
            "aprobado_por": self.approved_by,
            "aprobado_en": self.approved_at,
            "creado_en": self.created_at,
            "siguiente_paso": self._next_step(),
        }


# ============================================================================
# CONOCIMIENTO DEL DOMINIO (palabras clave normalizadas: minúsculas, sin tildes)
# ============================================================================

TYPE_KEYWORDS: Dict[RequestType, Tuple[str, ...]] = {
    RequestType.NEW_APP: (
        "nueva aplicacion", "nueva app", "aplicacion nueva", "crear una aplicacion",
        "crear una app", "desde cero", "construir una aplicacion", "desarrollar una aplicacion",
    ),
    RequestType.SCALE: (
        "escalar", "escalabilidad", "escalable", "rendimiento", "performance", "lento",
        "lentitud", "latencia", "concurrencia", "usuarios concurrentes", "alta carga",
        "picos de carga",
    ),
    RequestType.ENHANCEMENT: (
        "mejorar", "mejora", "mejoras", "agregar", "anadir", "nueva funcionalidad",
        "nuevo modulo", "ampliar", "modificar", "extender",
    ),
    RequestType.BUGFIX: (
        "error", "errores", "falla", "fallas", "bug", "bugs", "corregir", "correccion",
        "arreglar", "no funciona", "excepcion", "se cae", "crash",
    ),
}

TYPE_ANSWER_HINTS: Tuple[Tuple[str, RequestType], ...] = (
    ("nueva", RequestType.NEW_APP),
    ("escal", RequestType.SCALE),
    ("mejora", RequestType.ENHANCEMENT),
    ("correc", RequestType.BUGFIX),
)

CAPABILITIES: Dict[str, Tuple[AgentProfile, Tuple[str, ...]]] = {
    "datos": (NEXUS, (
        "base de datos", "bases de datos", "tabla", "tablas", "esquema", "sql",
        "modelo de datos", "datos", "migracion", "indices", "consultas",
    )),
    "integraciones": (SYNAPSE, (
        "api", "apis", "integracion", "integraciones", "integrar", "webhook", "erp",
        "pasarela de pago", "servicio externo", "sistemas externos", "rest",
    )),
    "reglas": (MATRIX, (
        "regla", "reglas", "validacion", "validaciones", "aprobacion", "calculo",
        "impuesto", "impuestos", "retencion", "retenciones", "politica", "politicas",
        "descuento", "descuentos",
    )),
    "reportes": (INSIGHT, (
        "reporte", "reportes", "dashboard", "dashboards", "kpi", "kpis", "metrica",
        "metricas", "informe", "informes", "analitica", "indicadores",
    )),
    "interfaz": (AURORA, (
        "pantalla", "pantallas", "interfaz", "ui", "ux", "movil", "web", "formulario",
        "formularios", "diseno", "frontend",
    )),
    "ia": (GENESIS, (
        "ia", "inteligencia artificial", "chatbot", "prediccion", "predicciones", "llm",
        "recomendaciones", "machine learning", "asistente virtual",
    )),
    "seguridad": (SENTINEL, (
        "seguridad", "autenticacion", "login", "inicio de sesion", "contrasena", "contrasenas",
        "permisos", "roles y permisos", "mfa", "2fa", "doble factor", "sso", "cifrado",
    )),
    "monitoreo": (ARGUS, (
        "monitoreo", "monitorear", "observabilidad", "alerta", "alertas", "uptime", "caidas",
        "salud del sistema", "trazas", "logs",
    )),
}

MULTI_TENANT = ("multiempresa", "multi empresa", "multitenant", "multi tenant", "varias empresas", "multisede")
HIGH_VOLUME = ("millones", "miles de usuarios", "alta concurrencia", "usuarios concurrentes", "alta disponibilidad", "24/7")
COMPLIANCE = ("normativa", "normativas", "cumplimiento", "auditoria", "dian", "gdpr", "pci", "habeas data", "regulacion")

TYPE_BASE_SCORE = {
    RequestType.NEW_APP: 2,
    RequestType.SCALE: 1,
    RequestType.ENHANCEMENT: 0,
    RequestType.BUGFIX: 0,
}

Q_TYPE = Question(
    "tipo_solicitud",
    "¿Se trata de una aplicación nueva, escalar una existente, una mejora o una corrección?",
    "La descripción no deja claro el tipo de solicitud y de eso depende todo el plan.",
)
Q_APP = Question(
    "app_id",
    "¿Sobre qué aplicación existente es la solicitud (nombre o identificador)?",
    "Hace falta saber qué aplicación se va a tocar.",
)
Q_SCOPE = Question(
    "alcance",
    "¿Qué áreas abarca: datos, integraciones con otros sistemas, reglas de negocio, reportes, interfaz, IA, seguridad o monitoreo?",
    "No se detectó qué partes de la aplicación están involucradas.",
)
Q_DATA_MODEL = Question(
    "modelo_datos",
    "¿Cómo se separan los datos de cada empresa: 'una base por empresa' (base independiente por cliente) o "
    "'multiempresa' (una sola base compartida con id_empresa)? Si solo habrá una empresa responde 'no aplica'.",
    "Nexus crea la base de datos independiente de la aplicación y despliega los objetos según este modelo.",
)

DATA_MODEL_HINTS: Tuple[Tuple[str, str], ...] = (
    ("multiempresa", "multiempresa"), ("multi empresa", "multiempresa"), ("multitenant", "multiempresa"),
    ("compartida", "multiempresa"), ("una sola base", "multiempresa"),
    ("por empresa", "por_empresa"), ("por cliente", "por_empresa"), ("independiente", "por_empresa"),
    ("separada", "por_empresa"), ("no aplica", "por_empresa"), ("una sola empresa", "por_empresa"),
)
DATA_MODEL_LABELS = {
    "por_empresa": "una base de datos por empresa ({app}_{empresa})",
    "multiempresa": "una base multiempresa ({app}) con id_empresa y seguridad por fila",
}


def data_model_from(answer: str) -> Optional[str]:
    normalized = _normalize(answer)
    for hint, model in DATA_MODEL_HINTS:
        if hint in normalized:
            return model
    return None


Q_DB_ENGINE = Question(
    "motor_base_datos",
    "¿Qué motor de base de datos usará la aplicación: SQL Server, PostgreSQL, Firebird o MongoDB? "
    "Si no tienes preferencia responde 'recomienda'. Se puede cambiar después si la aplicación escala.",
    "Nexus crea la base en ese motor y guarda las tablas en formato portable para poder cambiar de motor más adelante.",
)
Q_ENGINE_CHANGE = Question(
    "cambio_motor",
    "¿Quieres pasar la aplicación a otro motor de base de datos (por ejemplo de MongoDB a SQL Server o PostgreSQL)? "
    "Indica el motor destino o responde 'no aplica'.",
    "Nexus puede cambiar el motor: despliega el esquema en el nuevo, copia los datos y deja el cambio revertible.",
)
DB_ENGINE_HINTS: Tuple[Tuple[str, str], ...] = (
    ("mongo", "mongodb"), ("nosql", "mongodb"), ("documental", "mongodb"),
    ("postgres", "postgresql"), ("firebird", "firebird"),
    ("sql server", "sqlserver"), ("sqlserver", "sqlserver"), ("mssql", "sqlserver"), ("sql", "sqlserver"),
)
DB_ENGINE_RECOMMEND = ("recomienda", "recomendado", "recomendacion", "no aplica", "no se", "cualquiera",
                       "indiferente", "sin preferencia", "decide", "decidan")
FLEXIBLE_DOCUMENTS = ("documentos", "esquema flexible", "estructura variable", "json", "catalogo dinamico", "iot",
                      "eventos", "sensores", "contenido")
DB_ENGINE_LABELS = {"sqlserver": "SQL Server", "postgresql": "PostgreSQL", "firebird": "Firebird", "mongodb": "MongoDB"}


def db_engine_from(answer: str, last: bool = False) -> Optional[str]:
    """Primer motor mencionado; con last=True el último ('de Mongo a SQL Server' → sqlserver)."""
    normalized = _normalize(answer)
    found = [(m.start(), engine) for hint, engine in DB_ENGINE_HINTS
             for m in re.finditer(rf"\b{re.escape(hint)}", normalized)]
    if not found:
        return None
    return (max if last else min)(found)[1]


def recommend_db_engine(corpus: str) -> Tuple[str, str]:
    """SQL Server es el estándar corporativo; MongoDB solo si pide documentos flexibles sin multiempresa ni normativa."""
    if _contains_any(corpus, FLEXIBLE_DOCUMENTS) and not _contains_any(corpus, MULTI_TENANT + COMPLIANCE):
        return "mongodb", "Recomendado por Cortex: datos de estructura flexible sin multiempresa ni normativa"
    return "sqlserver", "Recomendado por Cortex: estándar corporativo, transacciones ACID y seguridad por fila"


TIER_ORDER = {Complexity.LOW: 0, Complexity.MEDIUM: 1, Complexity.HIGH: 2}

QUESTION_BANK: Dict[RequestType, List[Tuple[Complexity, Question]]] = {
    RequestType.NEW_APP: [
        (Complexity.LOW, Question("objetivo", "¿Qué problema de negocio resuelve la aplicación?", "Define el alcance funcional.")),
        (Complexity.LOW, Question("usuarios_roles", "¿Quiénes la van a usar y con qué roles (administrador, cliente, técnico…)?", "Define permisos y flujos por rol.")),
        (Complexity.LOW, Question("plataformas", "¿En qué plataformas debe funcionar: web, móvil, escritorio o solo API?", "Define si interviene Aurora y qué entregables de interfaz.")),
        (Complexity.LOW, Q_DATA_MODEL),
        (Complexity.LOW, Q_DB_ENGINE),
        (Complexity.MEDIUM, Question("volumen", "¿Cuántos usuarios concurrentes y transacciones por día esperas?", "Dimensiona base de datos e infraestructura.")),
        (Complexity.MEDIUM, Question("integraciones", "¿Con qué sistemas externos debe integrarse (ERP, pagos, correo…)?", "Define el trabajo de Synapse.")),
        (Complexity.MEDIUM, Question("datos_existentes", "¿Hay datos existentes que migrar? ¿De qué sistema?", "Define si Nexus debe planear una migración.")),
        (Complexity.HIGH, Question("cumplimiento", "¿Aplica alguna normativa (DIAN, habeas data, PCI, auditoría)?", "Agrega reglas y controles obligatorios.")),
        (Complexity.HIGH, Question("disponibilidad", "¿Qué disponibilidad se exige (horario laboral, 24/7, SLA)?", "Define la estrategia de despliegue de Orbit.")),
        (Complexity.HIGH, Question("plazo_presupuesto", "¿Cuál es el plazo y el presupuesto disponible?", "Permite priorizar y dividir en fases.")),
    ],
    RequestType.SCALE: [
        (Complexity.LOW, Question("sintoma", "¿Qué síntoma ves hoy (lentitud, caídas, errores bajo carga) y en qué módulo?", "Ubica el cuello de botella.")),
        (Complexity.LOW, Question("objetivo_carga", "¿Qué carga debe soportar (usuarios concurrentes, peticiones por segundo)?", "Define la meta medible.")),
        (Complexity.LOW, Q_ENGINE_CHANGE),
        (Complexity.MEDIUM, Question("metricas_actuales", "¿Qué métricas tienes hoy (tiempos de respuesta, uso de CPU y base de datos)?", "Da la línea base para comparar.")),
        (Complexity.MEDIUM, Question("ventana_mantenimiento", "¿Hay ventana de mantenimiento o debe hacerse sin cortes?", "Define cómo despliega Orbit.")),
        (Complexity.HIGH, Question("presupuesto_infra", "¿Cuál es el presupuesto de infraestructura?", "Limita las opciones (réplicas, caché, regiones).")),
        (Complexity.HIGH, Question("multi_region", "¿Los usuarios están en varias regiones o países?", "Puede requerir despliegue multi-región.")),
    ],
    RequestType.ENHANCEMENT: [
        (Complexity.LOW, Question("funcionalidad", "Describe la funcionalidad: qué debe poder hacer el usuario que hoy no puede.", "Define el alcance exacto.")),
        (Complexity.LOW, Question("criterios_aceptacion", "¿Cómo sabremos que está terminada (criterios de aceptación)?", "Prism los usa para validar.")),
        (Complexity.MEDIUM, Question("usuarios_afectados", "¿Qué roles o usuarios usan o se ven afectados por el cambio?", "Define permisos y pruebas.")),
        (Complexity.MEDIUM, Question("impacto_datos", "¿El cambio modifica datos existentes o su estructura?", "Define si Nexus necesita migraciones.")),
        (Complexity.HIGH, Question("compatibilidad", "¿Hay integraciones o clientes que dependan del comportamiento actual?", "Evita romper consumidores existentes.")),
        (Complexity.HIGH, Question("plazo", "¿Para cuándo se necesita?", "Permite dividir en entregas.")),
    ],
    RequestType.BUGFIX: [
        (Complexity.LOW, Question("pasos_reproducir", "¿Cuáles son los pasos para reproducir el error?", "Sin reproducirlo no se puede corregir con seguridad.")),
        (Complexity.LOW, Question("esperado_vs_actual", "¿Qué debería pasar y qué pasa en realidad (mensaje de error incluido)?", "Define cuándo está corregido.")),
        (Complexity.LOW, Question("severidad", "¿Qué tan grave es: bloqueante, alta, media o baja?", "Decide si va como hotfix.")),
        (Complexity.MEDIUM, Question("entorno", "¿En qué entorno ocurre (producción, pruebas) y en qué versión?", "Acota la causa.")),
        (Complexity.MEDIUM, Question("desde_cuando", "¿Desde cuándo ocurre? ¿Empezó tras un despliegue?", "Puede apuntar al cambio que lo causó.")),
    ],
}

ALWAYS_INCLUDED = (VECTOR, PRISM, ORBIT)
INCLUDED_BY_TYPE: Dict[RequestType, Tuple[AgentProfile, ...]] = {
    RequestType.NEW_APP: (NEXUS, SENTINEL, ARGUS),
    RequestType.SCALE: (NEXUS, ARGUS),
}
PLAN_ORDER = (NEXUS, MATRIX, SENTINEL, SYNAPSE, INSIGHT, AURORA, GENESIS, VECTOR, PRISM, ORBIT, ARGUS)
DEPENDENCIES: Dict[str, Tuple[AgentProfile, ...]] = {
    NEXUS.codename: (),
    MATRIX.codename: (NEXUS,),
    SENTINEL.codename: (NEXUS, MATRIX),
    SYNAPSE.codename: (NEXUS, MATRIX, SENTINEL),
    INSIGHT.codename: (NEXUS,),
    AURORA.codename: (),
    GENESIS.codename: (NEXUS,),
    VECTOR.codename: (NEXUS, MATRIX, SENTINEL, SYNAPSE, INSIGHT, AURORA, GENESIS),
    PRISM.codename: (VECTOR,),
    ORBIT.codename: (PRISM,),
    ARGUS.codename: (ORBIT,),
}

DEFAULT_ACTIONS: Dict[str, str] = {
    NEXUS.codename: "Diseñar o ajustar el modelo de datos, índices y migraciones.",
    MATRIX.codename: "Traducir los requisitos en reglas de negocio validadas.",
    SYNAPSE.codename: "Definir contratos de API e integraciones externas.",
    INSIGHT.codename: "Diseñar reportes, KPIs y dashboards.",
    AURORA.codename: "Diseñar flujos de usuario, pantallas y componentes accesibles.",
    GENESIS.codename: "Diseñar los componentes de IA requeridos.",
    VECTOR.codename: "Implementar los cambios siguiendo los diseños aprobados.",
    PRISM.codename: "Validar con pruebas unitarias, de integración y de seguridad.",
    ORBIT.codename: "Desplegar a producción con plan de reversión.",
    SENTINEL.codename: "Definir autenticación, roles, permisos y auditoría; exigir MFA a los roles sensibles.",
    ARGUS.codename: "Configurar métricas, sondas de salud y alertas; verificar el SLA después del despliegue.",
}

TYPE_ACTIONS: Dict[RequestType, Dict[str, str]] = {
    RequestType.NEW_APP: {
        NEXUS.codename: ("Registrar la aplicación en kinetix con {modelo} en {motor}, crear su base de datos independiente "
                         "y desplegar tablas y migraciones según ese modelo. Las tablas quedan en formato portable para "
                         "poder cambiar de motor si la aplicación escala."),
        AURORA.codename: ("Diseñar el sistema de diseño y las pantallas: shell con navegación, tablero, listados con "
                          "filtros y exportación, formularios por secciones, detalle y configuración."),
    },
    RequestType.SCALE: {
        NEXUS.codename: "Analizar consultas lentas; proponer índices, particionamiento y pools de conexión.",
        SYNAPSE.codename: "Agregar caché y rate limiting en las APIs más cargadas.",
        VECTOR.codename: "Optimizar el código del cuello de botella identificado.",
        PRISM.codename: "Ejecutar pruebas de carga contra el objetivo acordado.",
        ORBIT.codename: "Desplegar de forma escalonada y vigilar métricas.",
        ARGUS.codename: "Comparar latencia, errores y recursos contra la línea base y el objetivo de carga.",
    },
    RequestType.ENHANCEMENT: {
        VECTOR.codename: "Implementar la funcionalidad según los criterios de aceptación.",
        PRISM.codename: "Validar criterios de aceptación y ejecutar pruebas de regresión.",
    },
    RequestType.BUGFIX: {
        VECTOR.codename: "Reproducir el error, identificar la causa raíz y corregirla.",
        PRISM.codename: "Agregar una prueba que reproduzca el error y ejecutar regresión.",
        ORBIT.codename: "Desplegar la corrección (hotfix si la severidad es bloqueante o alta).",
        SENTINEL.codename: "Revisar el flujo de autenticación o permisos afectado y su rastro en la auditoría.",
    },
}


# ============================================================================
# EJECUCIÓN POR SPRINTS (regla de la fábrica: complejidad media o alta)
# ============================================================================

SPRINT_COMPLEXITIES = frozenset({Complexity.MEDIUM, Complexity.HIGH})
SPRINT_EXIT_CRITERIA = ("Entregable demostrado, pruebas de Prism en verde y aprobación humana para cerrar el sprint; "
                        "el siguiente sprint solo inicia cuando un humano lo decide.")
Q_NEW_APP_ID = Question(
    "id_aplicacion",
    "¿Qué identificador corto tendrá la aplicación (minúsculas y '_', p. ej. 'talleres')?",
    "Los proyectos de complejidad media o alta se ejecutan por sprints identificados por aplicación; "
    "también nombra su base en Nexus.",
)
_SLUG = re.compile(r"[^a-z0-9]+")


def sprint_id(aplicacion: str, numero: int) -> str:
    return f"{aplicacion}-sprint-{numero:02d}"


def app_slug(answer: str) -> Optional[str]:
    """Identificador válido para Nexus (^[a-z][a-z0-9_]{1,29}$) o None si la respuesta no sirve."""
    slug = _SLUG.sub("_", _normalize(answer)).strip("_")[:30].rstrip("_")
    if slug in ("no_aplica", "no_se", "ninguno") or not re.fullmatch(r"[a-z][a-z0-9_]{1,29}", slug):
        return None
    return slug


SprintTask = Tuple[AgentProfile, str]
# clave, nombre, objetivo, entregable, tareas
SprintSpec = Tuple[str, str, str, str, Tuple[SprintTask, ...]]

CAPABILITY_SPRINTS: Dict[str, SprintSpec] = {
    "datos": ("datos", "Modelo de datos completo", "Completar tablas, índices y migraciones de todos los módulos.",
              "Migraciones desplegadas y repositorios probados.", (
                  (NEXUS, "Registrar las tablas restantes como migraciones portables y desplegarlas."),
                  (VECTOR, "Implementar repositorios y servicios sobre las tablas nuevas."),
                  (PRISM, "Pruebas de integración de la capa de datos."))),
    "reglas": ("reglas", "Reglas de negocio", "Llevar las reglas de negocio a validaciones ejecutables.",
               "Reglas validadas e implementadas con sus pruebas.", (
                   (MATRIX, "Traducir los requisitos en reglas de negocio validadas y resolver conflictos."),
                   (VECTOR, "Implementar las reglas en la capa de servicios."),
                   (PRISM, "Pruebas de cada regla, incluidas sus excepciones."))),
    "seguridad": ("seguridad", "Seguridad y permisos", "Ajustar autenticación, roles, permisos y auditoría.",
                  "Flujos de acceso protegidos y auditados.", (
                      (SENTINEL, DEFAULT_ACTIONS[SENTINEL.codename]),
                      (VECTOR, "Aplicar los permisos en endpoints y pantallas."),
                      (PRISM, "Pruebas de autorización y de los controles OWASP aplicables."))),
    "integraciones": ("integraciones", "Integraciones y APIs", "Conectar la aplicación con los sistemas externos.",
                      "Contratos OpenAPI publicados e integraciones funcionando.", (
                          (SYNAPSE, "Definir contratos de API e integraciones externas con seguridad y rate limiting."),
                          (VECTOR, "Implementar los clientes e integraciones definidos."),
                          (PRISM, "Pruebas de contrato e integración contra dobles de los sistemas externos."))),
    "interfaz": ("interfaz", "Interfaz de usuario", "Construir las pantallas y flujos principales.",
                 "Pantallas navegables y accesibles (WCAG AA).", (
                     (AURORA, "Diseñar flujos de usuario, pantallas y componentes accesibles."),
                     (VECTOR, "Implementar las pantallas con el sistema de diseño."),
                     (PRISM, "Pruebas E2E de los flujos principales y revisión de accesibilidad."))),
    "reportes": ("reportes", "Reportes y analítica", "Entregar los reportes, KPIs y dashboards acordados.",
                 "Dashboards con datos reales y KPIs verificados.", (
                     (INSIGHT, DEFAULT_ACTIONS[INSIGHT.codename]),
                     (VECTOR, "Implementar consultas y vistas de los reportes."),
                     (PRISM, "Validar los KPIs contra datos de prueba conocidos."))),
    "ia": ("ia", "Componentes de IA", "Incorporar los componentes de IA requeridos.",
           "Componentes de IA integrados con métricas de calidad.", (
               (GENESIS, DEFAULT_ACTIONS[GENESIS.codename]),
               (VECTOR, "Integrar los componentes de IA en la aplicación."),
               (PRISM, "Evaluar la calidad de las respuestas y los casos límite."))),
}
NEW_APP_CAPABILITY_ORDER = ("reglas", "integraciones", "interfaz", "reportes", "ia")
CHANGE_CAPABILITY_ORDER = ("datos", "reglas", "seguridad", "integraciones", "interfaz", "reportes", "ia")

COMPLIANCE_SPRINT: SprintSpec = (
    "cumplimiento", "Cumplimiento y auditoría", "Cubrir la normativa aplicable con reglas, controles y auditoría.",
    "Evidencia de cumplimiento revisada.", (
        (MATRIX, "Convertir la normativa en reglas obligatorias con sus excepciones auditadas."),
        (SENTINEL, "Asegurar auditoría completa, retención de registros y MFA en roles sensibles."),
        (PRISM, "Auditoría de seguridad OWASP y verificación de los controles normativos.")))
PERFORMANCE_SPRINT: SprintSpec = (
    "rendimiento", "Rendimiento y carga", "Garantizar el volumen y la concurrencia esperados.",
    "Pruebas de carga que cumplen el objetivo.", (
        (NEXUS, "Revisar índices, particionamiento y planes de consulta para el volumen esperado."),
        (PRISM, "Ejecutar pruebas de carga contra el objetivo de concurrencia."),
        (ARGUS, "Medir la línea base de latencia, errores y recursos.")))
PILOT_SPRINT: SprintSpec = (
    "piloto", "Piloto controlado", "Validar la aplicación con usuarios reales en un entorno controlado.",
    "Piloto aprobado por el negocio.", (
        (ORBIT, "Desplegar en un entorno de piloto con plan de reversión."),
        (PRISM, "Pruebas de aceptación con los usuarios del piloto."),
        (ARGUS, "Vigilar errores y uso durante el piloto.")))
RELEASE_SPRINT: SprintSpec = (
    "salida", "Salida a producción", "Estabilizar, desplegar y dejar la aplicación vigilada.",
    "Aplicación en producción con monitoreo y SLA verificado.", (
        (PRISM, "Regresión completa y validación de cobertura mínima."),
        (ORBIT, DEFAULT_ACTIONS[ORBIT.codename]),
        (ARGUS, DEFAULT_ACTIONS[ARGUS.codename])))


def _sprint_specs(request: "OrchestrationRequest", corpus: str) -> List[SprintSpec]:
    """Sprints viables en orden lógico: fundaciones, un sprint por capacidad y salida."""
    caps = set(request.capabilities)
    high = request.complexity == Complexity.HIGH
    nexus_action = TYPE_ACTIONS[RequestType.NEW_APP][NEXUS.codename]
    if request.request_type == RequestType.NEW_APP:
        specs: List[SprintSpec] = [(
            "fundaciones", "Fundaciones", "Dejar lista la base técnica: datos, seguridad y esqueleto del proyecto.",
            "Aplicación registrada en Nexus, autenticación funcionando y pipeline de CI en verde.", (
                (NEXUS, nexus_action),
                (SENTINEL, DEFAULT_ACTIONS[SENTINEL.codename]),
                (VECTOR, "Crear el esqueleto del proyecto (clean architecture) con autenticación integrada y CI."),
                (PRISM, "Configurar pruebas automáticas y cobertura mínima en CI.")))]
        specs.extend(CAPABILITY_SPRINTS[c] for c in NEW_APP_CAPABILITY_ORDER if c in caps)
        if high and _contains_any(corpus, COMPLIANCE):
            specs.append(COMPLIANCE_SPRINT)
        if high and _contains_any(corpus, HIGH_VOLUME):
            specs.append(PERFORMANCE_SPRINT)
        if high:
            specs.append(PILOT_SPRINT)
        specs.append(RELEASE_SPRINT)
        return specs
    if request.request_type == RequestType.SCALE:
        specs = [("diagnostico", "Diagnóstico y línea base", "Ubicar el cuello de botella con métricas.",
                  "Línea base medida y cuello de botella identificado.", (
                      (ARGUS, "Medir la línea base de latencia, errores y recursos."),
                      (NEXUS, "Analizar consultas lentas y uso de la base de datos.")))]
        if request.engine_change:
            label = DB_ENGINE_LABELS[request.engine_change]
            specs.append(("cambio_motor", f"Cambio de motor a {label}",
                          "Pasar la aplicación al motor nuevo de forma revertible.",
                          f"Aplicación funcionando en {label} con sus datos copiados.", (
                              (NEXUS, f"Revisar bloqueos (cambio-motor?vista_previa=true), registrar equivalentes, "
                                      f"desplegar el esquema en {label} y copiar los datos."),
                              (PRISM, "Validar la aplicación sobre el motor nuevo antes de completar el cambio."))))
        specs.append(("optimizacion", "Optimización", "Atacar el cuello de botella identificado.",
                      "Mejoras implementadas y medidas.", tuple(
                          (agent, TYPE_ACTIONS[RequestType.SCALE][agent.codename]) for agent in (NEXUS, SYNAPSE, VECTOR))))
        specs.append(("salida", "Pruebas de carga y salida", "Comprobar el objetivo de carga y desplegar.",
                      "Objetivo de carga cumplido en producción.", tuple(
                          (agent, TYPE_ACTIONS[RequestType.SCALE][agent.codename]) for agent in (PRISM, ORBIT, ARGUS))))
        return specs
    if request.request_type == RequestType.ENHANCEMENT:
        specs = [("analisis", "Análisis y diseño del cambio", "Acordar el diseño técnico y las pruebas de aceptación.",
                  "ADR del cambio y pruebas de aceptación definidas.", (
                      (VECTOR, "Analizar el impacto en el código y documentar el diseño técnico (ADR)."),
                      (PRISM, "Definir las pruebas de aceptación a partir de los criterios.")))]
        specs.extend(CAPABILITY_SPRINTS[c] for c in CHANGE_CAPABILITY_ORDER if c in caps)
        if len(specs) == 1:
            specs.append(("construccion", "Construcción", "Implementar la funcionalidad.", "Funcionalidad implementada.", (
                (VECTOR, TYPE_ACTIONS[RequestType.ENHANCEMENT][VECTOR.codename]),
                (PRISM, TYPE_ACTIONS[RequestType.ENHANCEMENT][PRISM.codename]))))
        specs.append(("salida", "Validación y despliegue", "Regresión y despliegue del cambio.", "Cambio en producción.", (
            (PRISM, "Regresión completa sobre los flujos afectados."),
            (ORBIT, DEFAULT_ACTIONS[ORBIT.codename]))))
        return specs
    bugfix = TYPE_ACTIONS[RequestType.BUGFIX]
    diagnosis: Tuple[SprintTask, ...] = ((VECTOR, bugfix[VECTOR.codename]), (PRISM, bugfix[PRISM.codename]))
    if "seguridad" in caps:
        diagnosis += ((SENTINEL, bugfix[SENTINEL.codename]),)
    return [("diagnostico", "Diagnóstico y corrección", "Reproducir el error y corregir su causa raíz.",
             "Prueba que reproduce el error, ahora en verde.", diagnosis),
            ("salida", "Regresión y despliegue", "Asegurar que nada más se rompió y desplegar.", "Corrección en producción.", (
                (PRISM, "Regresión completa."), (ORBIT, bugfix[ORBIT.codename])))]


def _normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def _contains_any(text: str, keywords: Tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(k)}\b", text) for k in keywords)


class OrchestratorAgent:
    """Cortex: evalúa solicitudes, pregunta lo necesario y propone planes delegados."""

    def __init__(self) -> None:
        self.name = CORTEX.codename
        self.version = "0.2.0"
        self._requests: Dict[str, OrchestrationRequest] = {}
        logger.info("✅ %s v%s initialized", self.name, self.version)

    # ------------------------------------------------------------------ API

    def submit(
        self,
        descripcion: str,
        app_id: Optional[str] = None,
        request_type: Optional[RequestType] = None,
    ) -> OrchestrationRequest:
        if not descripcion or not descripcion.strip():
            raise ValueError("La descripción de la solicitud es obligatoria.")
        request = OrchestrationRequest(
            id=f"req-{uuid.uuid4().hex[:8]}",
            descripcion=descripcion.strip(),
            app_id=app_id.strip() if app_id else None,
            explicit_type=request_type,
        )
        self._evaluate(request)
        self._requests[request.id] = request
        return request

    def answer(self, request_id: str, answers: Dict[str, str]) -> OrchestrationRequest:
        request = self.get(request_id)
        if request.status in (RequestStatus.APPROVED, RequestStatus.COMPLETED):
            raise ValueError("La solicitud ya fue aprobada; crea una nueva para cambiar el alcance.")
        for key, value in answers.items():
            if value and value.strip():
                request.answers[key] = value.strip()
        if request.answers.get(Q_APP.id) and not request.app_id:
            request.app_id = request.answers[Q_APP.id]
        self._evaluate(request)
        return request

    def approve(self, request_id: str, approved_by: str) -> OrchestrationRequest:
        request = self.get(request_id)
        if request.status != RequestStatus.PLAN_PROPOSED:
            raise ValueError("Solo se puede aprobar una solicitud con plan propuesto.")
        if not approved_by or not approved_by.strip():
            raise ValueError("Indica quién aprueba el plan.")
        request.status = RequestStatus.APPROVED
        request.approved_by = approved_by.strip()
        request.approved_at = datetime.utcnow().isoformat()
        if not request.sprints:
            for task in request.plan:
                task.status = TaskStatus.READY_TO_DELEGATE
            return request
        for task in request.plan:
            task.status = TaskStatus.BY_SPRINT
        for sprint in request.sprints:
            sprint.status = SprintStatus.PENDING
            for task in sprint.tareas:
                task.status = TaskStatus.WAITING_SPRINT
        return request

    # ------------------------------------------------------------- sprints

    def _sprint(self, request_id: str, numero: int) -> Tuple[OrchestrationRequest, Sprint]:
        request = self.get(request_id)
        if not request.sprints:
            raise ValueError("Esta solicitud no se ejecuta por sprints (complejidad baja).")
        if request.status in (RequestStatus.NEEDS_CLARIFICATION, RequestStatus.PLAN_PROPOSED):
            raise ValueError("Aprueba el plan antes de iniciar sprints.")
        if not 1 <= numero <= len(request.sprints):
            raise KeyError(f"{request_id}/sprint/{numero}")
        return request, request.sprints[numero - 1]

    def start_sprint(self, request_id: str, numero: int, started_by: str) -> OrchestrationRequest:
        """Un humano decide cuándo continuar: solo se inicia si el sprint anterior está completado."""
        if not started_by or not started_by.strip():
            raise ValueError("Indica quién inicia el sprint.")
        request, sprint = self._sprint(request_id, numero)
        if sprint.status != SprintStatus.PENDING:
            raise ValueError(f"El {sprint.etiqueta} está {sprint.status.value}; solo se inicia un sprint pendiente.")
        previous = request.sprints[numero - 2] if numero > 1 else None
        if previous and previous.status != SprintStatus.DONE:
            raise ValueError(f"Completa primero el {previous.etiqueta} ({previous.id}).")
        sprint.status = SprintStatus.IN_PROGRESS
        sprint.started_by, sprint.started_at = started_by.strip(), datetime.utcnow().isoformat()
        for task in sprint.tareas:
            task.status = TaskStatus.READY_TO_DELEGATE
        return request

    def complete_sprint(self, request_id: str, numero: int, completed_by: str,
                        notas: Optional[str] = None) -> OrchestrationRequest:
        if not completed_by or not completed_by.strip():
            raise ValueError("Indica quién da por completado el sprint.")
        request, sprint = self._sprint(request_id, numero)
        if sprint.status != SprintStatus.IN_PROGRESS:
            raise ValueError(f"El {sprint.etiqueta} está {sprint.status.value}; solo se completa un sprint en curso.")
        sprint.status = SprintStatus.DONE
        sprint.completed_by, sprint.completed_at = completed_by.strip(), datetime.utcnow().isoformat()
        sprint.notas = notas.strip() if notas and notas.strip() else None
        for task in sprint.tareas:
            task.status = TaskStatus.DONE
        if all(s.status == SprintStatus.DONE for s in request.sprints):
            request.status = RequestStatus.COMPLETED
            for task in request.plan:
                task.status = TaskStatus.DONE
        return request

    def sprints_for_app(self, aplicacion: str) -> List[Tuple[OrchestrationRequest, Sprint]]:
        """Todos los sprints de una aplicación, solicitud por solicitud, en orden de creación."""
        key = aplicacion.strip().lower()
        return [(r, s) for r in self._requests.values() if (r.aplicacion or "").lower() == key for s in r.sprints]

    def get(self, request_id: str) -> OrchestrationRequest:
        if request_id not in self._requests:
            raise KeyError(request_id)
        return self._requests[request_id]

    def list_requests(self) -> List[OrchestrationRequest]:
        return list(self._requests.values())

    # ------------------------------------------------------------ evaluación

    def _evaluate(self, request: OrchestrationRequest) -> None:
        corpus = _normalize(" ".join([request.descripcion, *request.answers.values()]))

        request.request_type = self._resolve_type(request, _normalize(request.descripcion))
        if request.request_type is None:
            request.answers.pop(Q_TYPE.id, None)
            request.capabilities, request.complexity, request.plan = [], None, []
            request.pending_questions = [Q_TYPE]
            request.status = RequestStatus.NEEDS_CLARIFICATION
            return

        request.capabilities = [
            name for name, (_, keywords) in CAPABILITIES.items() if _contains_any(corpus, keywords)
        ]
        request.complexity = self._complexity(request.request_type, request.capabilities, corpus)
        request.data_model = None
        if request.request_type == RequestType.NEW_APP and Q_DATA_MODEL.id in request.answers:
            request.data_model = data_model_from(request.answers[Q_DATA_MODEL.id])
            if request.data_model is None:
                request.answers.pop(Q_DATA_MODEL.id)
        self._resolve_engine(request, corpus)
        self._resolve_new_app_id(request)
        request.pending_questions = self._questions_for(request)

        if request.pending_questions:
            request.plan, request.sprints = [], []
            request.status = RequestStatus.NEEDS_CLARIFICATION
        else:
            request.plan = self._build_plan(request.request_type, request.capabilities, request.data_model,
                                            request.db_engine, request.engine_change)
            request.sprints = self._build_sprints(request, corpus)
            request.status = RequestStatus.PLAN_PROPOSED

    @staticmethod
    def _uses_sprints(request: OrchestrationRequest) -> bool:
        return request.complexity in SPRINT_COMPLEXITIES

    def _resolve_new_app_id(self, request: OrchestrationRequest) -> None:
        request.new_app_id = None
        if request.request_type != RequestType.NEW_APP or Q_NEW_APP_ID.id not in request.answers:
            return
        answer = request.answers[Q_NEW_APP_ID.id]
        slug = app_slug(answer)
        if slug is None and _contains_any(_normalize(answer), ("no aplica", "no se", "ninguno")):
            slug = f"app_{request.id.removeprefix('req-')}"
        if slug is None:
            request.answers.pop(Q_NEW_APP_ID.id)
        request.new_app_id = slug

    def _build_sprints(self, request: OrchestrationRequest, corpus: str) -> List[Sprint]:
        if not self._uses_sprints(request):
            return []
        specs = _sprint_specs(request, corpus)
        aplicacion = request.aplicacion or f"app_{request.id.removeprefix('req-')}"
        sprints = []
        for numero, (clave, nombre, objetivo, entregable, tasks) in enumerate(specs, start=1):
            codenames = {agent.codename for agent, _ in tasks}
            sprints.append(Sprint(
                numero=numero, total=len(specs), aplicacion=aplicacion, clave=clave, nombre=nombre,
                objetivo=objetivo, entregable=entregable,
                tareas=[PlanTask(
                    id=f"s{numero:02d}_{agent.codename.lower()}", agent=agent,
                    accion=action
                    .replace("{modelo}", DATA_MODEL_LABELS.get(request.data_model or "", "el modelo de datos acordado"))
                    .replace("{motor}", DB_ENGINE_LABELS.get(request.db_engine or "", "el motor acordado")),
                    depends_on=[f"s{numero:02d}_{dep.codename.lower()}" for dep in DEPENDENCIES[agent.codename]
                                if dep.codename in codenames],
                ) for agent, action in tasks],
            ))
        return sprints

    @staticmethod
    def _resolve_engine(request: OrchestrationRequest, corpus: str) -> None:
        request.db_engine = request.db_engine_reason = request.engine_change = None
        if request.request_type == RequestType.NEW_APP and Q_DB_ENGINE.id in request.answers:
            answer = request.answers[Q_DB_ENGINE.id]
            engine = db_engine_from(answer)
            if engine:
                request.db_engine, request.db_engine_reason = engine, "Elegido en la solicitud"
            elif _contains_any(_normalize(answer), DB_ENGINE_RECOMMEND):
                request.db_engine, request.db_engine_reason = recommend_db_engine(corpus)
            else:
                request.answers.pop(Q_DB_ENGINE.id)
        if request.request_type == RequestType.SCALE and Q_ENGINE_CHANGE.id in request.answers:
            request.engine_change = db_engine_from(request.answers[Q_ENGINE_CHANGE.id], last=True)

    def _resolve_type(self, request: OrchestrationRequest, description: str) -> Optional[RequestType]:
        if request.explicit_type:
            return request.explicit_type

        typed_answer = request.answers.get(Q_TYPE.id)
        if typed_answer:
            normalized = _normalize(typed_answer)
            for hint, request_type in TYPE_ANSWER_HINTS:
                if hint in normalized:
                    return request_type
            return None

        matches = {t for t, keywords in TYPE_KEYWORDS.items() if _contains_any(description, keywords)}
        if request.app_id:
            matches.discard(RequestType.NEW_APP)
        elif RequestType.NEW_APP in matches:
            return RequestType.NEW_APP
        return matches.pop() if len(matches) == 1 else None

    @staticmethod
    def _complexity(request_type: RequestType, capabilities: List[str], corpus: str) -> Complexity:
        score = TYPE_BASE_SCORE[request_type] + len(capabilities)
        score += sum(2 for signals in (MULTI_TENANT, HIGH_VOLUME, COMPLIANCE) if _contains_any(corpus, signals))
        if _contains_any(corpus, ("web",)) and _contains_any(corpus, ("movil", "android", "ios")):
            score += 1
        if score <= 2:
            return Complexity.LOW
        if score <= 5:
            return Complexity.MEDIUM
        return Complexity.HIGH

    @staticmethod
    def _questions_for(request: OrchestrationRequest) -> List[Question]:
        questions: List[Question] = []
        if request.request_type != RequestType.NEW_APP and not request.app_id:
            questions.append(Q_APP)
        if request.request_type in (RequestType.NEW_APP, RequestType.ENHANCEMENT) and not request.capabilities:
            questions.append(Q_SCOPE)
        if request.request_type == RequestType.NEW_APP and request.complexity in SPRINT_COMPLEXITIES:
            questions.append(Q_NEW_APP_ID)
        level = TIER_ORDER[request.complexity]
        questions.extend(
            q for tier, q in QUESTION_BANK[request.request_type] if TIER_ORDER[tier] <= level
        )
        return [q for q in questions if q.id not in request.answers]

    @staticmethod
    def _build_plan(request_type: RequestType, capabilities: List[str], data_model: Optional[str] = None,
                    db_engine: Optional[str] = None, engine_change: Optional[str] = None) -> List[PlanTask]:
        included = {CAPABILITIES[name][0].codename for name in capabilities}
        included.update(agent.codename for agent in ALWAYS_INCLUDED)
        included.update(agent.codename for agent in INCLUDED_BY_TYPE.get(request_type, ()))

        actions = dict(TYPE_ACTIONS.get(request_type, {}))
        if engine_change:
            actions[NEXUS.codename] = (
                f"Cambiar el motor de la aplicación a {DB_ENGINE_LABELS[engine_change]}: revisar bloqueos con "
                "cambio-motor?vista_previa=true, registrar equivalentes de las migraciones SQL manuales, desplegar el "
                "esquema, copiar los datos tabla por tabla, validar y completar el cambio (revertible hasta completarlo). "
                + actions.get(NEXUS.codename, DEFAULT_ACTIONS[NEXUS.codename])
            )
        plan: List[PlanTask] = []
        for agent in PLAN_ORDER:
            if agent.codename not in included:
                continue
            depends_on = [
                f"{dep.codename.lower()}_01" for dep in DEPENDENCIES[agent.codename] if dep.codename in included
            ]
            plan.append(
                PlanTask(
                    id=f"{agent.codename.lower()}_01",
                    agent=agent,
                    accion=actions.get(agent.codename, DEFAULT_ACTIONS[agent.codename])
                    .replace("{modelo}", DATA_MODEL_LABELS.get(data_model or "", "el modelo de datos acordado"))
                    .replace("{motor}", DB_ENGINE_LABELS.get(db_engine or "", "el motor acordado")),
                    depends_on=depends_on,
                )
            )
        return plan
