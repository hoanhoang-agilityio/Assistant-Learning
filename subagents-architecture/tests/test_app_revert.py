"""Tests for going back to an earlier plan.

``resolve_version`` is gone. It existed to map *"the original plan"* onto a
``version_id`` with a model call, and the supervisor has already read the
conversation that phrase came from — so ``list_versions`` shows the index and
``restore_version`` takes an id from it
(``docs/supervisor-architecture.md`` §1, §4.2).

What did not change is everything that makes a restore safe:

* it is an **append**, not a rewind — the versions since are not deleted, so the
  user can undo the undo, and they will
* the restored plan is **re-verified**, because a plan that was valid when it was
  saved may not be valid now
* an id the model invented reaches no database lookup
* the user is told *why* it was re-checked, not just that it was
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from app.core.langgraph.plans.versioning import describe_verification_reason, render_versions
from app.core.langgraph.runtime import draft_store as drafts
from app.core.langgraph.supervisor import tools as supervisor_tools
from tests.support import call, message, updates

PROFILE = {
    "weight_kg": 75.0,
    "height_cm": 175.0,
    "age": 28,
    "sex": "male",
    "activity_level": "light",
    "days_per_week": 4,
    "level": 3,
    "goal": "fat_loss",
    "equipment": ["barbell"],
    "injuries": [],
}

INDEX = [
    {"version_id": "v3-id", "label": "v3", "created_at": "2026-08-03T00:00:00"},
    {"version_id": "v2-id", "label": "v2", "created_at": "2026-08-02T00:00:00"},
    {"version_id": "v1-id", "label": "v1", "created_at": "2026-08-01T00:00:00"},
]


def _plan(name: str) -> dict:
    """A one-day plan labelled so a test can tell which version it came from."""
    return {
        "template_id": "upper_lower_4day",
        "days": [
            {
                "name": f"{name} day",
                "exercises": [
                    {
                        "slot_id": "s0",
                        "exercise_id": "back_squat",
                        "name": "Back Squat",
                        "sets": 4,
                        "reps": [5, 8],
                        "rir": [1, 2],
                    }
                ],
            }
        ],
    }


def _state(**overrides) -> dict:
    """Build a supervisor state the version tools can read."""
    return {
        "messages": [],
        "profile": dict(PROFILE),
        "plan": _plan("current"),
        "macros": {"kcal": 2100, "tdee": 2400, "goal": "fat_loss"},
        "episodic_context": "",
        "current_version_id": "v3-id",
        "missing_fields": [],
        "goal_conflict": None,
        **overrides,
    }


def _config(user_id: str | None = "1") -> dict:
    """A runnable config with a unique thread id and an owner."""
    return {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "metadata": {"user_id": user_id, "session_id": "s-1"},
    }


@pytest.fixture(autouse=True)
def _stored_versions(monkeypatch):
    """Serve the version index and the snapshots from memory, not Postgres."""
    stored = {
        entry["version_id"]: SimpleNamespace(
            id=entry["version_id"],
            user_id=1,
            label=entry["label"],
            plan=_plan(entry["label"]),
            macros={"kcal": 2000, "tdee": 2300, "goal": "fat_loss"},
            # Deliberately not the current profile's hash: the restore has to
            # say the details have moved, which is the one line that stops a
            # re-check reading as a rubber stamp.
            profile_hash="stale-hash",
            rubric_version="v1",
        )
        for entry in INDEX
    }

    async def fake_index(_user_id):
        return list(INDEX)

    async def fake_get(version_id):
        return stored.get(version_id)

    monkeypatch.setattr("app.core.langgraph.supervisor.tools.versions.version_index", fake_index)
    monkeypatch.setattr("app.core.langgraph.supervisor.tools.versions.get_version", fake_get)
    monkeypatch.setattr(
        "app.core.langgraph.supervisor.tools.versions.profile_hash", lambda _profile: "current-hash"
    )
    monkeypatch.setattr("app.core.langgraph.supervisor.tools.versions.rubric_version", lambda: "v1")
    monkeypatch.setattr("app.core.langgraph.plans.rendering.load_catalog", lambda *a, **k: {})
    return stored


@pytest.fixture
def scored(monkeypatch):
    """Score every restored plan as a pass, without a rubric database."""
    seen: list[dict] = []

    async def fake_score(plan, profile, scope=None):
        seen.append({"plan": plan, "profile": profile})
        return {"kcal": 2050, "tdee": 2350, "goal": profile["goal"]}, [], "pass"

    monkeypatch.setattr("app.core.langgraph.supervisor.tools.versions.score", fake_score)
    return seen


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


async def test_the_versions_are_listed_for_the_user_to_choose_from():
    """The list is loaded fresh: a plan may have been saved in another session."""
    result = await call(supervisor_tools.list_versions, _state(), _config())
    body = json.loads(message(result).content)

    assert body["status"] == "versions"
    assert body["current"] == "v3-id"
    for entry in INDEX:
        assert entry["version_id"] in body["rendered"]


async def test_one_version_is_no_history_at_all(monkeypatch):
    """The only version saved is the plan they already have."""

    async def only_one(_user_id):
        return INDEX[:1]

    monkeypatch.setattr("app.core.langgraph.supervisor.tools.versions.version_index", only_one)

    result = await call(supervisor_tools.list_versions, _state(), _config())
    assert json.loads(message(result).content)["status"] == "no_history"


async def test_an_anonymous_session_has_no_history():
    """Nothing was stored, so there is nothing to go back to."""
    result = await call(supervisor_tools.list_versions, _state(), _config(user_id=None))
    assert json.loads(message(result).content)["status"] == "no_history"


def test_render_versions_marks_the_current_one():
    """The user is choosing between them, so which one they are on matters."""
    rendered = render_versions(INDEX)
    assert "(current)" in rendered.splitlines()[0]
    assert "(current)" not in "\n".join(rendered.splitlines()[1:])


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------


async def test_restoring_produces_a_draft_not_a_saved_plan(scored):
    """A restore stops at the confirm gate like any other overwrite."""
    drafts.clear()
    result = await call(supervisor_tools.restore_version, _state(), _config(), version_id="v1-id")
    body = json.loads(message(result).content)

    assert body["status"] == "draft"
    assert "plan" not in updates(result), "a restore changed the stored plan on its own"

    draft = drafts.read(body["draft_id"])
    assert draft.plan["days"][0]["name"].startswith("v1")


async def test_the_restored_plan_is_reverified(scored):
    """A plan that was valid when saved may not be valid for the user now."""
    drafts.clear()
    await call(supervisor_tools.restore_version, _state(), _config(), version_id="v1-id")

    assert scored, "the verifiers did not run on the restored plan"
    assert scored[0]["plan"]["days"][0]["name"].startswith("v1")


async def test_the_restored_draft_carries_recomputed_macros(scored):
    """The old targets belong to the old profile."""
    drafts.clear()
    result = await call(supervisor_tools.restore_version, _state(), _config(), version_id="v1-id")
    draft = drafts.read(json.loads(message(result).content)["draft_id"])

    assert draft.macros["kcal"] == 2050, "the version's stored macros were reused"


async def test_the_answer_says_whether_the_old_checks_still_apply(scored):
    """The user is told why it was re-checked, not just that it was."""
    drafts.clear()
    result = await call(supervisor_tools.restore_version, _state(), _config(), version_id="v1-id")
    draft = drafts.read(json.loads(message(result).content)["draft_id"])

    notes = [issue for issue in draft.issues if issue["rubric_ref"] == "versions.restore"]
    assert len(notes) == 1
    assert "changed" in notes[0]["message"], (
        "a stale profile hash must be reported, not silently ignored"
    )


async def test_a_restore_is_an_append_and_records_where_it_came_from(scored, monkeypatch):
    """Restore v1 creates v4 with v1's content — it does not rewind.

    The intermediate versions must survive, or the user cannot undo the undo.
    """
    drafts.clear()
    written: list[dict] = []

    async def fake_insert(**kwargs):
        written.append(kwargs)
        return {"version_id": "v4-id", "label": "v4", "created_at": "2026-08-10T00:00:00"}

    monkeypatch.setattr(
        "app.core.langgraph.supervisor.tools.persistence.insert_version", fake_insert
    )

    restored = await call(supervisor_tools.restore_version, _state(), _config(), version_id="v1-id")
    draft_id = json.loads(message(restored).content)["draft_id"]
    await call(supervisor_tools.save_plan, _state(), _config(), draft_id=draft_id)

    assert len(written) == 1
    assert written[0]["restored_from"] == "v1-id", "the restore source was not recorded"
    assert written[0]["parent_id"] == "v3-id", "the superseded version was not recorded"
    assert written[0]["plan"]["days"][0]["name"].startswith("v1")


async def test_a_version_that_does_not_exist_is_reported(scored):
    """An id the model invented reaches no lookup that could succeed."""
    result = await call(supervisor_tools.restore_version, _state(), _config(), version_id="made-up")
    body = json.loads(message(result).content)

    assert body["status"] == "refused"
    assert "list_versions" in body["reason"]
    assert scored == []


async def test_another_users_version_is_not_readable(scored, _stored_versions):
    """An id belonging to someone else is not a version this session may read."""
    _stored_versions["v1-id"].user_id = 999

    result = await call(supervisor_tools.restore_version, _state(), _config(), version_id="v1-id")
    body = json.loads(message(result).content)

    assert body["status"] == "refused"
    # Worded as though it does not exist. Saying "that is not yours" would
    # confirm it is someone's.
    assert "no version" in body["reason"]
    assert scored == []


# ---------------------------------------------------------------------------
# Explaining the re-check
# ---------------------------------------------------------------------------


def test_verification_reason_distinguishes_a_moved_profile():
    """The hash decides what the user is told, not whether the checks run."""
    same = describe_verification_reason("abc", "abc")
    moved = describe_verification_reason("abc", "def")

    assert "unchanged" in same
    assert "have changed" in moved


def test_a_missing_stored_hash_is_treated_as_moved():
    """An old row without a fingerprint cannot claim its checks still apply."""
    assert "have changed" in describe_verification_reason("", "def")
