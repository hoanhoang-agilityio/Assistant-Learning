"""Tests for verification: the rubric checks and the scoring facade over them.

Every check here is a pure function over a fixture catalog, so nothing touches
Postgres, a model or HTTP. Verification is no longer a subgraph, so what is
asserted is the behaviour of :func:`run_checks` and :func:`score` rather than a
topology.

The properties worth regression-testing are the design's own claims:

* the verifier cannot see the build transcript
* injuries match on attributes, so a newly added exercise is caught
* a muscle with no landmark is reported as unassessed, not passed
* scope narrows which checks run, and an empty scope runs all three
"""

import inspect

import pytest

from app.core.langgraph import scoring
from app.core.langgraph.checks import check_injury, check_macro, check_volume
from app.core.langgraph.scoring import run_checks, score, sort_issues
from tests.seed import CONTRAINDICATIONS, MACRO_RULES, RUBRIC_VERSION, VOLUME_LANDMARKS

CATALOG = {
    "bb_back_squat": {
        "name": "Barbell back squat",
        "movement_pattern": "squat",
        "joint_actions": ["knee_flexion_deep", "hip_extension"],
        "loaded_positions": ["knee_end_range"],
        "contribution": {"quads": 1.0, "glutes": 0.5},
    },
    "leg_press": {
        "name": "Leg press",
        "movement_pattern": "squat",
        "joint_actions": ["knee_extension", "hip_extension"],
        "loaded_positions": [],
        "contribution": {"quads": 1.0, "glutes": 0.3},
    },
    "hack_squat": {
        "name": "Hack squat",
        "movement_pattern": "squat",
        "joint_actions": ["knee_flexion_deep", "hip_extension"],
        "loaded_positions": ["knee_end_range"],
        "contribution": {"quads": 1.0},
    },
    "bb_bench_press": {
        "name": "Barbell bench press",
        "movement_pattern": "horizontal_push",
        "joint_actions": ["shoulder_horizontal_adduction", "elbow_extension"],
        "loaded_positions": [],
        "contribution": {"chest": 1.0, "triceps": 0.5, "front_delts": 0.5},
    },
    "walking_lunge": {
        "name": "Walking lunge",
        "movement_pattern": "lunge",
        "joint_actions": ["knee_extension", "hip_extension"],
        "loaded_positions": [],
        "contribution": {"quads": 0.8, "glutes": 0.8},
    },
}

PROFILE = {"weight_kg": 75.0, "height_cm": 175, "age": 28, "sex": "male", "injuries": []}


def _plan(*days: dict) -> dict:
    """Wrap day dicts into a plan."""
    return {"days": list(days)}


def _day(name: str, *exercises: tuple[str, int]) -> dict:
    """Build a training day from ``(exercise_id, sets)`` pairs."""
    return {
        "name": name,
        "exercises": [
            {"exercise_id": exercise_id, "sets": sets, "reps": [6, 8], "rir": 2}
            for exercise_id, sets in exercises
        ],
    }


def _severities(issues: list, source: str) -> list[str]:
    """Return the severities of issues from one verifier."""
    return [issue["severity"] for issue in issues if issue["source"] == source]


# ---------------------------------------------------------------------------
# Structural guarantees
# ---------------------------------------------------------------------------


def test_the_verifier_cannot_be_handed_a_transcript():
    """workflow.md 1.3: the verifier must be blind to the build process.

    ``VerifyState`` enforced this by omitting ``messages``. With the subgraph
    gone the same guarantee is in the signatures — there is no argument a
    message list could arrive in.
    """
    for function in (score, run_checks, check_macro, check_volume, check_injury):
        assert "messages" not in inspect.signature(function).parameters


def test_all_rubrics_share_one_version():
    """A report citing one version must not be produced partly under another."""
    assert (
        MACRO_RULES["rubric_version"]
        == VOLUME_LANDMARKS["rubric_version"]
        == CONTRAINDICATIONS["rubric_version"]
        == RUBRIC_VERSION
    )


# ---------------------------------------------------------------------------
# Macro
# ---------------------------------------------------------------------------


def test_macro_passes_a_sane_target():
    """A target inside every threshold produces no issues."""
    macros = {"kcal": 2100, "protein_g": 150, "fat_g": 70, "tdee": 2600}
    assert check_macro(macros, PROFILE, MACRO_RULES) == []


