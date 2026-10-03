"""
Motor de diseño de Aurora: color (WCAG 2.1), generación de tokens, temas claro/oscuro, validación de tokens
y auditoría de accesibilidad de tokens y componentes.
"""

from __future__ import annotations

import colorsys
import copy
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
SHORT_HEX = re.compile(r"^#[0-9A-Fa-f]{3}$")
DIMENSION = re.compile(r"^(0|\d{1,4}(\.\d{1,2})?(px|rem|em|%))$")
DURATION = re.compile(r"^\d{1,4}ms$")
FONT_FAMILY = re.compile(r"^[A-Za-z0-9 ,'\"\-]{1,200}$")
SHADOW = re.compile(r"^(none|[0-9a-zA-Z#(),.\s%\-]{1,160})$")

STEPS = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900")
_LIGHTNESS = dict(zip(STEPS, (0.96, 0.90, 0.80, 0.70, 0.60, 0.50, 0.42, 0.34, 0.26, 0.17)))
PALETTES = ("primary", "secondary", "neutral", "success", "warning", "error", "info")
ROLES = (
    "background", "surface", "text", "text_muted", "primary", "on_primary", "secondary", "on_secondary",
    "error", "on_error", "success", "warning", "link", "error_text", "input_border", "border", "focus",
)
WCAG_LEVELS = ("A", "AA", "AAA")
LEVEL_RATIOS: Dict[str, Dict[str, float]] = {
    "AA": {"texto": 4.5, "texto_grande": 3.0, "no_texto": 3.0},
    "AAA": {"texto": 7.0, "texto_grande": 4.5, "no_texto": 3.0},
}
BREAKPOINTS = {"mobile": "320px", "tablet": "768px", "desktop": "1024px"}
PRESETS = {
    "material": {"primary": "#6750A4", "secondary": "#625B71"},
    "apple": {"primary": "#007AFF", "secondary": "#5856D6"},
    "kinetix": {"primary": "#1D4ED8", "secondary": "#0F766E"},
}
SEMANTIC_DEFAULTS = {"success": "#16A34A", "warning": "#D97706", "error": "#DC2626", "info": "#2563EB"}
DARK_TEXT = "#111827"
WHITE = "#FFFFFF"

# (rol de primer plano, rol de fondo, tipo de contraste, criterio WCAG)
CONTRAST_PAIRS: Tuple[Tuple[str, str, str, str], ...] = (
    ("text", "background", "texto", "1.4.3"),
    ("text", "surface", "texto", "1.4.3"),
    ("text_muted", "background", "texto", "1.4.3"),
    ("on_primary", "primary", "texto", "1.4.3"),
    ("on_secondary", "secondary", "texto", "1.4.3"),
    ("on_error", "error", "texto", "1.4.3"),
    ("link", "background", "texto", "1.4.3"),
    ("error_text", "background", "texto", "1.4.3"),
    ("primary", "background", "no_texto", "1.4.11"),
    ("input_border", "background", "no_texto", "1.4.11"),
    ("focus", "background", "no_texto", "2.4.7"),
)


class DesignError(ValueError):
    """Entrada de diseño inválida (color, token, componente)."""


# ============================================================================ color


def normalize_hex(value: str) -> str:
    raw = (value or "").strip()
    if SHORT_HEX.match(raw):
        raw = "#" + "".join(ch * 2 for ch in raw[1:])
    if not HEX.match(raw):
        raise DesignError(f"Color inválido: {value!r} (usa #RRGGBB)")
    return raw.upper()


def _rgb(color: str) -> Tuple[float, float, float]:
    color = normalize_hex(color)
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def _hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in (r, g, b))


