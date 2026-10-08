"""Sergio's evolution: long-term memory (RAG + feedback history) and a
self-correction loop, so the same mistake is not made twice.

* ``memory.LongTermMemory``: every finished task, every review verdict and
  every piece of feedback from the user, in a vector database (chromadb),
  searchable by meaning. Before a new Blender model or video edit the
  closest lessons are read into the prompt.
* ``reflect.self_correct``: generate -> check -> reflect -> regenerate, as a
  LangGraph state machine, until the result passes or the rounds run out;
  what fixed it becomes a lesson in memory.
* ``crew.run_crew``: a crewAI team (specialist + quality supervisor) for
  long written tasks, when crewAI is installed.
"""
