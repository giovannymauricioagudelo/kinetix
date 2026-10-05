"""Exportadores de Aurora: tokens a CSS/SCSS/Tailwind/DTCG/Android y layouts responsivos (pantallas HTML en screens.py)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from src.agents.interface_design_agent.design import DesignError

EXPORT_FORMATS = ("css", "scss", "tailwind", "json", "android")
LAYOUT_TYPES = ("grid", "sidebar", "stack")
MEDIA_TYPES = {
    "css": "text/css", "scss": "text/x-scss", "tailwind": "application/javascript",
    "json": "application/json", "android": "application/xml", "html": "text/html",
}
EXTENSIONS = {"css": "css", "scss": "scss", "tailwind": "js", "json": "json", "android": "xml"}


def _flat(tokens: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Pares (nombre-variable, valor) de los tokens base (sin temas)."""
    pairs: List[Tuple[str, str]] = []
    for palette, steps in tokens["color"].items():
        for step, value in steps.items():
            pairs.append((f"color-{palette}-{step}", value))
    typo = tokens["typography"]
    pairs.append(("font-family", typo["font_family"]))
    for name, value in typo["scale"].items():
        pairs.append((f"font-size-{name}", value))
    for name, value in typo["weights"].items():
        pairs.append((f"font-weight-{name}", str(value)))
    for name, value in typo["line_height"].items():
        pairs.append((f"line-height-{name}", str(value)))
    for group, prefix in (("spacing", "space"), ("radius", "radius"), ("shadow", "shadow"),
                          ("breakpoints", "breakpoint"), ("motion", "duration")):
        for name, value in tokens[group].items():
            pairs.append((f"{prefix}-{name}", value))
    return pairs


def _role_var(role: str) -> str:
    return "color-" + role.replace("_", "-")


def to_css(tokens: Dict[str, Any]) -> str:
    lines = [":root {"]
    lines += [f"  --{name}: {value};" for name, value in _flat(tokens)]
    lines += [f"  --{_role_var(role)}: {value};" for role, value in tokens["themes"]["light"].items()]
    lines.append("}")
    dark = [f"  --{_role_var(role)}: {value};" for role, value in tokens["themes"]["dark"].items()]
    lines += ["", '[data-theme="dark"] {', *dark, "}", "", "@media (prefers-color-scheme: dark) {",
              '  :root:not([data-theme="light"]) {', *("  " + line for line in dark), "  }", "}"]
    lines += ["", "@media (prefers-reduced-motion: reduce) {", "  :root { --duration-fast: 0ms; --duration-normal: 0ms; --duration-slow: 0ms; }", "}"]
    return "\n".join(lines) + "\n"


def to_scss(tokens: Dict[str, Any]) -> str:
    lines = [f"${name}: {value};" for name, value in _flat(tokens)]
    for theme, roles in tokens["themes"].items():
        lines.append("")
        lines.append(f"$theme-{theme}: (")
        lines += [f"  '{role.replace('_', '-')}': {value}," for role, value in roles.items()]
        lines.append(");")
    return "\n".join(lines) + "\n"


def to_tailwind(tokens: Dict[str, Any]) -> str:
    colors: Dict[str, Any] = {palette: dict(steps) for palette, steps in tokens["color"].items()}
    colors.update({role.replace("_", "-"): f"var(--{_role_var(role)})" for role in tokens["themes"]["light"]})
    config = {
        "darkMode": ["class", '[data-theme="dark"]'],
        "theme": {
            "screens": {"sm": tokens["breakpoints"]["mobile"], "md": tokens["breakpoints"]["tablet"],
                        "lg": tokens["breakpoints"]["desktop"]},
            "extend": {
                "colors": colors,
                "spacing": tokens["spacing"],
                "borderRadius": tokens["radius"],
                "boxShadow": tokens["shadow"],
                "fontFamily": {"sans": [f.strip() for f in tokens["typography"]["font_family"].split(",")]},
                "fontSize": tokens["typography"]["scale"],
                "transitionDuration": tokens["motion"],
            },
        },
    }
    return "/** @type {import('tailwindcss').Config} */\nmodule.exports = " + json.dumps(config, indent=2, ensure_ascii=False) + ";\n"