def relative_luminance(color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    a, b = relative_luminance(foreground), relative_luminance(background)
    light, dark = max(a, b), min(a, b)
    return round((light + 0.05) / (dark + 0.05), 2)


def with_lightness(color: str, lightness: float, saturation: Optional[float] = None) -> str:
    h, _, s = colorsys.rgb_to_hls(*_rgb(color))
    return _hex(*colorsys.hls_to_rgb(h, max(0.0, min(1.0, lightness)), s if saturation is None else saturation))


def color_scale(base: str) -> Dict[str, str]:
    base = normalize_hex(base)
    scale = {step: with_lightness(base, lightness) for step, lightness in _LIGHTNESS.items()}
    scale["base"] = base
    return scale


def neutral_from(primary: str) -> str:
    h, _, _ = colorsys.rgb_to_hls(*_rgb(primary))
    return _hex(*colorsys.hls_to_rgb(h, 0.5, 0.08))


def best_on(background: str) -> str:
    return WHITE if contrast_ratio(WHITE, background) >= contrast_ratio(DARK_TEXT, background) else DARK_TEXT


def adjust_for_contrast(foreground: str, background: str, target: float) -> Optional[str]:
    """Variante de `foreground` con el mismo tono que alcanza `target` contra `background` (None si no existe)."""
    if contrast_ratio(foreground, background) >= target:
        return normalize_hex(foreground)
    h, l, s = colorsys.rgb_to_hls(*_rgb(foreground))
    darker = relative_luminance(background) > 0.18
    step = -0.01 if darker else 0.01
    current = l
    while 0.0 <= current <= 1.0:
        candidate = _hex(*colorsys.hls_to_rgb(h, current, s))
        if contrast_ratio(candidate, background) >= target:
            return candidate
        current += step
    return None


def contrast_report(foreground: str, background: str) -> Dict[str, Any]:
    foreground, background = normalize_hex(foreground), normalize_hex(background)
    ratio = contrast_ratio(foreground, background)
    return {
        "color_texto": foreground,
        "color_fondo": background,
        "relacion": ratio,
        "AA": {"texto": ratio >= 4.5, "texto_grande": ratio >= 3.0, "no_texto": ratio >= 3.0},
        "AAA": {"texto": ratio >= 7.0, "texto_grande": ratio >= 4.5},
        "sugerencia_AA": None if ratio >= 4.5 else adjust_for_contrast(foreground, background, 4.5),
        "sugerencia_AAA": None if ratio >= 7.0 else adjust_for_contrast(foreground, background, 7.0),
    }


# ============================================================================ tokens


def _themes(color: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    p, s, n, e = color["primary"], color["secondary"], color["neutral"], color["error"]
    light = {
        "background": WHITE, "surface": n["50"], "text": n["900"], "text_muted": n["700"],
        "primary": p["base"], "secondary": s["base"], "error": e["600"],
        "success": color["success"]["600"], "warning": color["warning"]["500"],
        "link": p["700"], "error_text": e["700"], "input_border": n["500"], "border": n["200"], "focus": p["600"],
    }
    dark = {
        "background": n["900"], "surface": n["800"], "text": n["50"], "text_muted": n["200"],
        "primary": p["300"], "secondary": s["300"], "error": e["300"],
        "success": color["success"]["300"], "warning": color["warning"]["300"],
        "link": p["200"], "error_text": e["200"], "input_border": n["400"], "border": n["700"], "focus": p["300"],
    }
    for theme in (light, dark):
        for role in ("primary", "secondary", "error"):
            theme[f"on_{role}"] = best_on(theme[role])
    return {"light": light, "dark": dark}


def typography(font_family: str, base_size_px: int, ratio: float) -> Dict[str, Any]:
    steps = {"xs": -2, "sm": -1, "base": 0, "lg": 1, "xl": 2, "2xl": 3, "3xl": 4, "4xl": 5}
    scale = {name: f"{round(base_size_px * ratio ** power)}px" for name, power in steps.items()}
    return {
        "font_family": font_family,
        "base_size_px": base_size_px,
        "ratio": ratio,
        "scale": scale,
        "roles": {"h1": "4xl", "h2": "3xl", "h3": "2xl", "h4": "xl", "body": "base", "caption": "sm"},
        "weights": {"regular": 400, "medium": 500, "bold": 700},
        "line_height": {"tight": 1.25, "normal": 1.5, "relaxed": 1.75},
    }


def build_tokens(primary: str, secondary: str, neutral: Optional[str] = None, *,
                 font_family: str = "Inter, 'Segoe UI', Roboto, sans-serif",
                 base_size_px: int = 16, ratio: float = 1.25, spacing_base_px: int = 4) -> Dict[str, Any]:
    primary, secondary = normalize_hex(primary), normalize_hex(secondary)
    color = {
        "primary": color_scale(primary),
        "secondary": color_scale(secondary),
        "neutral": color_scale(normalize_hex(neutral) if neutral else neutral_from(primary)),
        **{name: color_scale(value) for name, value in SEMANTIC_DEFAULTS.items()},
    }
    b = spacing_base_px
    tokens = {
        "color": color,
        "themes": _themes(color),
        "typography": typography(font_family, base_size_px, ratio),
        "spacing": {"xs": f"{b}px", "sm": f"{2 * b}px", "md": f"{4 * b}px", "lg": f"{6 * b}px",
                    "xl": f"{8 * b}px", "2xl": f"{12 * b}px", "3xl": f"{16 * b}px"},
        "radius": {"none": "0", "sm": "4px", "md": "8px", "lg": "16px", "full": "9999px"},
        "shadow": {
            "sm": "0 1px 2px rgba(0, 0, 0, 0.08)",
            "md": "0 4px 12px rgba(0, 0, 0, 0.12)",
            "lg": "0 12px 32px rgba(0, 0, 0, 0.16)",
        },
        "breakpoints": dict(BREAKPOINTS),
        "motion": {"fast": "150ms", "normal": "250ms", "slow": "400ms"},
    }
    validate_tokens(tokens)
    return tokens


def _number(low: float, high: float, integer: bool = False) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        return (not integer or isinstance(value, int)) and low <= value <= high
    return check


def _pattern(regex: re.Pattern) -> Callable[[Any], bool]:
    return lambda value: isinstance(value, str) and bool(regex.match(value))


def _one_of(options) -> Callable[[Any], bool]:
    return lambda value: value in options


_STEP_KEYS = (*STEPS, "base")
_SCALE_KEYS = ("xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl")
# (ruta con comodines, claves permitidas en el último nivel o None, validador del valor)
_TOKEN_RULES: Tuple[Tuple[Tuple[str, ...], Optional[Tuple[str, ...]], Callable[[Any], bool], str], ...] = (
    (("color", "*", "*"), _STEP_KEYS, _pattern(HEX), "color #RRGGBB"),
    (("themes", "*", "*"), ROLES, _pattern(HEX), "color #RRGGBB"),
    (("typography", "font_family"), None, _pattern(FONT_FAMILY), "familia tipográfica sin caracteres especiales"),
    (("typography", "base_size_px"), None, _number(10, 32, integer=True), "entero entre 10 y 32"),
    (("typography", "ratio"), None, _number(1.05, 2.0), "número entre 1.05 y 2"),
    (("typography", "scale", "*"), _SCALE_KEYS, _pattern(DIMENSION), "dimensión (px, rem, em, %)"),
    (("typography", "roles", "*"), ("h1", "h2", "h3", "h4", "body", "caption"), _one_of(_SCALE_KEYS), "paso de la escala"),
    (("typography", "weights", "*"), ("regular", "medium", "bold"), _number(100, 900, integer=True), "peso entre 100 y 900"),
    (("typography", "line_height", "*"), ("tight", "normal", "relaxed"), _number(1.0, 3.0), "número entre 1 y 3"),
    (("spacing", "*"), ("xs", "sm", "md", "lg", "xl", "2xl", "3xl"), _pattern(DIMENSION), "dimensión (px, rem, em, %)"),
    (("radius", "*"), ("none", "sm", "md", "lg", "full"), _pattern(DIMENSION), "dimensión (px, rem, em, %)"),
    (("shadow", "*"), ("sm", "md", "lg"), _pattern(SHADOW), "sombra CSS sin ';' ni llaves"),
    (("breakpoints", "*"), tuple(BREAKPOINTS), _pattern(DIMENSION), "dimensión (px, rem, em, %)"),
    (("motion", "*"), ("fast", "normal", "slow"), _pattern(DURATION), "duración en ms"),
)
_TOP_LEVEL = ("color", "themes", "typography", "spacing", "radius", "shadow", "breakpoints", "motion")


def token_leaves(tree: Dict[str, Any], prefix: Tuple[str, ...] = ()):
    for key, value in tree.items():
        path = (*prefix, str(key))
        if isinstance(value, dict):
            yield from token_leaves(value, path)
        else:
            yield path, value


def _rule_for(path: Tuple[str, ...]):
    for pattern, keys, check, description in _TOKEN_RULES:
        if len(pattern) == len(path) and all(p in ("*", s) for p, s in zip(pattern, path)):
            if keys is not None and path[-1] not in keys:
                continue
            if pattern[0] == "color" and path[1] not in PALETTES:
                continue
            if pattern[0] == "themes" and path[1] not in ("light", "dark"):
                continue
            return check, description
    return None


def validate_tokens(tokens: Dict[str, Any]) -> None:
    unknown = set(tokens) - set(_TOP_LEVEL)
    if unknown:
        raise DesignError(f"Grupos de tokens desconocidos: {', '.join(sorted(unknown))}")
    for path, value in token_leaves(tokens):
        rule = _rule_for(path)
        if rule is None:
            raise DesignError(f"Token no permitido: {'.'.join(path)}")
        check, description = rule
        if not check(value):
            raise DesignError(f"Valor inválido en {'.'.join(path)}: se espera {description}")


def merge_tokens(current: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    def merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                merge(base[key], value)
            else:
                base[key] = normalize_hex(value) if isinstance(value, str) and (HEX.match(value) or SHORT_HEX.match(value)) else value
        return base

    merged = merge(copy.deepcopy(current), overrides)
    validate_tokens(merged)
    return merged


# ============================================================================ componentes

COMPONENT_TYPES = (
    "button", "input", "select", "checkbox", "radio", "switch", "card", "modal", "navbar", "tabs",
    "table", "list", "alert", "tooltip", "datepicker", "badge", "avatar", "link", "icon_button",
)
INTERACTIVE = frozenset({"button", "input", "select", "checkbox", "radio", "switch", "tabs", "datepicker", "link", "icon_button"})
NEEDS_LABEL = frozenset({"input", "select", "checkbox", "radio", "switch", "datepicker", "icon_button"})
COMPONENT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,59}$")
STATE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,29}$")

DEFAULT_COMPONENTS: Tuple[Dict[str, Any], ...] = (
    {"nombre": "Button", "tipo": "button", "variantes": ["primary", "secondary", "danger", "ghost"],
     "estados": ["default", "hover", "focus", "active", "disabled"],
     "propiedades": {"min_alto_px": 44, "min_ancho_px": 44, "radio": "md", "rol_aria": "button"}},
    {"nombre": "IconButton", "tipo": "icon_button", "variantes": ["primary", "ghost"],
     "estados": ["default", "hover", "focus", "disabled"],
     "propiedades": {"min_alto_px": 44, "min_ancho_px": 44, "etiqueta_accesible": True, "rol_aria": "button"}},
    {"nombre": "TextField", "tipo": "input", "variantes": ["outlined", "filled"],
     "estados": ["default", "hover", "focus", "error", "disabled"],
     "propiedades": {"min_alto_px": 44, "etiqueta_accesible": True, "mensaje_error_asociado": True}},
    {"nombre": "Select", "tipo": "select", "variantes": ["outlined"],
     "estados": ["default", "focus", "open", "error", "disabled"],
     "propiedades": {"min_alto_px": 44, "etiqueta_accesible": True, "rol_aria": "combobox"}},
    {"nombre": "Checkbox", "tipo": "checkbox", "variantes": ["default"],
     "estados": ["unchecked", "checked", "indeterminate", "focus", "disabled"],
     "propiedades": {"min_alto_px": 24, "min_ancho_px": 24, "etiqueta_accesible": True}},
    {"nombre": "Card", "tipo": "card", "variantes": ["elevated", "outlined"], "estados": ["default"],
     "propiedades": {"radio": "lg", "sombra": "md"}},
    {"nombre": "Modal", "tipo": "modal", "variantes": ["dialog", "alertdialog"], "estados": ["open", "closed"],
     "propiedades": {"atrapa_foco": True, "cierra_con_escape": True, "devuelve_foco": True, "rol_aria": "dialog"}},
    {"nombre": "Navbar", "tipo": "navbar", "variantes": ["top", "side"], "estados": ["default", "collapsed"],
     "propiedades": {"landmark": "navigation", "enlace_saltar_contenido": True}},
    {"nombre": "Tabs", "tipo": "tabs", "variantes": ["line", "pill"], "estados": ["default", "selected", "focus", "disabled"],
     "propiedades": {"min_alto_px": 44, "rol_aria": "tablist", "navegacion_flechas": True}},
    {"nombre": "DataTable", "tipo": "table", "variantes": ["default", "striped"], "estados": ["default", "loading", "empty"],
     "propiedades": {"encabezados_th": True, "caption": True}},
    {"nombre": "Alert", "tipo": "alert", "variantes": ["info", "success", "warning", "error"], "estados": ["default"],
     "propiedades": {"rol_aria": "alert", "no_solo_color": True}},
)


def normalize_component(raw: Dict[str, Any]) -> Dict[str, Any]:
    name = str(raw.get("nombre") or "")
    kind = str(raw.get("tipo") or "")
    if not COMPONENT_NAME.match(name):
        raise DesignError("nombre del componente: letra inicial y luego letras, números, '_' o '-' (máx. 60)")
    if kind not in COMPONENT_TYPES:
        raise DesignError(f"tipo de componente no soportado: {kind!r} (opciones: {', '.join(COMPONENT_TYPES)})")
    variants = [str(v) for v in raw.get("variantes") or ["default"]]
    states = [str(s) for s in raw.get("estados") or ["default"]]
    for value in (*variants, *states):
        if not STATE_NAME.match(value):
            raise DesignError(f"variante/estado inválido: {value!r}")
    props = raw.get("propiedades") or {}
    if not isinstance(props, dict) or len(props) > 30:
        raise DesignError("propiedades debe ser un objeto con máximo 30 claves")
    for key, value in props.items():
        if not STATE_NAME.match(str(key)) or not isinstance(value, (str, int, float, bool)) or (isinstance(value, str) and len(value) > 100):
            raise DesignError(f"propiedad inválida: {key!r}")
    return {"nombre": name, "tipo": kind, "variantes": variants[:20], "estados": states[:20], "propiedades": props}


# (tipo de componente, propiedad requerida, criterio, severidad, mensaje, corrección)
_REQUIRED_PROPERTIES: Tuple[Tuple[str, str, str, str, str, str], ...] = (
    ("modal", "atrapa_foco", "2.4.3", "alta", "El foco no queda contenido en el modal", "propiedad atrapa_foco=true"),
    ("modal", "cierra_con_escape", "2.1.2", "alta", "El modal no se puede cerrar con teclado", "propiedad cierra_con_escape=true"),
    ("table", "encabezados_th", "1.3.1", "media", "La tabla no declara encabezados", "Usa <th scope> (propiedad encabezados_th=true)"),
    ("alert", "no_solo_color", "1.4.1", "media", "El tipo de alerta podría depender solo del color",
     "Agrega icono o texto (propiedad no_solo_color=true)"),
)


def _target_size(props: Dict[str, Any]) -> Optional[float]:
    sizes = [v for v in (props.get("min_alto_px"), props.get("min_ancho_px", props.get("min_alto_px")))
             if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return min(sizes) if sizes else None


def audit_component(component: Dict[str, Any], level: str) -> List[Dict[str, Any]]:
    kind, props, states = component["tipo"], component.get("propiedades", {}), set(component.get("estados", []))
    found: List[Tuple[str, str, str, str]] = []
    if kind in INTERACTIVE and "focus" not in states:
        found.append(("2.4.7", "alta" if level != "A" else "media", "No define estado de foco visible",
                      "Agrega el estado 'focus' con indicador de 3:1 o más"))
    if kind in NEEDS_LABEL and not props.get("etiqueta_accesible"):
        found.append(("1.3.1 / 4.1.2", "alta", "No declara etiqueta accesible",
                      "Asocia un <label> o aria-label (propiedad etiqueta_accesible=true)"))
    found += [(c, s, m, f) for t, prop, c, s, m, f in _REQUIRED_PROPERTIES if t == kind and not props.get(prop)]
    if kind in INTERACTIVE:
        smallest = _target_size(props)
        if level == "AAA" and (smallest is None or smallest < 44):
            found.append(("2.5.5", "alta", "Área táctil menor a 44×44 px", "min_alto_px y min_ancho_px de al menos 44"))
        elif smallest is not None and smallest < 24:
            found.append(("2.5.8 (WCAG 2.2)", "baja", "Área táctil menor a 24×24 px", "Aumenta el tamaño mínimo a 24 px o más"))
    return [{"componente": component["nombre"], "criterio": c, "severidad": s, "mensaje": m, "correccion": f}
            for c, s, m, f in found]


# ============================================================================ auditoría


def audit_tokens(tokens: Dict[str, Any], level: str) -> Dict[str, Any]:
    if level not in WCAG_LEVELS:
        raise DesignError(f"Nivel WCAG inválido: {level!r} (A, AA o AAA)")
    ratios = LEVEL_RATIOS.get(level)
    checks, fixes = [], {}
    for theme_name, theme in tokens["themes"].items():
        for fg_role, bg_role, kind, criterion in CONTRAST_PAIRS:
            fg, bg = theme[fg_role], theme[bg_role]
            ratio = contrast_ratio(fg, bg)
            required = ratios[kind] if ratios else None
            passed = required is None or ratio >= required
            check = {
                "tema": theme_name, "primer_plano": fg_role, "fondo": bg_role, "colores": [fg, bg],
                "tipo": kind, "criterio": criterion, "relacion": ratio, "requerido": required, "cumple": passed,
            }
            if not passed:
                suggestion: Dict[str, str] = {}
                if fg_role.startswith("on_"):
                    alternative = best_on(bg)
                    if contrast_ratio(alternative, bg) >= required:
                        suggestion = {fg_role: alternative}
                    else:
                        adjusted = adjust_for_contrast(bg, alternative, required)
                        suggestion = {fg_role: alternative, bg_role: adjusted} if adjusted else {}
                else:
                    candidate = adjust_for_contrast(fg, bg, required)
                    suggestion = {fg_role: candidate} if candidate else {}
                if suggestion:
                    check["sugerencia"] = suggestion
                    fixes.setdefault(theme_name, {}).update(suggestion)
            checks.append(check)
    return {"verificaciones": checks, "correcciones": fixes}


def accessibility_report(tokens: Dict[str, Any], components: List[Dict[str, Any]], level: str) -> Dict[str, Any]:
    contrast = audit_tokens(tokens, level)
    component_issues = [i for c in components for i in audit_component(c, level)]
    failing = [c for c in contrast["verificaciones"] if not c["cumple"]]
    blocking = [i for i in component_issues if i["severidad"] == "alta"]
    total = len(contrast["verificaciones"]) + len(components)
    passed = total - len(failing) - len({i["componente"] for i in blocking})
    return {
        "nivel_wcag": level,
        "cumple": not failing and not blocking,
        "total_verificaciones": total,
        "verificaciones_aprobadas": max(passed, 0),
        "contraste": contrast["verificaciones"],
        "contraste_fallido": len(failing),
        "componentes": component_issues,
        "correcciones_sugeridas": contrast["correcciones"],
        "nota": "Nivel A no exige contraste mínimo; los resultados de contraste son informativos." if level == "A" else None,
    }
