"""The fly brain regions and the part of Sergio that does each one's job."""

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
        "fly": "Ojos y lóbulos ópticos · antenas y lóbulo antenal",
        "job": "Preprocesan lo que entra: movimiento, luz, olores; cada canal por separado.",
        "sergio": "Las entradas: lo que escribe, su voz, la pantalla y la cámara. Llegan ya limpias a la región que toca.",
        "where": "Chat, voz, Sergio ve",
    },
    {
        "key": "cuerno_lateral",
        "fly": "Cuerno lateral",
        "job": "Respuestas innatas: caminos fijos que no hay que aprender.",
        "sergio": "Reflejos: atajos de teclado y palabras que van directo a su sitio, en el propio navegador, sin esperar al servidor ni a la IA.",
        "where": "Ctrl+K y las teclas G + letra",
    },
    {
        "key": "cuerpo_fungiforme",
        "fly": "Cuerpo fungiforme (células de Kenyon, neuronas de dopamina)",
        "job": "Aprende asociaciones: un código disperso de pocas neuronas activas y dopamina que premia lo que salió bien.",
        "sergio": "Atajos aprendidos: cada vez que elige un destino para unas palabras, la conexión se refuerza; lo que descarta se debilita. Lo que no usa se olvida poco a poco.",
        "where": "Memoria de atajos en este equipo",
    },
    {
        "key": "complejo_central",
        "fly": "Complejo central",
        "job": "Mantiene el rumbo y elige hacia dónde ir.",
        "sergio": "El enrutador: junta reflejos y aprendizaje, ordena los destinos y, si nada encaja, se lo pasa a Sergio en el chat.",
        "where": "La paleta de atajos",
    },
    {
        "key": "descendentes",
        "fly": "Neuronas descendentes",
        "job": "Convierten la decisión en movimiento.",
        "sergio": "Las acciones: abrir una sección, empezar una encuesta, un Post-it o una conversación. Nunca mensajes, llamadas, compras ni borrados por su cuenta.",
        "where": "Cada destino de la paleta",
    },
    {
        "key": "fibra_gigante",
        "fly": "Fibra gigante",
        "job": "El reflejo de escape: el camino más corto del cerebro, de la amenaza al salto.",
        "sergio": "Escape: pulse Esc tres veces seguidas y Sergio detiene lo que esté haciendo (Nodes, enjambre, Cowork y la voz).",
        "where": "Esc · Esc · Esc",
    },
    {
        "key": "club_rico",
        "fly": "Club rico de neuronas centrales",
        "job": "Pocas neuronas muy conectadas que integran todas las regiones.",
        "sergio": "El chat con Sergio: cualquier petición que no sea un atajo termina ahí, con todo el contexto.",
        "where": "Chat",
    },
]


def brain_map(memory_stats: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"facts": FACTS, "regions": REGIONS, "memory": memory_stats or {}}


__all__ = ["FACTS", "REGIONS", "brain_map"]
