"""OpenDesign in Spanish: replaces the editor's visible English texts in its
source before it is built (scripts/instalar-programas.sh runs it after each
update of OpenDesign; the next update first discards it with git checkout).

Only exact texts in known places change (between tags, in title / label /
placeholder / aria-label attributes, and a few string literals), so the
code itself is never touched. Usage: python3 opendesign_es.py <OpenDesign dir>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TEXT = {  # shown between tags (also when the text sits on its own line)
    "Alignment": "Alineación",
    "All pages": "Todas las páginas",
    "Background color": "Color de fondo",
    "Background image": "Imagen de fondo",
    "Canvas": "Lienzo",
    "Carousel PDF": "PDF de carrusel",
    "Click a template to apply": "Toque una plantilla para aplicarla",
    "Click to add a shape": "Toque para añadir una forma",
    "Click to add text": "Toque para añadir texto",
    "Create your first design to get started": "Cree su primer diseño para empezar",
    "Custom color": "Color personalizado",
    "Dimensions": "Medidas",
    "Field name": "Nombre del campo",
    "Fill color": "Color de relleno",
    "Flip": "Voltear",
    "Font size": "Tamaño de letra",
    "Gradient presets": "Degradados",
    "Kit name": "Nombre del kit",
    "Layer order": "Orden de capas",
    "Loading...": "Cargando…",
    "My Designs": "Mis diseños",
    "No brand kit yet": "Aún no hay kit de marca",
    "No designs yet": "Aún no hay diseños",
    "No saved designs yet": "Aún no hay diseños guardados",
    "No templates yet.": "Aún no hay plantillas.",
    "PNG at 2x": "PNG al doble",
    "Recent designs": "Diseños recientes",
    "Reload": "Recargar",
    "Solid colors": "Colores sólidos",
    "Start from a template": "Empiece con una plantilla",
    "Stroke color": "Color del borde",
    "Style": "Estilo",
    "This page": "Esta página",
    "Upload images to add to canvas": "Suba imágenes para añadirlas al lienzo",
    "New Design": "Nuevo diseño",
    "Add a heading": "Añadir un título",
    "Add a subheading": "Añadir un subtítulo",
    "Add body text": "Añadir texto",
    "Upload image": "Subir imagen",
    "Auto-save": "Guardar solo",
    "Save": "Guardar",
}
ATTRS = {  # title / aria-label / label / placeholder
    "Active brand kit": "Kit de marca activo",
    "Add brand color": "Añadir color de marca",
    "Available fonts": "Letras disponibles",
    "Custom height in pixels": "Alto en píxeles",
    "Custom width in pixels": "Ancho en píxeles",
    "Delete this brand kit": "Borrar este kit de marca",
    "New brand kit": "Nuevo kit de marca",
    "Remove logo": "Quitar el logo",
    "Upload logo": "Subir logo",
    "Body font": "Letra del texto",
    "Font family": "Tipo de letra",
    "Heading font": "Letra de títulos",
    "Width": "Ancho",
    "Height": "Alto",
    "Add logo to canvas": "Añadir el logo al lienzo",
    "Add page below": "Añadir página debajo",
    "Add page": "Añadir página",
    "Back to designs": "Volver a los diseños",
    "Delete page": "Borrar página",
    "Delete this kit": "Borrar este kit",
    "Delete": "Borrar",
    "Design": "Diseño",
    "Duplicate page": "Duplicar página",
    "Duplicate": "Duplicar",
    "Export this design": "Exportar este diseño",
    "Fit to screen": "Ajustar a la pantalla",
    "Redo (Cmd+Shift+Z)": "Rehacer (Ctrl+Mayús+Z)",
    "Restore the previous size and layout": "Volver al tamaño anterior",
    "Save changes automatically after a short pause": "Guarda los cambios solo, tras una pausa breve",
    "Undo (Cmd+Z)": "Deshacer (Ctrl+Z)",
    "Zoom in": "Acercar",
    "Zoom out": "Alejar",
}
LITERALS = {  # string literals in code (labels of menus, defaults, states)
    '"Templates"': '"Plantillas"',
    '"Brand"': '"Marca"',
    '"Elements"': '"Elementos"',
    '"Uploads"': '"Subidas"',
    '"Bg"': '"Fondo"',
    '"Designs"': '"Diseños"',
    '"Rectangle"': '"Rectángulo"',
    '"Circle"': '"Círculo"',
    '"Triangle"': '"Triángulo"',
    '"Line"': '"Línea"',
    '"Untitled Design"': '"Diseño sin título"',
    '"Add a heading"': '"Añadir un título"',
    '"Add a subheading"': '"Añadir un subtítulo"',
    '"Add body text"': '"Añadir texto"',
    '"Preparing..."': '"Preparando…"',
    '"Export"': '"Exportar"',
    '"Unsaved changes"': '"Cambios sin guardar"',
    '"Saving…"': '"Guardando…"',
    '"Save failed"': '"No se pudo guardar"',
    '"All changes saved"': '"Todo guardado"',
}
SIDEBAR_TEXT = re.compile(r'(label: |text: )"Text"')


def translate(source: str) -> str:
    out = source
    for en, es in TEXT.items():
        out = re.sub(rf"(>\s*){re.escape(en)}(\s*<)", rf"\g<1>{es}\g<2>", out)
    for en, es in ATTRS.items():
        out = re.sub(
            rf'((?:title|aria-label|label|placeholder)=")({re.escape(en)})(")',
            rf"\g<1>{es}\g<3>",
            out,
        )
    for en, es in LITERALS.items():
        out = out.replace(en, es)
    out = SIDEBAR_TEXT.sub(r'\g<1>"Texto"', out)
    out = out.replace('"Brand Kit"', '"Kit de marca"').replace('"Background"', '"Fondo"')
    out = re.sub(r"Pages \(\{", "Páginas ({", out)
    return out


def main(folder: str) -> int:
    root = Path(folder) / "src" / "client"
    changed = 0
    for path in sorted(root.rglob("*.ts*")):
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        text = path.read_text(encoding="utf-8")
        new = translate(text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
    print(f"OpenDesign en español: {changed} archivos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
