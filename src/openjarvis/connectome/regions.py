"""The fly brain regions and the zone of Sergio's mind that does each one's job."""

from __future__ import annotations

from typing import Any, Dict, List

FACTS = {
    "neurons": "≈140 000 neuronas",
    "synapses": "más de 50 millones de sinapsis",
    "cell_types": "más de 8 000 tipos de célula",
    "sources": [
        {
            "cite": "Dorkenwald et al. (2024), «Neuronal wiring diagram of an adult brain», Nature (FlyWire, Universidad de Princeton).",
            "url": "https://doi.org/10.1038/s41586-024-07558-y",
        },
        {
            "cite": "Lin et al. (2024), «Network statistics of the whole-brain connectome of Drosophila», Nature.",
            "url": "https://doi.org/10.1038/s41586-024-07968-y",
        },
        {
            "cite": "Scheffer et al. (2020), «A connectome and analysis of the adult Drosophila central brain», eLife (hemicerebro, Janelia y Google).",
            "url": "https://doi.org/10.7554/eLife.57443",
        },
        {
            "cite": "Januszewski et al. (2018), «High-precision automated reconstruction of neurons with flood-filling networks», Nature Methods (Google).",
            "url": "https://doi.org/10.1038/s41592-018-0049-4",
        },
    ],
}

REGIONS: List[Dict[str, Any]] = [
    {
        "key": "sentidos",
        "fly": "Lóbulos óptico y antenal",
        "job": "Preprocesan lo que entra; cada canal por separado.",
        "sergio": "Zona de entrada: lo que escribe, su voz, la pantalla y la cámara se codifican en pocas células activas.",
        "where": "Chat, voz, Sergio ve",
    },
    {
        "key": "cuerpo_fungiforme",
        "fly": "Cuerpo fungiforme (células de Kenyon, dopamina)",
        "job": "Memoria por asociación: lo que salió bien refuerza sus sinapsis.",
        "sergio": "Zona de memoria: guarda un engrama de cada conversación y lo recupera cuando vuelve el tema, aunque ya no quepa en la ventana de contexto.",
        "where": "Memoria a largo plazo",
    },
    {
        "key": "cuerno_lateral",
        "fly": "Cuerno lateral",
        "job": "Lo innato: caminos fijos que no hay que aprender.",
        "sergio": "Zona de prompts y habilidades: la biblioteca de prompts, las skills y los reflejos de teclado.",
        "where": "Biblioteca de prompts · skills",
    },
    {
        "key": "complejo_central",
        "fly": "Complejo central",
        "job": "Mantiene el rumbo y elige hacia dónde ir.",
        "sergio": "Zona de conversación: el hilo de lo que se habla y qué zona aporta más en cada turno.",
        "where": "Cada respuesta",
    },
    {
        "key": "descendentes",
        "fly": "Neuronas descendentes",
        "job": "Convierten la decisión en movimiento.",
        "sergio": "Zona de herramientas: abrir apps, buscar, el equipo. Nunca mensajes, llamadas, compras ni borrados por su cuenta.",
        "where": "Herramientas",
    },
    {
        "key": "fibra_gigante",
        "fly": "Fibra gigante",
        "job": "El reflejo de escape, el camino más corto.",
        "sergio": "Escape: Esc tres veces detiene Nodes, enjambre, Cowork y la voz.",
        "where": "Esc · Esc · Esc",
    },
    {
        "key": "club_rico",
        "fly": "Club rico de neuronas centrales",
        "job": "Pocas neuronas muy conectadas que integran todas las regiones.",
        "sergio": "Integración: el modelo de lenguaje recibe lo que aportó cada zona y responde.",
        "where": "Sergio",
    },
]

# How learning works, said once for the page.
LEARNING = (
    "Cuando un recuerdo o una habilidad ayuda, las conexiones entre las palabras "
    "de la petición y ese recuerdo se refuerzan, y los recuerdos usados juntos "
    "se enlazan. La próxima vez esas conexiones lo traen directo, sin buscar "
    "entre todo (más rápido). Una corrección las debilita y lo que no se usa se "
    "olvida poco a poco. Es memoria y contexto, no un cambio de los pesos del modelo."
)


def brain_map(
    memory_stats: Dict[str, Any] | None = None, mind: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    return {
        "facts": FACTS,
        "regions": REGIONS,
        "learning": LEARNING,
        "memory": memory_stats or {},
        "mind": mind or {},
    }


__all__ = ["FACTS", "LEARNING", "REGIONS", "brain_map"]
