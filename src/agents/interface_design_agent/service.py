"""Casos de uso de Aurora: sistemas de diseño multiempresa con tokens versionados, componentes y accesibilidad WCAG."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional

from src.agents.common import iso, new_id, utcnow
from src.agents.interface_design_agent import design, exporters
from src.agents.interface_design_agent.design import DesignError
from src.agents.interface_design_agent.repository import DesignRepository, DesignSystem
from src.agents.security_agent.models import ConflictError, InvalidInputError, NotFoundError

VERSION = "1.0.0"
SYSTEM_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,99}$")
CSS_CLASS = re.compile(r"^[a-z][a-z0-9-]{0,40}$")


def _invalid(error: DesignError) -> InvalidInputError:
    return InvalidInputError(str(error))


class AuroraService:
    def __init__(self, repository: DesignRepository, clock: Callable = utcnow) -> None:
        self._repo = repository
        self._clock = clock

    def ping(self) -> None:
        self._repo.ping()

    @staticmethod
    def _view(system: DesignSystem, include_tokens: bool = True) -> Dict[str, Any]:
        view: Dict[str, Any] = {
            "id_sistema": system.id_sistema,
            "nombre": system.nombre,
            "version": system.version,
            "nivel_wcag": system.nivel_wcag,
            "estado": system.estado,
            "creado_por": system.creado_por,
            "fecha_creacion": iso(system.fecha_creacion),
            "fecha_modificacion": iso(system.fecha_modificacion),
            "total_componentes": len(system.componentes) or system.total_componentes,
        }
        if include_tokens:
            view["tokens"] = system.tokens
            view["componentes"] = system.componentes
        return view

    def _get(self, id_sistema: str, id_empresa: str) -> DesignSystem:
        system = self._repo.get(id_sistema, id_empresa)
        if system is None:
            raise NotFoundError(f"Sistema de diseño no encontrado: {id_sistema}")
        return system

    # ================================================================ sistemas

    def create_system(self, actor: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        name = str(data.get("nombre") or "").strip()
        if not SYSTEM_NAME.match(name):
            raise InvalidInputError("nombre: letras, números, espacio, '_', '.' o '-' (máx. 100)")
        level = data.get("nivel_wcag", "AA")
        if level not in design.WCAG_LEVELS:
            raise InvalidInputError("nivel_wcag debe ser A, AA o AAA")
        preset = data.get("paleta_base", "kinetix")
        if preset != "personalizada" and preset not in design.PRESETS:
            raise InvalidInputError(f"paleta_base debe ser {', '.join(design.PRESETS)} o personalizada")
        base = design.PRESETS.get(preset, {})
        primary = data.get("color_primario") or base.get("primary")
        secondary = data.get("color_secundario") or base.get("secondary") or primary
        if not primary:
            raise InvalidInputError("La paleta personalizada requiere color_primario")
        try:
            spacing = int(data.get("espaciado_base_px", 4))
            if not 2 <= spacing <= 16:
                raise DesignError("espaciado_base_px debe estar entre 2 y 16")
            tokens = design.build_tokens(
                primary, secondary, data.get("color_neutro"),
                font_family=data.get("tipografia") or "Inter, 'Segoe UI', Roboto, sans-serif",
                base_size_px=int(data.get("tamano_base_px", 16)),
                ratio=float(data.get("escala_tipografica", 1.25)),
                spacing_base_px=spacing,
            )
            components = [design.normalize_component(c) for c in design.DEFAULT_COMPONENTS]
        except (TypeError, ValueError) as e:
            raise InvalidInputError(str(e))
        now = self._clock()
        system = DesignSystem(
            id_sistema=new_id("sd"), nombre=name, id_empresa=id_empresa, nivel_wcag=level, tokens=tokens,
            creado_por=actor, fecha_creacion=now, fecha_modificacion=now, componentes=components,
        )
        if not self._repo.create(system):
            raise ConflictError(f"Ya existe un sistema de diseño llamado {name!r}")
        report = design.accessibility_report(tokens, components, level)
        return {
            **self._view(system),
            "tokens_generados": sum(1 for _ in design.token_leaves(tokens)),
            "accesibilidad": {"cumple": report["cumple"], "contraste_fallido": report["contraste_fallido"]},
        }

    def list_systems(self, id_empresa: str) -> Dict[str, Any]:
        systems = self._repo.list(id_empresa)
        return {"total": len(systems), "sistemas": [self._view(s, include_tokens=False) for s in systems]}

    def get_system(self, id_sistema: str, id_empresa: str) -> Dict[str, Any]:
        return self._view(self._get(id_sistema, id_empresa))

    def update_tokens(self, id_sistema: str, id_empresa: str, overrides: Dict[str, Any],
                      version: int, nivel_wcag: Optional[str] = None) -> Dict[str, Any]:
        system = self._get(id_sistema, id_empresa)
        if version != system.version:
            raise ConflictError(f"El sistema cambió (versión actual {system.version}); recarga y vuelve a intentar")
        level = nivel_wcag or system.nivel_wcag
        if level not in design.WCAG_LEVELS:
            raise InvalidInputError("nivel_wcag debe ser A, AA o AAA")
        try:
            tokens = design.merge_tokens(system.tokens, overrides or {})
        except DesignError as e:
            raise _invalid(e)
        if not self._repo.update_tokens(id_sistema, id_empresa, tokens, version, level, self._clock()):
            raise ConflictError("El sistema cambió mientras se guardaba; recarga y vuelve a intentar")
        return self.get_system(id_sistema, id_empresa)

    # ================================================================ componentes

    def upsert_component(self, id_sistema: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        system = self._get(id_sistema, id_empresa)
        try:
            component = design.normalize_component(data)
        except DesignError as e:
            raise _invalid(e)
        created = self._repo.upsert_component(system.id_sistema, component, self._clock())
        return {"componente": component, "creado": created,
                "problemas_accesibilidad": design.audit_component(component, system.nivel_wcag)}

    def delete_component(self, id_sistema: str, id_empresa: str, nombre: str) -> Dict[str, Any]:
        system = self._get(id_sistema, id_empresa)
        if not self._repo.delete_component(system.id_sistema, nombre):
            raise NotFoundError(f"Componente no encontrado: {nombre}")
        return {"eliminado": nombre}

    # ================================================================ accesibilidad y exportación

    def accessibility(self, id_sistema: str, id_empresa: str, nivel: Optional[str], aplicar: bool) -> Dict[str, Any]:
        system = self._get(id_sistema, id_empresa)
        level = nivel or system.nivel_wcag
        try:
            report = design.accessibility_report(system.tokens, system.componentes, level)
        except DesignError as e:
            raise _invalid(e)
        report["id_sistema"] = system.id_sistema
        report["version_evaluada"] = system.version
        if aplicar and report["correcciones_sugeridas"]:
            overrides = {"themes": report["correcciones_sugeridas"]}
            updated = self.update_tokens(id_sistema, id_empresa, overrides, system.version, level)
            after = design.accessibility_report(updated["tokens"], updated["componentes"], level)
            report["correcciones_aplicadas"] = True
            report["version_nueva"] = updated["version"]
            report["contraste_fallido_despues"] = after["contraste_fallido"]
            report["cumple_despues"] = after["cumple"]
        else:
            report["correcciones_aplicadas"] = False
        return report

    def export(self, id_sistema: str, id_empresa: str, fmt: str) -> Dict[str, Any]:
        system = self._get(id_sistema, id_empresa)
        try:
            content = exporters.export(system.tokens, fmt)
        except DesignError as e:
            raise _invalid(e)
        slug = re.sub(r"[^a-z0-9]+", "-", system.nombre.lower()).strip("-") or "tokens"
        return {
            "formato": fmt,
            "archivo": f"{slug}-v{system.version}.{exporters.EXTENSIONS[fmt]}",
            "tipo_contenido": exporters.MEDIA_TYPES[fmt],
            "contenido": content,
            "bytes": len(content.encode("utf-8")),
        }

    def layout(self, id_sistema: str, id_empresa: str, data: Dict[str, Any]) -> Dict[str, Any]:
        system = self._get(id_sistema, id_empresa)
        css_class = data.get("clase", "kx-layout")
        if not CSS_CLASS.match(css_class or ""):
            raise InvalidInputError("clase: minúsculas, números y '-' (máx. 40)")
        columns = {"mobile": data.get("columnas_movil", 1), "tablet": data.get("columnas_tablet", 6),
                   "desktop": data.get("columnas_escritorio", 12)}
        if not all(isinstance(v, int) and 1 <= v <= 24 for v in columns.values()):
            raise InvalidInputError("Las columnas deben ser enteros entre 1 y 24")
        max_width = data.get("ancho_maximo_px", 1280)
        if not isinstance(max_width, int) or not 320 <= max_width <= 3840:
            raise InvalidInputError("ancho_maximo_px debe estar entre 320 y 3840")
        try:
            return exporters.responsive_layout(system.tokens, data.get("tipo", "grid"), columns,
                                               data.get("espaciado", "md"), max_width, css_class)
        except DesignError as e:
            raise _invalid(e)

    def screen(self, id_sistema: str, id_empresa: str, tipo: str, nombre_app: str, idioma: str) -> Dict[str, Any]:
        system = self._get(id_sistema, id_empresa)
        if not 1 <= len(nombre_app or "") <= 80:
            raise InvalidInputError("nombre_app es obligatorio (máx. 80 caracteres)")
        try:
            return exporters.screen_html(system.tokens, tipo, nombre_app, idioma)
        except DesignError as e:
            raise _invalid(e)

    @staticmethod
    def contrast(color_texto: str, color_fondo: str) -> Dict[str, Any]:
        try:
            return design.contrast_report(color_texto, color_fondo)
        except DesignError as e:
            raise _invalid(e)
