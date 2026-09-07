"""Tests for the ``load_exercise`` tool and the catalogue filtering behind it."""

import json
from pathlib import Path

import pytest
from langchain.tools import ToolRuntime

from src.enums import (
    BodyRegion,
    EquipmentType,
    MovementPattern,
    MuscleGroup,
)
from src.schemas import (
    CoachContext,
    Exercise,
    UserProfile,
)
from src.services import catalogue
from src.tools import COACH_TOOLS, load_exercise
from src.tools.context import context_profile
from src.tools.load_exercise import SlotQuery
from tests.test_load_user_context import COMPLETE_PROFILE

DATA_DIR = Path("data")

SHOULDER_INJURY: dict = {
    "body_part": "shoulder",
    "status": "ACTIVE",
    "restrictions": [
        {"movement_pattern": "VERTICAL_PUSH", "action": "PROHIBITED"},
    ],
}


@pytest.fixture(scope="module")
def exercises() -> list[Exercise]:
    """The seeded catalogue, as the tool hands it to the agent."""
    rows = json.loads((DATA_DIR / "exercises.json").read_text())
    return [Exercise.model_validate(row) for row in rows]


def _profile(**overrides) -> UserProfile:
    """A complete profile, with whatever this test wants to constrain."""
    return UserProfile.model_validate(COMPLETE_PROFILE | overrides)


def _runtime(profile: dict | None) -> ToolRuntime:
    """The runtime the agent builds around a tool call, carrying the coach's context."""
    return ToolRuntime(
        state=None,
        config={},
        stream_writer=None,
        tool_call_id="call_1",
        store=None,
        context=CoachContext(user_id="user-1", profile=profile),
    )


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch, exercises):
    """Serve the seed file in place of Postgres, narrowing as the query does."""

    async def _fetch(
        movement_patterns,
        *,
        body_region=None,
        exclude_ids=None,
    ) -> list[Exercise]:
        return [
            exercise
            for exercise in exercises
            if (not movement_patterns or exercise.movement_pattern in movement_patterns)
            and (body_region is None or exercise.body_region is body_region)
            and (not exclude_ids or exercise.id not in exclude_ids)
        ]

    monkeypatch.setattr(catalogue, "fetch_exercises", _fetch)


# --- Filtering on the user's constraints ------------------------------------------------


def test_an_injury_removes_the_movement_it_prohibits(exercises) -> None:
    """A prescription the profile forbids is the failure the tool exists to prevent."""
    profile = _profile(injuries=[SHOULDER_INJURY])

    permitted = catalogue.allowed_exercises(exercises, profile)

    assert any(
        exercise.movement_pattern is MovementPattern.VERTICAL_PUSH
        for exercise in exercises
    )
    assert not any(
        exercise.movement_pattern is MovementPattern.VERTICAL_PUSH
        for exercise in permitted
    )


def test_a_resolved_injury_restricts_nothing(exercises) -> None:
    """`InjuryStatus.RESOLVED` is what a user says when they have recovered."""
    profile = _profile(injuries=[SHOULDER_INJURY | {"status": "RESOLVED"}])

    assert len(catalogue.allowed_exercises(exercises, profile)) == len(exercises)


def test_equipment_the_user_does_not_own_is_removed(exercises) -> None:
    """Prescribing a barbell to someone with dumbbells is a plan they cannot follow."""
    profile = _profile(
        available_equipment={"equipment": [EquipmentType.DUMBBELL]},
    )

    permitted = catalogue.allowed_exercises(exercises, profile)

    assert permitted
    assert not any(
        EquipmentType.BARBELL in exercise.equipment for exercise in permitted
    )


def test_bodyweight_is_available_to_everyone(exercises) -> None:
    """Nobody lists their own body as equipment, and dropping press-ups is absurd."""
    profile = _profile(available_equipment={"equipment": [EquipmentType.DUMBBELL]})

    permitted = catalogue.allowed_exercises(exercises, profile)

    assert any(
        exercise.equipment == [EquipmentType.BODYWEIGHT] for exercise in permitted
    )