def test_macro_blocks_protein_below_floor():
    """Protein under 1.6 g/kg blocks and suggests the target instead."""
    macros = {"kcal": 2100, "protein_g": 90, "fat_g": 70, "tdee": 2600}
    issues = check_macro(macros, PROFILE, MACRO_RULES)
    protein = [i for i in issues if i["rubric_ref"] == "macro.protein_g_per_kg.min"]
    assert len(protein) == 1
    assert protein[0]["severity"] == "block"
    assert protein[0]["suggestion"] == {"protein_g": 150}


def test_macro_blocks_calories_below_floor():
    """A target under the sex-specific kcal floor blocks."""
    macros = {"kcal": 1200, "protein_g": 150, "fat_g": 70}
    issues = check_macro(macros, PROFILE, MACRO_RULES)
    assert "block" in _severities(issues, "macro")
    assert any(i["rubric_ref"] == "macro.floor_kcal" for i in issues)


def test_macro_blocks_an_over_aggressive_deficit():
    """More than 25% below maintenance blocks and suggests the capped figure."""
    macros = {"kcal": 1800, "protein_g": 150, "fat_g": 70, "tdee": 2600}
    issues = check_macro(macros, PROFILE, MACRO_RULES)
    deficit = [i for i in issues if i["rubric_ref"] == "macro.deficit.max_pct_tdee"]
    assert len(deficit) == 1
    assert deficit[0]["suggestion"] == {"kcal": 1950}


def test_macro_reports_missing_weight_rather_than_guessing():
    """Without body weight the check says so instead of assuming one."""
    issues = check_macro({"kcal": 2100}, {"sex": "male"}, MACRO_RULES)
    assert [i["severity"] for i in issues] == ["info"]
    assert "weight" in issues[0]["message"].lower()


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------


def test_volume_counts_fractional_contributions():
    """A bench set is 1.0 to chest and 0.5 to triceps, not 1.0 to both.

    24 weekly bench sets is chosen because the two counting rules disagree about
    it: chest is 24 either way and exceeds its MRV of 22, while triceps is 12
    fractionally (inside its range) but 24 if each set were credited whole,
    which would exceed the triceps MRV of 18. Exactly one block is therefore the
    signature of correct counting.
    """
    plan = _plan(
        _day("Push A", ("bb_bench_press", 8)),
        _day("Push B", ("bb_bench_press", 8)),
        _day("Push C", ("bb_bench_press", 8)),
    )
    issues = check_volume(plan, CATALOG, VOLUME_LANDMARKS)

    blocks = [i for i in issues if i["severity"] == "block"]
    assert [i["rubric_ref"] for i in blocks] == ["volume.chest.mrv"], (
        "triceps blocked too — sets are being credited whole to every muscle"
    )


def test_volume_reports_a_muscle_with_no_landmark_as_unassessed():
    """An unlisted muscle must be named, not silently passed.

    Silence reads as approval. Uses a muscle deliberately absent from the
    rubric, so the test keeps working as landmarks are added.
    """
    catalog = {
        "obscure_lift": {
            "name": "Obscure lift",
            "movement_pattern": "unknown",
            "joint_actions": [],
            "loaded_positions": [],
            "contribution": {"tibialis_anterior": 1.0},
        }
    }
    issues = check_volume(_plan(_day("Day", ("obscure_lift", 6))), catalog, VOLUME_LANDMARKS)

    unassessed = [i for i in issues if i["rubric_ref"] == "volume.muscles"]
    assert len(unassessed) == 1
    assert unassessed[0]["severity"] == "info"
    assert "not assessed" in unassessed[0]["message"]


def test_volume_blocks_above_mrv():
    """Quads past MRV blocks and suggests the top of MAV."""
    plan = _plan(
        _day("Legs A", ("bb_back_squat", 8), ("leg_press", 6)),
        _day("Legs B", ("bb_back_squat", 8), ("leg_press", 6)),
    )
    issues = check_volume(plan, CATALOG, VOLUME_LANDMARKS)
    quads = [i for i in issues if i["rubric_ref"] == "volume.quads.mrv"]
    assert len(quads) == 1
    assert quads[0]["severity"] == "block"
    assert quads[0]["suggestion"] == {"target_sets_week": 18}


def test_volume_warns_below_mev():
    """Too little volume warns rather than blocks — it is not dangerous."""
    plan = _plan(_day("Legs", ("leg_press", 3)))
    issues = check_volume(plan, CATALOG, VOLUME_LANDMARKS)
    quads = [i for i in issues if i["rubric_ref"] == "volume.quads.mev"]
    assert len(quads) == 1
    assert quads[0]["severity"] == "warn"


