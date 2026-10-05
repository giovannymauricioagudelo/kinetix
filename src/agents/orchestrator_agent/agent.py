"""
Cortex (OrchestratorAgent) — punto de entrada de la fábrica de aplicaciones.

Evalúa cada solicitud (aplicación nueva, escalabilidad, mejora o corrección),
calcula su complejidad, hace las preguntas que correspondan a ese nivel y solo
entonces propone un plan que reparte el trabajo entre los demás agentes.
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


class TaskStatus(str, Enum):
    PENDING_APPROVAL = "pendiente_aprobacion"
    READY_TO_DELEGATE = "lista_para_delegar"


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

    def to_dict(self) -> Dict[str, object]:
        if self.status == RequestStatus.NEEDS_CLARIFICATION:
            next_step = "Responde las preguntas pendientes para que Cortex pueda proponer un plan."
        elif self.status == RequestStatus.PLAN_PROPOSED:
            next_step = "Revisa el plan y apruébalo; Cortex no delega nada sin aprobación humana."
        else:
            next_step = "Plan aprobado: las tareas están listas para delegarse a cada agente."
        return {
            "id": self.id,
            "descripcion": self.descripcion,
            "app_id": self.app_id,
            "tipo_solicitud": self.request_type.value if self.request_type else None,
            "complejidad": self.complexity.value if self.complexity else None,
            "capacidades_detectadas": self.capabilities,
            "modelo_datos": self.data_model,
            "estado": self.status.value,
            "preguntas_pendientes": [q.to_dict() for q in self.pending_questions],
            "respuestas": self.answers,
            "plan": [t.to_dict() for t in self.plan],
            "aprobado_por": self.approved_by,
            "aprobado_en": self.approved_at,
            "creado_en": self.created_at,
            "siguiente_paso": next_step,
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

TIER_ORDER = {Complexity.LOW: 0, Complexity.MEDIUM: 1, Complexity.HIGH: 2}

QUESTION_BANK: Dict[RequestType, List[Tuple[Complexity, Question]]] = {
    RequestType.NEW_APP: [
        (Complexity.LOW, Question("objetivo", "¿Qué problema de negocio resuelve la aplicación?", "Define el alcance funcional.")),
        (Complexity.LOW, Question("usuarios_roles", "¿Quiénes la van a usar y con qué roles (administrador, cliente, técnico…)?", "Define permisos y flujos por rol.")),
        (Complexity.LOW, Question("plataformas", "¿En qué plataformas debe funcionar: web, móvil, escritorio o solo API?", "Define si interviene Aurora y qué entregables de interfaz.")),
        (Complexity.LOW, Q_DATA_MODEL),
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
        NEXUS.codename: ("Registrar la aplicación en kinetix con {modelo}, crear su base de datos independiente "
                         "y desplegar tablas y migraciones según ese modelo."),
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


def _normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def _contains_any(text: str, keywords: Tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(k)}\b", text) for k in keywords)


class OrchestratorAgent:
    """Cortex: evalúa solicitudes, pregunta lo necesario y propone planes delegados."""

    def __init__(self) -> None:
        self.name = CORTEX.codename
        self.version = "0.1.0"
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
        if request.status == RequestStatus.APPROVED:
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
        for task in request.plan:
            task.status = TaskStatus.READY_TO_DELEGATE
        return request

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
        request.pending_questions = self._questions_for(request)

        if request.pending_questions:
            request.plan = []
            request.status = RequestStatus.NEEDS_CLARIFICATION
        else:
            request.plan = self._build_plan(request.request_type, request.capabilities, request.data_model)
            request.status = RequestStatus.PLAN_PROPOSED

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
        level = TIER_ORDER[request.complexity]
        questions.extend(
            q for tier, q in QUESTION_BANK[request.request_type] if TIER_ORDER[tier] <= level
        )
        return [q for q in questions if q.id not in request.answers]

    @staticmethod
    def _build_plan(request_type: RequestType, capabilities: List[str],
                    data_model: Optional[str] = None) -> List[PlanTask]:
        included = {CAPABILITIES[name][0].codename for name in capabilities}
        included.update(agent.codename for agent in ALWAYS_INCLUDED)
        included.update(agent.codename for agent in INCLUDED_BY_TYPE.get(request_type, ()))

        actions = TYPE_ACTIONS.get(request_type, {})
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
                    accion=actions.get(agent.codename, DEFAULT_ACTIONS[agent.codename]).replace(
                        "{modelo}", DATA_MODEL_LABELS.get(data_model or "", "el modelo de datos acordado")),
                    depends_on=depends_on,
                )
            )
        return plan
