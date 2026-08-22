"""The ``write_todo`` node: write the coach agent's plan of work for this request."""

from typing import Literal, TypedDict

from src.schemas import GraphState
from src.services.todo import generate_todo
from src.utils.logging import logger


class TodoItem(TypedDict):
    """One step on the coach agent's list."""

    id: int
    task: str
    status: Literal["pending", "in_progress", "done"]


class TodoUpdate(TypedDict):
    """The state ``write_todo`` writes."""

    todo: list[dict]


def to_todo_items(tasks: list[str]) -> list[TodoItem]:
    """Number the written steps and mark them all outstanding."""

    return [
        TodoItem(id=number, task=task, status="pending")
        for number, task in enumerate(tasks, start=1)
    ]


async def write_todo(state: GraphState) -> TodoUpdate:
    """Generate a dynamic todo list for the current coaching request."""

    plan = state.get("plan")
    profile = state.get("profile")
    user_query = state["user_query"]

    tasks = await generate_todo(
        user_query=user_query, profile=profile, plan=plan
    )
    todo = to_todo_items(tasks)

    return {"todo": list(todo)}