def test_an_unrecorded_equipment_list_does_not_empty_the_catalogue(exercises) -> None:
    """Equipment is not a required profile field, so nobody was ever asked for it."""
    permitted = catalogue.allowed_exercises(exercises, _profile())

    assert len(permitted) == len(exercises)


def test_no_profile_filters_nothing(exercises) -> None:
    """Unreachable past the context gate; the filter must not silently return zero rows."""
    assert len(catalogue.allowed_exercises(exercises, None)) == len(exercises)


# --- Ranking ------------------------------------------------------------------------------


def test_the_slot_muscles_come_first(exercises) -> None:
    """A chest slot filled by the triceps work that ranks alphabetically first is wrong."""
    pushes = [
        exercise
        for exercise in exercises
        if exercise.movement_pattern is MovementPattern.HORIZONTAL_PUSH
    ]

    best = catalogue.rank_exercises(pushes, [MuscleGroup.CHEST])[0]

    assert MuscleGroup.CHEST in best.primary_muscles


def test_muscles_rank_rather_than_filter(exercises) -> None:
    """A slot whose muscles no row lists has to stay fillable, not return nothing."""
    pushes = [
        exercise
        for exercise in exercises
        if exercise.movement_pattern is MovementPattern.HORIZONTAL_PUSH
    ]

    ranked = catalogue.rank_exercises(pushes, [MuscleGroup.CALVES])

    assert len(ranked) == len(pushes)


def test_ranking_is_total_so_the_same_slot_gets_the_same_candidates(exercises) -> None:
    """An unstable order makes a re-run of the same plan a different plan."""
    first = [item.id for item in catalogue.rank_exercises(exercises, [])]
    second = [item.id for item in catalogue.rank_exercises(exercises[::-1], [])]

    assert first == second


# --- Selection ----------------------------------------------------------------------------


async def test_the_candidates_are_capped(seeded) -> None:
    """A hundred rows of catalogue would crowd out the plan the agent is writing."""
    found = await catalogue.find_exercises(None, [])

    assert len(found) == catalogue.MAX_EXERCISE_CANDIDATES


def test_the_cap_does_not_starve_a_slot_the_catalogue_can_fill(exercises) -> None:
    """Trimming candidates to save tokens must not leave a slot with nothing to choose."""
    pushes = [
        exercise
        for exercise in exercises
        if exercise.movement_pattern is MovementPattern.HORIZONTAL_PUSH
    ]

    assert len(pushes[: catalogue.MAX_EXERCISE_CANDIDATES]) > 1


def test_the_candidate_carries_what_the_slot_is_checked_against(exercises) -> None:
    """The gate re-checks pattern, region and primary muscles; a blind pick fails it."""
    assert {
        "id",
        "name",
        "movement_pattern",
        "body_region",
        "primary_muscles",
        "equipment",
    } <= catalogue.CANDIDATE_FIELDS


def test_the_ranking_inputs_are_not_paid_for_twice(exercises) -> None:
    """Both are spent ordering the list the agent reads top-first; sending them repeats it."""
    assert "secondary_muscles" not in catalogue.CANDIDATE_FIELDS
    assert "difficulty" not in catalogue.CANDIDATE_FIELDS


async def test_exercises_already_used_can_be_excluded(seeded) -> None:
    """The same movement on every day of the week is a plan nobody wants."""
    first = await catalogue.find_exercises(
        None, [MovementPattern.HORIZONTAL_PUSH], limit=1
    )
    second = await catalogue.find_exercises(
        None, [MovementPattern.HORIZONTAL_PUSH], exclude_ids=[first[0].id], limit=1
    )

    assert first[0].id != second[0].id


async def test_an_unreachable_database_finds_nothing_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising tool aborts the agent's turn; an empty one lets it carry on."""

    async def _explode(movement_patterns, **kwargs) -> list[Exercise]:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(catalogue, "fetch_exercises", _explode)

    assert await catalogue.find_exercises(None, [MovementPattern.SQUAT]) == []


# --- The tool -----------------------------------------------------------------------------


