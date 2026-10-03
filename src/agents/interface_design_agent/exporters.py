"""Exportadores de Aurora: tokens a CSS/SCSS/Tailwind/DTCG/Android, layouts responsivos y pantallas HTML accesibles."""

from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Tuple

from src.agents.interface_design_agent.design import DesignError

EXPORT_FORMATS = ("css", "scss", "tailwind", "json", "android")
LAYOUT_TYPES = ("grid", "sidebar", "stack")
SCREEN_TYPES = ("login", "dashboard", "list", "form")
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


# ============================================================================ pantallas


def _base_styles() -> str:
    return """
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; font-family: var(--font-family); font-size: var(--font-size-base); line-height: var(--line-height-normal);
       color: var(--color-text); background: var(--color-background); }
h1 { font-size: var(--font-size-3xl); line-height: var(--line-height-tight); margin: 0 0 var(--space-md); }
h2 { font-size: var(--font-size-xl); margin: 0 0 var(--space-sm); }
a { color: var(--color-link); }
:focus-visible { outline: 3px solid var(--color-focus); outline-offset: 2px; }
.skip-link { position: absolute; left: -9999px; top: var(--space-sm); background: var(--color-surface); padding: var(--space-sm); }
.skip-link:focus { left: var(--space-sm); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.container { max-width: 1200px; margin-inline: auto; padding: var(--space-lg) var(--space-md); }
.card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg);
        box-shadow: var(--shadow-sm); padding: var(--space-lg); }
.field { display: flex; flex-direction: column; gap: var(--space-xs); margin-bottom: var(--space-md); }
.field input, .field select { min-height: 44px; padding: var(--space-sm) var(--space-md); font: inherit; color: var(--color-text);
        background: var(--color-background); border: 1px solid var(--color-input-border); border-radius: var(--radius-md); }
.field .error { color: var(--color-error-text); font-size: var(--font-size-sm); }
.btn { min-height: 44px; min-width: 44px; padding: var(--space-sm) var(--space-lg); font: inherit; font-weight: var(--font-weight-medium);
       border: 0; border-radius: var(--radius-md); cursor: pointer; background: var(--color-primary); color: var(--color-on-primary); }
.btn--secondary { background: var(--color-secondary); color: var(--color-on-secondary); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.grid { display: grid; gap: var(--space-md); grid-template-columns: 1fr; }
@media (min-width: 768px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (min-width: 1024px) { .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--color-border); }
nav ul { display: flex; gap: var(--space-md); list-style: none; margin: 0; padding: 0; }
header.app { display: flex; justify-content: space-between; align-items: center; padding: var(--space-md);
             border-bottom: 1px solid var(--color-border); background: var(--color-surface); }
"""


def _shell(title: str, app: str, lang: str, css: str, body: str, with_nav: bool) -> str:
    nav = (
        f'<header class="app"><strong>{app}</strong><nav aria-label="Principal"><ul>'
        '<li><a href="#" aria-current="page">Inicio</a></li><li><a href="#">Reportes</a></li>'
        '<li><a href="#">Configuración</a></li></ul></nav></header>'
        if with_nav else ""
    )
    return (
        f'<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{title} · {app}</title>\n'
        f"<style>\n{css}{_base_styles()}</style>\n</head>\n<body>\n"
        f'<a class="skip-link" href="#contenido">Saltar al contenido</a>\n{nav}\n'
        f'<main id="contenido" class="container">\n{body}\n</main>\n</body>\n</html>\n'
    )


def screen_html(tokens: Dict[str, Any], screen: str, app_name: str, lang: str = "es") -> Dict[str, Any]:
    if screen not in SCREEN_TYPES:
        raise DesignError(f"Tipo de pantalla no soportado: {screen!r} (opciones: {', '.join(SCREEN_TYPES)})")
    if lang not in ("es", "en", "pt"):
        raise DesignError("idioma debe ser es, en o pt")
    app = html.escape(app_name)
    css = to_css(tokens)
    if screen == "login":
        body = (
            '<section class="card" style="max-width:420px;margin:var(--space-2xl) auto" aria-labelledby="t">'
            '<h1 id="t">Iniciar sesión</h1><form method="post" novalidate>'
            '<div class="field"><label for="u">Usuario</label><input id="u" name="usuario" autocomplete="username" required></div>'
            '<div class="field"><label for="p">Contraseña</label><input id="p" name="contrasena" type="password" '
            'autocomplete="current-password" required aria-describedby="p-err"><span id="p-err" class="error" role="alert"></span></div>'
            '<button class="btn" type="submit">Entrar</button></form></section>'
        )
        components, with_nav = ["Card", "TextField", "Button"], False
    elif screen == "dashboard":
        cards = "".join(
            f'<article class="card" aria-labelledby="k{i}"><h2 id="k{i}">{name}</h2>'
            '<p style="font-size:var(--font-size-2xl);margin:0">—</p></article>'
            for i, name in enumerate(("Ventas", "Pedidos", "Clientes", "Incidencias"))
        )
        body = f'<h1>Panel</h1><section class="grid" aria-label="Indicadores">{cards}</section>'
        components, with_nav = ["Navbar", "Card"], True
    elif screen == "list":
        rows = "".join(
            f'<tr><td>Elemento {i}</td><td>Activo</td><td><a href="#">Ver<span class="sr-only"> elemento {i}</span></a></td></tr>'
            for i in range(1, 4)
        )
        body = (
            '<h1>Listado</h1><form role="search" class="field" style="max-width:360px"><label for="q">Buscar</label>'
            '<input id="q" type="search" name="q"></form><div class="card"><table><caption class="sr-only">Elementos</caption>'
            '<thead><tr><th scope="col">Nombre</th><th scope="col">Estado</th><th scope="col">Acciones</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
        )
        components, with_nav = ["Navbar", "TextField", "DataTable"], True
    else:
        body = (
            '<h1>Nuevo registro</h1><form class="card" method="post" style="max-width:640px">'
            '<div class="field"><label for="n">Nombre <span aria-hidden="true">*</span></label>'
            '<input id="n" name="nombre" required aria-required="true"></div>'
            '<div class="field"><label for="e">Correo</label><input id="e" name="correo" type="email" autocomplete="email"></div>'
            '<div class="field"><label for="t">Tipo</label><select id="t" name="tipo">'
            '<option>General</option><option>Prioritario</option></select></div>'
            '<div style="display:flex;gap:var(--space-sm)"><button class="btn" type="submit">Guardar</button>'
            '<button class="btn btn--secondary" type="reset">Cancelar</button></div></form>'
        )
        components, with_nav = ["Navbar", "TextField", "Select", "Button"], True
    titles = {"login": "Iniciar sesión", "dashboard": "Panel", "list": "Listado", "form": "Formulario"}
    document = _shell(titles[screen], app, lang, css, body, with_nav)
    return {"pantalla": screen, "componentes_usados": components, "html": document, "bytes": len(document.encode("utf-8"))}
