"""Generation of the coach agent's plan of work for one coaching request."""

import json
from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.core.configs.config import settings
from src.core.langgraph.prompts import build_todo_writer_messages
from src.utils.logging import logger

MAX_TODO_STEPS = 8

# Used when the writer is unavailable. Deliberately generic and tool-free: it keeps the
# coaching turn moving with the same kind of instruction the writer would have produced.
FALLBACK_TASKS: tuple[str, ...] = (
    "Establish what the user is asking for in this request.",
    "Set the calorie and macro targets that suit the user's profile and goal.",
    "Build the training week that the user's profile, goal and constraints call for.",
    "Return the complete plan.",
)

_WRITER_TOKEN_LIMIT = 512


class TodoPlan(BaseModel):
    """Structured output for the todo writer."""

    tasks: list[str] = Field(
        description="Ordered steps for the coach agent, one imperative sentence each.",
    )


@lru_cache
def _build_writer() -> ChatOpenAI:
    """Build the shared todo-writer model from application settings."""
    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=settings.DEFAULT_LLM_MODEL,
        max_completion_tokens=_WRITER_TOKEN_LIMIT,
    )


def _as_prompt_json(value: dict[str, Any] | None) -> str | None:
    """Render a profile or plan for the prompt, or None when there is nothing to render."""

    if not value:
        return None
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def usable_tasks(tasks: list[str]) -> list[str]:
    """Keep the steps that carry text, capped at what a single turn should attempt."""

    return [task.strip() for task in tasks if task.strip()][:MAX_TODO_STEPS]


async def generate_todo(
    user_query: str, profile: dict[str, Any] | None, plan: dict[str, Any] | None
) -> list[str]:
    """Write the ordered steps the coach agent has to complete for this request."""

    try:
        writer = _build_writer().with_structured_output(TodoPlan)
        todo_plan = await writer.ainvoke(
            build_todo_writer_messages(
                user_query=user_query,
                profile=_as_prompt_json(profile) or "none on record",
                plan=_as_prompt_json(plan),
            )
        )
    except Exception as error:
        logger.exception("todo_generation_failed", error=str(error))
        return list(FALLBACK_TASKS)

    tasks = usable_tasks(todo_plan.tasks)
    if not tasks:
        logger.warning("todo_generation_empty")
        return list(FALLBACK_TASKS)

    return tasks