def _slot(slot_id: str, patterns: list[MovementPattern], **overrides) -> dict:
    """One slot as the model passes it in the batch."""
    return {"slot_id": slot_id, "movement_patterns": patterns} | overrides


async def _invoke(slots: list[dict], profile: dict | None):
    """Call the tool as the agent's tool node would, so both content and artifact come back."""
    return await load_exercise.ainvoke(
        {
            "type": "tool_call",
            "name": load_exercise.name,
            "args": {"slots": slots, "runtime": _runtime(profile)},
            "id": "call_1",
        }
    )


async def test_the_tool_returns_candidates_the_agent_can_choose_between(seeded) -> None:
    """The agent prescribes by id, so the id and the name have to be in the payload."""
    result = await load_exercise.ainvoke(
        {
            "slots": [_slot("d1_s1", [MovementPattern.SQUAT])],
            "runtime": _runtime(COMPLETE_PROFILE),
        }
    )

    assert result["d1_s1"]
    assert all({"id", "name"} <= set(candidate) for candidate in result["d1_s1"])


async def test_the_tool_leaves_out_what_the_agent_does_not_choose_on(seeded) -> None:
    """Instructions for a hundred rows would cost more context than the plan itself, and
    the fields the gate re-checks afterwards were already spent as the query that picked
    these candidates — nothing left for the model to choose on but id and name."""
    result = await load_exercise.ainvoke(
        {
            "slots": [_slot("d1_s1", [MovementPattern.SQUAT])],
            "runtime": _runtime(COMPLETE_PROFILE),
        }
    )

    assert set(result["d1_s1"][0]) == {"id", "name"}
    assert json.dumps(result)


async def test_the_artifact_keeps_the_full_candidate_metadata(seeded) -> None:
    """The gate re-checks pattern, region and muscles; that has to survive somewhere even
    though the model itself never sees it."""
    result = await _invoke([_slot("d1_s1", [MovementPattern.SQUAT])], COMPLETE_PROFILE)

    assert set(result.artifact["exercises"][0]) == catalogue.CANDIDATE_FIELDS


async def test_the_compact_payload_matches_the_artifacts_slot_assignment(
    seeded,
) -> None:
    """The model has to be choosing from the same candidates the gate will check afterwards."""
    result = await _invoke([_slot("d1_s1", [MovementPattern.SQUAT])], COMPLETE_PROFILE)
    content = json.loads(result.content)

    assert [candidate["id"] for candidate in content["d1_s1"]] == (
        result.artifact["slots"]["d1_s1"]
    )


async def test_the_tool_filters_on_the_injury_the_model_never_passed(seeded) -> None:
    """The whole point of the out-of-band profile: the filter is not the model's to skip."""
    result = await load_exercise.ainvoke(
        {
            "slots": [_slot("d1_s1", [MovementPattern.VERTICAL_PUSH])],
            "runtime": _runtime(COMPLETE_PROFILE | {"injuries": [SHOULDER_INJURY]}),
        }
    )

    assert result == {"d1_s1": []}


async def test_the_tool_narrows_on_the_slot_it_was_given(seeded) -> None:
    """`required_body_region` is a slot constraint the gate re-checks afterwards."""
    result = await _invoke(
        [_slot("d1_s1", [MovementPattern.SQUAT], body_region=BodyRegion.LOWER)],
        COMPLETE_PROFILE,
    )

    assert all(
        candidate["body_region"] == BodyRegion.LOWER
        for candidate in result.artifact["exercises"]
    )


# --- The batch ------------------------------------------------------------------------------


async def test_every_slot_in_the_batch_gets_its_own_candidates(seeded) -> None:
    """One call has to answer the whole week, not just the slot the model asked last."""
    result = await load_exercise.ainvoke(
        {
            "slots": [
                _slot("d1_s1", [MovementPattern.HORIZONTAL_PUSH]),
                _slot("d2_s1", [MovementPattern.SQUAT]),
            ],
            "runtime": _runtime(COMPLETE_PROFILE),
        }
    )

    assert set(result) == {"d1_s1", "d2_s1"}
    assert result["d1_s1"] and result["d2_s1"]
    assert result["d1_s1"] != result["d2_s1"]


