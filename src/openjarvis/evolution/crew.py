"""A crewAI team with a quality supervisor, for long written work.

Specialist writes, the Quality Supervisor reviews it against the brief and
sends it back with concrete fixes (crewAI hierarchical process, the
supervisor as manager). Runs on Gemini through LiteLLM with the user's key.
crewAI is optional (``sergio evolucion instalar crew``); without it Sergio's
own orchestrator (planner + Revisor) does the same job.
"""

from __future__ import annotations

import os
from typing import Any

MODEL = "gemini/gemini-2.5-flash"
BACKUP = "gemini/gemini-flash-lite-latest"  # its own quota, when the main one runs out


def available() -> bool:
    try:
        import crewai  # noqa: F401
    except ImportError:
        return False
    return True


def run_crew(task: str, lessons: str = "", model: str = MODEL) -> dict[str, Any]:
    """The crew's result for *task*: {"result", "agents", "engine"}."""
    if not available():
        raise RuntimeError("crewAI no está instalado (sergio evolucion instalar crew).")
    errors = []
    for name in dict.fromkeys((model, BACKUP)):
        try:
            return _run(task, lessons, name)
        except Exception as exc:  # noqa: BLE001 — quota or a busy model: the backup
            errors.append(f"{name}: {str(exc)[:120]}")
    raise RuntimeError("El equipo no pudo trabajar: " + " | ".join(errors))


def _run(task: str, lessons: str, model: str) -> dict[str, Any]:
    from crewai import LLM, Agent, Crew, Process, Task

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY")
    llm = LLM(model=model, api_key=key, temperature=0.4)
    specialist = Agent(
        role="Especialista",
        goal="Resolver la tarea con precisión de experto, en español, sin inventar datos.",
        backstory="Experto senior en la materia de la tarea; cita lo que sabe y marca lo que no sabe.",
        llm=llm, allow_delegation=False, verbose=False,
    )
    supervisor = Agent(
        role="Supervisor de calidad",
        goal="Que el resultado cumpla el encargo punto por punto, sin errores ni relleno.",
        backstory="Revisor exigente: contrasta cada afirmación con el encargo y devuelve el trabajo con "
                  "correcciones concretas hasta que está bien.",
        llm=llm, allow_delegation=True, verbose=False,
    )
    work = Task(
        description=f"{task}\n\n{lessons}".strip(),
        expected_output="El trabajo terminado, revisado y en español, listo para entregar.",
        agent=specialist,
    )
    crew = Crew(agents=[specialist], tasks=[work], manager_agent=supervisor, process=Process.hierarchical,
                verbose=False)
    out = crew.kickoff()
    return {"result": str(getattr(out, "raw", out)), "agents": ["Especialista", "Supervisor de calidad"],
            "engine": "crewai", "model": model}


__all__ = ["available", "run_crew"]
