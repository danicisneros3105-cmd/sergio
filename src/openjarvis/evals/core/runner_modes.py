"""EvalRunner's episode and interactive (multi-turn) modes, few-shot example
injection and prompt formatting.

Split out of ``runner.py``; its names are looked up on that module at call
time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import openjarvis.evals.core.runner as _runner
from openjarvis.evals.core.types import EvalRecord, EvalResult


class _RunnerModesMixin:
    def _run_episode_mode(
        self,
        records: List[EvalRecord],
        progress_callback: Optional[Callable[[int, int], None]],
        total: int,
    ) -> None:
        """Process samples sequentially within episodes.

        Mirrors the original LifelongAgentBench ``PreviousSampleUtilizationCallback``:
        successful completions are accumulated and injected as in-context
        examples into subsequent tasks within the same episode.

        The original injects the full interaction history (question + all
        agent/environment exchanges) from prior successful sessions, not
        just problem/answer summaries.  We replicate this by storing
        the full message history for each successful task.
        """
        # Only treat a dataset as having interactive environments if it actually
        # overrides create_task_env.  The DatasetProvider base class provides a
        # default implementation that returns None, so hasattr() is always True —
        # we must check for a real override to avoid calling env.reset() on None.
        from openjarvis.evals.core.dataset import DatasetProvider

        has_task_env = (
            type(self._dataset).create_task_env is not DatasetProvider.create_task_env
        )

        for episode in self._dataset.iter_episodes():
            successful_examples: List[Dict[str, Any]] = []

            for record in episode:
                if has_task_env:
                    result = self._process_interactive(
                        record,
                        successful_examples,
                    )
                else:
                    # Inject prior examples into prompt, then single-shot
                    augmented = self._inject_examples(
                        record,
                        successful_examples,
                    )
                    result = self._process_one(augmented)

                self._results.append(result)
                self._flush_result(result)

                # Accumulate successful examples for lifelong learning.
                # Store the full interaction history when available.
                if result.is_correct:
                    example: Dict[str, Any] = {
                        "problem": record.problem,
                        "answer": result.model_answer,
                    }
                    # Attach full interaction history if recorded
                    interaction = (
                        result.scoring_metadata.get(
                            "_interaction_history",
                        )
                        if result.scoring_metadata
                        else None
                    )
                    if interaction:
                        example["interaction_history"] = interaction
                    successful_examples.append(example)
                    # FIFO eviction matching original's utilized_sample_count
                    if len(successful_examples) > self._MAX_PRIOR_EXAMPLES:
                        successful_examples.pop(0)

                if progress_callback is not None:
                    progress_callback(len(self._results), total)

    def _inject_examples(
        self,
        record: EvalRecord,
        examples: List[Dict[str, Any]],
    ) -> EvalRecord:
        """Create a copy of the record with prior examples prepended.

        Matches the original's ``PreviousSampleUtilizationCallback``
        which injects the full interaction history (question + all
        agent/environment exchanges) from prior successful tasks.
        """
        if not examples:
            return record

        example_text = "## Previously Completed Tasks\n\n"
        for i, ex in enumerate(examples, 1):
            example_text += f"### Example {i}\n"
            # Use full interaction history if available (matching original)
            history = ex.get("interaction_history")
            if history and isinstance(history, list):
                # Format the full multi-turn exchange
                for msg in history:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "system":
                        continue
                    label = "Agent" if role == "assistant" else "User"
                    example_text += f"{label}: {content}\n"
                example_text += "\n"
            else:
                # Fallback: problem + answer summary
                example_text += (
                    f"Task: {ex['problem'][:800]}\nSolution: {ex['answer'][:800]}\n\n"
                )
        example_text += "## Current Task\n\n"

        return _runner.EvalRecord(
            record_id=record.record_id,
            problem=example_text + record.problem,
            reference=record.reference,
            category=record.category,
            subject=record.subject,
            metadata=record.metadata,
        )

    def _process_interactive(
        self,
        record: EvalRecord,
        prior_examples: List[Dict[str, Any]],
    ) -> EvalResult:
        """Process a record via multi-turn environment interaction.

        Used when the dataset provides ``create_task_env()``, e.g. for
        LifelongAgentBench where agents must interact with DB/KG/OS
        environments across multiple turns.

        The full interaction history is recorded in scoring_metadata so
        it can be injected into subsequent tasks in the same episode,
        matching the original's ``PreviousSampleUtilizationCallback``.
        """
        cfg = self._config
        env = None
        total_latency = 0.0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cost = 0.0
        all_responses: List[str] = []

        try:
            env = self._dataset.create_task_env(record)
            env.reset(record)

            # Build system prompt from record (first part before task)
            system_prompt = ""
            problem_text = record.problem
            # Split on "## Task" or "## Question" to separate system from task
            for sep in ("## Task\n", "## Question\n", "## Database Schema\n"):
                if sep in problem_text:
                    idx = problem_text.index(sep)
                    system_prompt = problem_text[:idx].strip()
                    break

            # Build conversation with optional prior examples
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # Inject prior examples (lifelong learning) — use full
            # interaction history when available, matching the original's
            # PreviousSampleUtilizationCallback which replays the complete
            # chat history from prior successful sessions.
            if prior_examples:
                examples_text = "Here are examples of previously completed tasks:\n\n"
                for i, ex in enumerate(prior_examples, 1):
                    history = ex.get("interaction_history")
                    if history and isinstance(history, list):
                        # Full interaction replay (original format)
                        examples_text += f"Example {i}:\n"
                        for msg in history:
                            role = msg.get("role", "user")
                            content = msg.get("content", "")
                            if role == "system":
                                continue
                            label = "Agent" if role == "assistant" else "User"
                            examples_text += f"{label}: {content}\n"
                        examples_text += "\n"
                    else:
                        # Fallback: problem + answer summary
                        examples_text += (
                            f"Example {i}:\n"
                            f"Task: {ex['problem'][:800]}\n"
                            f"Solution: {ex['answer'][:800]}\n\n"
                        )
                messages.append({"role": "user", "content": examples_text})
                messages.append(
                    {
                        "role": "assistant",
                        "content": "I've reviewed the examples. Ready.",
                    }
                )

            # Initial task message — always use the full problem text which
            # contains the system prompt, schema, AND task instruction.
            # env.reset() is called for side effects (DB init, container
            # start) but its return value (schema-only observation) is
            # intentionally NOT used as the prompt because record.problem
            # already has everything the agent needs.
            task_content = problem_text
            messages.append({"role": "user", "content": task_content})

            # Use environment's max_turns if available, else default
            max_turns = (
                env.max_turns
                if hasattr(env, "max_turns")
                else self._MAX_INTERACTIVE_TURNS_DEFAULT
            )

            for turn in range(max_turns):
                # Format conversation as prompt for the backend
                prompt = self._format_messages_as_prompt(messages)

                full = self._backend.generate_full(
                    prompt,
                    model=cfg.model,
                    system=system_prompt,
                    temperature=cfg.temperature,
                    max_tokens=cfg.max_tokens,
                )
                content = full.get("content", "")
                usage = full.get("usage", {})
                total_latency += full.get("latency_seconds", 0.0)
                total_prompt_tokens += usage.get("prompt_tokens", 0)
                total_completion_tokens += usage.get("completion_tokens", 0)
                total_cost += full.get("cost_usd", 0.0)
                all_responses.append(content)

                # Strip <think> tags before parsing actions
                cleaned = _runner._strip_think_tags(content)
                messages.append({"role": "assistant", "content": cleaned})

                # Step the environment
                observation, is_done = env.step(cleaned)
                messages.append({"role": "user", "content": observation})

                if is_done:
                    break

            # Evaluate
            is_correct, scoring_meta = env.evaluate()
            scoring_meta["num_turns"] = len(all_responses)
            scoring_meta["interactive"] = True
            # Store full interaction history for lifelong example injection.
            # Filter out system messages to save space.
            scoring_meta["_interaction_history"] = [
                msg for msg in messages if msg.get("role") != "system"
            ]

            score_val = _runner._extract_continuous_score(scoring_meta, is_correct)
            return _runner.EvalResult(
                record_id=record.record_id,
                model_answer="\n---\n".join(all_responses),
                is_correct=is_correct,
                score=score_val,
                latency_seconds=total_latency,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                cost_usd=total_cost,
                scoring_metadata=scoring_meta,
                trace_data=full.get("trace_data"),
                # Spec §6.2 extended fields. framework/commit are constant
                # per backend, so the last turn's value is correct. tool_calls
                # / turn_count come from the interactive loop itself.
                framework=full.get("framework", "openjarvis"),
                framework_commit=full.get("framework_commit", ""),
                tool_calls=int(full.get("tool_calls", 0)),
                turn_count=len(all_responses),
            )
        except Exception as exc:
            _runner.LOGGER.error(
                "Interactive processing failed for %s: %s",
                record.record_id,
                exc,
            )
            return _runner.EvalResult(
                record_id=record.record_id,
                model_answer="",
                error=str(exc),
                scoring_metadata={"interactive": True, "error": str(exc)},
                framework=getattr(self._backend, "framework_name", "openjarvis"),
                framework_commit=getattr(self._backend, "framework_commit_value", "")
                or "",
                tool_calls=0,
                turn_count=0,
            )
        finally:
            if env is not None:
                try:
                    env.close()
                except Exception:
                    pass

    @staticmethod
    def _format_messages_as_prompt(messages: List[Dict[str, str]]) -> str:
        """Format a message list as a single prompt string.

        Uses a clear role-labeled format that works with most LLMs when
        passed as a user prompt via the backend.
        """
        parts: List[str] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                # System prompt handled separately via backend's system param
                continue
            elif role == "user":
                parts.append(f"[User]\n{content}")
            elif role == "assistant":
                parts.append(f"[Assistant]\n{content}")
        parts.append("[Assistant]")  # Prompt the next assistant turn
        return "\n\n".join(parts)


__all__ = ["_RunnerModesMixin"]