def to_dtcg(tokens: Dict[str, Any]) -> str:
    """Formato W3C Design Tokens Community Group ($value / $type)."""
    def leaf(value: Any, kind: str) -> Dict[str, Any]:
        return {"$value": value, "$type": kind}

    doc: Dict[str, Any] = {
        "color": {p: {s: leaf(v, "color") for s, v in steps.items()} for p, steps in tokens["color"].items()},
        "theme": {t: {r: leaf(v, "color") for r, v in roles.items()} for t, roles in tokens["themes"].items()},
        "font": {
            "family": leaf([f.strip() for f in tokens["typography"]["font_family"].split(",")], "fontFamily"),
            "size": {n: leaf(v, "dimension") for n, v in tokens["typography"]["scale"].items()},
            "weight": {n: leaf(v, "fontWeight") for n, v in tokens["typography"]["weights"].items()},
        },
        "spacing": {n: leaf(v, "dimension") for n, v in tokens["spacing"].items()},
        "radius": {n: leaf(v, "dimension") for n, v in tokens["radius"].items()},
        "shadow": {n: leaf(v, "shadow") for n, v in tokens["shadow"].items()},
        "breakpoint": {n: leaf(v, "dimension") for n, v in tokens["breakpoints"].items()},
        "duration": {n: leaf(v, "duration") for n, v in tokens["motion"].items()},
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def _dp(value: str) -> str:
    return value[:-2] + "dp" if value.endswith("px") else ("0dp" if value == "0" else value)


def to_android(tokens: Dict[str, Any]) -> str:
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
    for palette, steps in tokens["color"].items():
        lines += [f'    <color name="{palette}_{step}">{value}</color>' for step, value in steps.items()]
    for theme, roles in tokens["themes"].items():
        lines += [f'    <color name="{theme}_{role}">{value}</color>' for role, value in roles.items()]
    lines += [f'    <dimen name="space_{n}">{_dp(v)}</dimen>' for n, v in tokens["spacing"].items()]
    lines += [f'    <dimen name="radius_{n}">{_dp(v)}</dimen>' for n, v in tokens["radius"].items()]
    lines += [f'    <dimen name="text_{n}">{_dp(v)[:-2] + "sp" if v.endswith("px") else v}</dimen>'
              for n, v in tokens["typography"]["scale"].items()]
    lines.append("</resources>")
    return "\n".join(lines) + "\n"


EXPORTERS = {"css": to_css, "scss": to_scss, "tailwind": to_tailwind, "json": to_dtcg, "android": to_android}


def export(tokens: Dict[str, Any], fmt: str) -> str:
    if fmt not in EXPORTERS:
        raise DesignError(f"Formato no soportado: {fmt!r} (opciones: {', '.join(EXPORT_FORMATS)})")
    return EXPORTERS[fmt](tokens)


# ============================================================================ layouts


def responsive_layout(tokens: Dict[str, Any], layout: str, columns: Dict[str, int], gap: str,
                      max_width_px: int, css_class: str) -> Dict[str, Any]:
    if layout not in LAYOUT_TYPES:
        raise DesignError(f"Tipo de layout no soportado: {layout!r} (opciones: {', '.join(LAYOUT_TYPES)})")
    if gap not in tokens["spacing"]:
        raise DesignError(f"Espaciado desconocido: {gap!r} (opciones: {', '.join(tokens['spacing'])})")
    bp = tokens["breakpoints"]
    cls = css_class
    lines: List[str] = []
    if layout == "grid":
        lines += [
            f".{cls} {{", "  display: grid;", f"  gap: var(--space-{gap});",
            f"  grid-template-columns: repeat({columns['mobile']}, minmax(0, 1fr));",
            f"  max-width: {max_width_px}px;", "  margin-inline: auto;", "  padding-inline: var(--space-md);", "}",
        ]
        for device in ("tablet", "desktop"):
            lines += [f"@media (min-width: {bp[device]}) {{",
                      f"  .{cls} {{ grid-template-columns: repeat({columns[device]}, minmax(0, 1fr)); }}", "}"]
        lines += [f".{cls}__span-full {{ grid-column: 1 / -1; }}"]
        lines += [f"@media (min-width: {bp['desktop']}) {{"]
        lines += [f"  .{cls}__span-{n} {{ grid-column: span {n} / span {n}; }}" for n in range(1, columns["desktop"] + 1)]
        lines.append("}")
    elif layout == "sidebar":
        lines += [
            f".{cls} {{", "  display: grid;", f"  gap: var(--space-{gap});",
            '  grid-template-areas: "header" "main" "sidebar" "footer";', "  grid-template-columns: 1fr;",
            f"  max-width: {max_width_px}px;", "  margin-inline: auto;", "}",
            f"@media (min-width: {bp['tablet']}) {{",
            f'  .{cls} {{ grid-template-areas: "header header" "sidebar main" "footer footer"; grid-template-columns: 240px 1fr; }}',
            "}",
            f".{cls}__header {{ grid-area: header; }}", f".{cls}__main {{ grid-area: main; }}",
            f".{cls}__sidebar {{ grid-area: sidebar; }}", f".{cls}__footer {{ grid-area: footer; }}",
        ]
    else:
        lines += [
            f".{cls} {{", "  display: flex;", "  flex-direction: column;", f"  gap: var(--space-{gap});",
            f"  max-width: {max_width_px}px;", "  margin-inline: auto;", "}",
            f"@media (min-width: {bp['tablet']}) {{", f"  .{cls}--row-tablet {{ flex-direction: row; flex-wrap: wrap; }}", "}",
        ]
    css = "\n".join(lines) + "\n"
    return {
        "tipo": layout,
        "clase": cls,
        "puntos_de_quiebre": bp,
        "columnas": columns,
        "css": css,
        "clases_generadas": css.count("{") - css.count("@media"),
    }