def test_volume_flags_an_unknown_exercise_without_crashing():
    """An exercise missing from the catalog is reported, not skipped in silence."""
    plan = _plan(_day("Legs", ("not_in_catalog", 4)))
    issues = check_volume(plan, CATALOG, VOLUME_LANDMARKS)
    assert any(i["rubric_ref"] == "volume.catalog" for i in issues)


# ---------------------------------------------------------------------------
# Injury
# ---------------------------------------------------------------------------


def test_injury_is_a_noop_without_declared_injuries():
    """No injuries means nothing to check."""
    plan = _plan(_day("Legs", ("bb_back_squat", 4)))
    assert check_injury(plan, PROFILE, CATALOG, CONTRAINDICATIONS) == []


def test_injury_blocks_on_joint_action_not_exercise_name():
    """The rule is a set intersection over attributes."""
    profile = {**PROFILE, "injuries": ["knee_pain_patellofemoral"]}
    plan = _plan(_day("Legs", ("bb_back_squat", 4)))
    issues = check_injury(plan, profile, CATALOG, CONTRAINDICATIONS)
    blocked = [i for i in issues if i["severity"] == "block"]
    assert len(blocked) == 1
    assert "knee_flexion_deep" in blocked[0]["message"]


def test_injury_catches_a_newly_added_exercise():
    """workflow.md 6.3: a name list would miss hack_squat; an attribute rule does not."""
    profile = {**PROFILE, "injuries": ["knee_pain_patellofemoral"]}
    plan = _plan(_day("Legs", ("hack_squat", 4)))
    issues = check_injury(plan, profile, CATALOG, CONTRAINDICATIONS)
    assert [i["severity"] for i in issues] == ["block"]


def test_injury_suggests_a_safe_alternative():
    """An issue carries a replacement, so repair has something to act on."""
    profile = {**PROFILE, "injuries": ["knee_pain_patellofemoral"]}
    plan = _plan(_day("Legs", ("bb_back_squat", 4)))
    issues = check_injury(plan, profile, CATALOG, CONTRAINDICATIONS)
    alternatives = issues[0]["suggestion"]["alternatives"]
    ids = {alt["exercise_id"] for alt in alternatives}
    assert "leg_press" in ids
    assert "hack_squat" not in ids, "an alternative must not carry the same contraindication"


def test_injury_enforces_a_pattern_set_cap():
    """The lunge cap applies across the week, not per session."""
    profile = {**PROFILE, "injuries": ["knee_pain_patellofemoral"]}
    plan = _plan(
        _day("A", ("walking_lunge", 3)),
        _day("B", ("walking_lunge", 3)),
    )
    issues = check_injury(plan, profile, CATALOG, CONTRAINDICATIONS)
    capped = [i for i in issues if i["rubric_ref"].endswith(".limit")]
    assert len(capped) == 1
    assert capped[0]["suggestion"] == {"max_sets_week": 4}


def test_injury_reports_an_unknown_injury_as_unassessed():
    """An injury with no rubric entry must not read as having been checked."""
    profile = {**PROFILE, "injuries": ["lower_back_disc_herniation"]}
    plan = _plan(_day("Legs", ("bb_back_squat", 4)))
    issues = check_injury(plan, profile, CATALOG, CONTRAINDICATIONS)
    assert [i["severity"] for i in issues] == ["info"]
    assert "not assessed" in issues[0]["message"]


# ---------------------------------------------------------------------------
# run_checks and score
# ---------------------------------------------------------------------------


MACROS = {"kcal": 2100, "protein_g": 150, "fat_g": 70, "tdee": 2600}

# `score` computes the macros itself, so it needs the fields `calc_macros`
# requires — which the checks alone do not read.
SCORE_PROFILE = {**PROFILE, "activity_level": "light", "goal": "muscle_gain"}


@pytest.fixture
def rubrics(monkeypatch):
    """Serve the seeded rubrics to the scoring helpers without a database.

    ``run_checks`` loads each rubric itself — that is the point of the helper,
    since a caller that had to fetch three rubrics could fetch two — so the
    seam the tests need is the loader, not an argument.
    """
    monkeypatch.setattr(scoring, "macro_rules", lambda: MACRO_RULES)
    monkeypatch.setattr(scoring, "volume_landmarks", lambda: VOLUME_LANDMARKS)
    monkeypatch.setattr(scoring, "contraindications", lambda: CONTRAINDICATIONS)


