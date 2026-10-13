"""Short, unconditional internal design policy; heavy Anatomy resources stay lazy."""

from pathlib import Path

ANATOMY_POLICY = (
    "\nGuía interna Anatomy de Sergio: en toda creación visual, parte de los "
    "componentes existentes y aplica la skill anatomy sin crear una sección "
    "visible. Diseño sereno, jerarquía clara, negro/blanco/azul claro; personajes "
    "amables de fieltro y geometría físicamente coherente. Respeta teclado, "
    "contraste y movimiento reducido. Usa FreeCAD/Bonsai/LibreCAD, ArtCraft, "
    "Kdenlive, OpenDesign y VSCodium cuando estén disponibles; verifica su "
    "estado antes de usarlos. Los estados y resultados siempre son reales. "
    f"Recursos internos: {Path(__file__).with_name('bundled') / 'anatomy'}."
)