async def test_an_exercise_two_slots_share_is_sent_once(seeded) -> None:
    """Repeating the full candidate row per slot is what made a twenty-slot week cost what
    it did; the artifact still dedupes it by id, even though the compact payload the model
    reads is cheap enough per slot on its own."""
    result = await _invoke(
        [
            _slot("d1_s1", [MovementPattern.SQUAT]),
            _slot("d3_s1", [MovementPattern.SQUAT]),
        ],
        COMPLETE_PROFILE,
    )

    sent = [candidate["id"] for candidate in result.artifact["exercises"]]

    assert result.artifact["slots"]["d1_s1"] == result.artifact["slots"]["d3_s1"]
    assert sent == list(dict.fromkeys(sent))
    assert len(sent) == len(result.artifact["slots"]["d1_s1"])


async def test_the_ids_a_slot_lists_are_all_in_the_payload(seeded) -> None:
    """A slot pointing at an id the batch never sent leaves the agent nothing to prescribe."""
    result = await _invoke(
        [
            _slot("d1_s1", [MovementPattern.HORIZONTAL_PUSH]),
            _slot("d2_s1", [MovementPattern.HINGE]),
        ],
        COMPLETE_PROFILE,
    )

    sent = {candidate["id"] for candidate in result.artifact["exercises"]}

    assert all(set(ids) <= sent for ids in result.artifact["slots"].values())


# --- The context the tool reads -------------------------------------------------------------


def test_a_missing_context_reads_as_no_profile() -> None:
    """Invoked without context, the tool must not crash the agent's turn."""
    assert context_profile(_runtime(None)) is None


def test_an_unusable_profile_reads_as_no_profile() -> None:
    """A half-filled profile is unreachable past the gate, but is not worth raising over."""
    assert context_profile(_runtime({"age": 34})) is None


def test_a_stored_profile_is_read_back_as_the_domain_model() -> None:
    """The filters are methods on `UserProfile`, not on the dict the store holds."""
    assert context_profile(_runtime(COMPLETE_PROFILE)) == UserProfile.model_validate(
        COMPLETE_PROFILE
    )


# --- Binding ------------------------------------------------------------------------------


def test_the_tool_is_bound_to_the_coach_agent() -> None:
    """Written but unbound, the agent would invent exercises instead of looking them up."""
    assert load_exercise in COACH_TOOLS


def test_the_profile_is_not_an_argument_the_model_can_get_wrong() -> None:
    """A filter the model has to remember to pass is advisory, not a constraint."""
    properties = set(load_exercise.tool_call_schema.model_json_schema()["properties"])

    assert properties == {"slots"}


def test_a_slot_asks_for_everything_that_narrows_it() -> None:
    """Batching must not cost the per-slot constraints the single-slot tool accepted."""
    assert set(SlotQuery.model_fields) == {
        "slot_id",
        "movement_patterns",
        "target_muscles",
        "body_region",
        "exclude_ids",
    }


# --- Against the seeded table ---------------------------------------------------------------


@pytest.mark.integration
async def test_the_pattern_and_region_narrowing_runs_in_the_database(
    require_postgres: None,
) -> None:
    """Both are indexed columns, and the filter is the query rather than a list scan."""
    found = await catalogue.fetch_exercises(
        [MovementPattern.SQUAT, MovementPattern.HINGE], body_region=BodyRegion.LOWER
    )

    assert found
    assert all(
        exercise.movement_pattern in {MovementPattern.SQUAT, MovementPattern.HINGE}
        and exercise.body_region is BodyRegion.LOWER
        for exercise in found
    )


@pytest.mark.integration
async def test_a_seeded_lookup_fills_a_real_slot(require_postgres: None) -> None:
    """The 4-day template's first slot is a horizontal push for chest."""
    found = await catalogue.find_exercises(
        _profile(),
        [MovementPattern.HORIZONTAL_PUSH],
        target_muscles=[MuscleGroup.CHEST],
    )

    assert found
    assert MuscleGroup.CHEST in found[0].primary_muscles