def _run(scope=None, **overrides):
    """Run the checks over a default plan and profile."""
    state = {
        "plan": _plan(_day("Legs", ("bb_back_squat", 4))),
        "profile": PROFILE,
        "computed_macros": MACROS,
        **overrides,
    }
    return run_checks(state["plan"], state["profile"], state["computed_macros"], CATALOG, scope)


def test_run_checks_collects_findings_from_every_check(rubrics):
    """All three checks contribute to one issue list."""
    issues, verdict = _run(
        profile={**PROFILE, "injuries": ["knee_pain_patellofemoral"]},
        computed_macros={"kcal": 1200, "protein_g": 90, "fat_g": 70, "tdee": 2600},
    )
    assert {issue["source"] for issue in issues} == {"macro", "volume", "injury"}
    assert verdict == "fail"


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (["injury"], {"injury"}),
        (["macro", "volume"], {"macro", "volume"}),
        ([], {"macro", "volume", "injury"}),
        (None, {"macro", "volume", "injury"}),
        (["nonsense"], {"macro", "volume", "injury"}),
    ],
)
def test_scope_selects_the_named_checks(rubrics, scope, expected):
    """A named scope runs exactly those; anything else assesses everything.

    An unrecognised scope must not scope *out* every check — scoring nothing
    and reporting a pass is the one outcome that must be unreachable.
    """
    issues, _ = _run(
        scope=scope,
        profile={**PROFILE, "injuries": ["knee_pain_patellofemoral"]},
        computed_macros={"kcal": 1200, "protein_g": 90, "fat_g": 70},
        plan=_plan(_day("Legs", ("bb_back_squat", 4)), _day("More legs", ("leg_press", 30))),
    )
    assert {issue["source"] for issue in issues} == expected


def test_clean_plan_passes(rubrics):
    """A plan inside every threshold produces a pass verdict."""
    issues, verdict = _run(scope=["macro", "injury"], plan=_plan(_day("Legs", ("leg_press", 5))))
    assert issues == []
    assert verdict == "pass"


def test_warnings_alone_do_not_fail(rubrics):
    """A warn-only run must not spend the repair budget."""
    _, verdict = _run(scope=["volume"], plan=_plan(_day("Legs", ("leg_press", 3))))
    assert verdict == "warn"


async def test_score_computes_macros_and_verifies_them_together(rubrics, monkeypatch):
    """The pairing `commit_draft` depends on: no verdict without macros.

    The macros the checks are graded on are the ones :func:`score` just
    computed, so a plan cannot be assessed against a target nobody produced.
    """
    monkeypatch.setattr(scoring, "load_catalog", lambda *a, **k: CATALOG)

    macros, issues, verdict = await score(_plan(_day("Legs", ("leg_press", 5))), SCORE_PROFILE)

    assert macros["kcal"] > 0
    assert verdict in ("pass", "warn", "fail")
    assert all(issue["source"] in ("macro", "volume", "injury") for issue in issues)


async def test_score_counts_sessions_off_the_plan(rubrics, monkeypatch):
    """TDEE follows the days the user will actually train, not the days asked for."""
    monkeypatch.setattr(scoring, "load_catalog", lambda *a, **k: CATALOG)
    profile = {**SCORE_PROFILE, "days_per_week": 6}

    two_days, *_ = await score(
        _plan(_day("A", ("leg_press", 4)), _day("B", ("bb_bench_press", 4))), profile
    )
    six_days, *_ = await score({"days": []}, profile)

    assert six_days["tdee"] > two_days["tdee"]


def test_sort_issues_puts_blocks_first():
    """Ordering is presentation, applied by the consumer, not by the checks."""
    issues = [
        {
            "source": "volume",
            "severity": "info",
            "location": "",
            "message": "",
            "suggestion": None,
            "rubric_ref": "",
        },
        {
            "source": "injury",
            "severity": "block",
            "location": "",
            "message": "",
            "suggestion": None,
            "rubric_ref": "",
        },
        {
            "source": "macro",
            "severity": "warn",
            "location": "",
            "message": "",
            "suggestion": None,
            "rubric_ref": "",
        },
    ]
    assert [i["severity"] for i in sort_issues(issues)] == ["block", "warn", "info"]
