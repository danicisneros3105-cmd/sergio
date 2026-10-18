"""Who did the research behind Salud mental and the mental gym.

Every scale and exercise comes from published studies. This module is the one
place that says which, by whom and where, so the app can credit them at the
end of each section, in small print.

Institution names are shown as text only, to say where a study was done. The
universities' logos are registered marks and their published rules ask for
written permission before an outside party uses them (checked October 2026 for
Columbia, Penn State, Michigan and UCLA; see ``docs/LEGAL-MARCAS.md``). So no
logo ships with Sergio. If the owner obtains permission, a logo file placed in
``~/.openjarvis/instituciones/<clave>.png`` (or .svg/.webp) is shown next to
the name, and the notice says it was added by the owner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

INSTITUTIONS: Dict[str, str] = {
    "columbia": "Universidad de Columbia",
    "indiana": "Universidad de Indiana",
    "pennstate": "Universidad Estatal de Pensilvania (Penn State)",
    "michigan": "Universidad de Míchigan",
    "chicago": "Universidad de Chicago",
    "bern": "Universidad de Berna",
    "uci": "Universidad de California, Irvine",
    "ubc": "Universidad de la Columbia Británica",
    "saarland": "Universidad del Sarre",
}

NOTICE = (
    "Las instituciones se nombran solo para decir dónde se hizo cada investigación. "
    "Sergio no tiene relación con ellas ni cuenta con su aval. Los logos de las "
    "universidades son marcas registradas y sus normas piden permiso por escrito para "
    "usarlos, así que Sergio no los incluye; solo se muestran si el propietario los "
    "añade con ese permiso."
)

# scope: "mente" (survey scales) or "gimnasio" (mental gym exercises).
STUDIES: List[Dict[str, Any]] = [
    {
        "scope": "mente",
        "topic": "Ánimo (PHQ-9 y PHQ-2)",
        "cite": "Kroenke, Spitzer y Williams (2001), Journal of General Internal Medicine; Kroenke, Spitzer y Williams (2003), Medical Care. Creado por Spitzer y Williams (Columbia) y Kroenke (Indiana); uso libre.",
        "doi": "10.1046/j.1525-1497.2001.016009606.x",
        "institutions": ["columbia", "indiana"],
    },
    {
        "scope": "mente",
        "topic": "Ansiedad (GAD-7 y GAD-2)",
        "cite": "Spitzer, Kroenke, Williams y Löwe (2006), Archives of Internal Medicine; Kroenke et al. (2007), Annals of Internal Medicine. Uso libre.",
        "doi": "10.1001/archinte.166.10.1092",
        "institutions": ["columbia", "indiana"],
    },
    {
        "scope": "mente",
        "topic": "Autoestima (Rosenberg)",
        "cite": "Rosenberg (1965), Society and the Adolescent Self-Image, Princeton University Press; versión española de Vázquez, Jiménez y Vázquez-Morejón (2004).",
        "doi": "",
        "institutions": [],
    },
    {
        "scope": "mente",
        "topic": "Rumiación (ítems de «brooding»)",
        "cite": "Treynor, Gonzalez y Nolen-Hoeksema (2003), Cognitive Therapy and Research.",
        "doi": "10.1023/A:1023910315561",
        "institutions": ["michigan"],
    },
    {
        "scope": "mente",
        "topic": "Preocupación (PSWQ-3)",
        "cite": "Meyer, Miller, Metzger y Borkovec (1990), Behaviour Research and Therapy; versión ultrabreve de Berle et al. (2011).",
        "doi": "10.1016/0005-7967(90)90135-6",
        "institutions": ["pennstate"],
    },
    {
        "scope": "mente",
        "topic": "Autenticidad",
        "cite": "Wood, Linley, Maltby, Baliousis y Joseph (2008), Journal of Counseling Psychology. Traducción de trabajo, no la versión española validada.",
        "doi": "10.1037/0022-0167.55.3.385",
        "institutions": [],
    },
    {
        "scope": "mente",
        "topic": "Soledad (UCLA de 3 ítems)",
        "cite": "Hughes, Waite, Hawkley y Cacioppo (2004), Research on Aging.",
        "doi": "10.1177/0164027504268574",
        "institutions": ["chicago"],
    },
    {
        "scope": "gimnasio",
        "topic": "Dual N-Back",
        "cite": "Jaeggi, Buschkuehl, Jonides y Perrig (2008), PNAS. Un metaanálisis posterior (Au et al., 2015, Psychonomic Bulletin & Review) halló un efecto pequeño sobre la inteligencia fluida; la evidencia sigue en debate.",
        "doi": "10.1073/pnas.0801268105",
        "institutions": ["michigan", "bern", "uci"],
    },
    {
        "scope": "gimnasio",
        "topic": "Matrices de razonamiento",
        "cite": "Klauer y Phye (2008), «Inductive reasoning: a training approach», Review of Educational Research.",
        "doi": "10.3102/0034654307313402",
        "institutions": [],
    },
    {
        "scope": "gimnasio",
        "topic": "Velocidad de procesamiento y campo visual útil",
        "cite": "Ball et al. (2002), JAMA, ensayo ACTIVE con adultos de 65 años o más en seis ciudades de EE. UU.; a los 10 años, Edwards et al. (2017), Alzheimer's & Dementia, hallaron en el grupo de velocidad un riesgo de demencia cerca de un 29 % menor (HR 0,71). No es un tratamiento.",
        "doi": "10.1001/jama.288.18.2271",
        "institutions": [],
    },
    {
        "scope": "gimnasio",
        "topic": "Alternancia y control inhibitorio",
        "cite": "Karbach y Kray (2009), Developmental Science; Diamond (2013), Annual Review of Psychology.",
        "doi": "10.1111/j.1467-7687.2009.00846.x",
        "institutions": ["saarland", "ubc"],
    },
    {
        "scope": "gimnasio",
        "topic": "Símbolos y dígitos",
        "cite": "Inspirado en el subtest de claves de la escala de inteligencia de Wechsler para adultos (WAIS-IV, 2008). Es un ejercicio propio: no es la prueba oficial ni da un cociente intelectual.",
        "doi": "",
        "institutions": [],
    },
]

LOGO_TYPES = (".png", ".svg", ".webp")
MAX_LOGO_BYTES = 300_000


def logos_dir() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "instituciones"


def logo_path(key: str, folder: Optional[Path] = None) -> Optional[Path]:
    """The logo file the owner added for *key*, if any (keys are fixed names)."""
    if key not in INSTITUTIONS:
        return None
    folder = folder or logos_dir()
    for ext in LOGO_TYPES:
        path = folder / f"{key}{ext}"
        if (
            path.is_file()
            and not path.is_symlink()
            and path.stat().st_size <= MAX_LOGO_BYTES
        ):
            return path
    return None


def credits(scope: str, folder: Optional[Path] = None) -> Dict[str, Any]:
    studies = []
    for s in STUDIES:
        if s["scope"] != scope:
            continue
        studies.append(
            {
                "topic": s["topic"],
                "cite": s["cite"],
                "url": f"https://doi.org/{s['doi']}" if s["doi"] else "",
                "institutions": [
                    {
                        "key": k,
                        "name": INSTITUTIONS[k],
                        "logo": logo_path(k, folder) is not None,
                    }
                    for k in s["institutions"]
                ],
            }
        )
    return {
        "scope": scope,
        "studies": studies,
        "notice": NOTICE,
        "logos_added_by_owner": any(
            i["logo"] for s in studies for i in s["institutions"]
        ),
    }


__all__ = [
    "INSTITUTIONS",
    "NOTICE",
    "STUDIES",
    "credits",
    "logo_path",
    "logos_dir",
]
