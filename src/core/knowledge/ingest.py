"""Seed and ingest helpers for the local knowledge base."""

from core.knowledge.schema import KnowledgeDocument
from core.knowledge.store import KnowledgeStore

_SEED_DOCUMENTS: list[KnowledgeDocument] = [
    KnowledgeDocument(
        id="hypertrophy-volume-guideline",
        title="Hypertrophy Weekly Set Volume",
        content=(
            "Most muscle groups respond well to roughly 10-20 hard sets per week for hypertrophy. "
            "Beginners often progress with the lower end, while trained individuals may need the "
            "upper range. Spread volume across 2-4 sessions per muscle group where possible."
        ),
        category="hypertrophy",
        tags=["volume", "sets", "hypertrophy", "muscle_gain"],
        goal_applicability=["muscle_gain", "recomposition", "general_fitness"],
        equipment_applicability=["gym", "home", "bodyweight"],
        source_type="guideline",
        source_url="local-kb://hypertrophy-volume-guideline",
        trust_score=0.95,
    ),
    KnowledgeDocument(
        id="safe-fat-loss-rate",
        title="Safe Fat Loss Rate",
        content=(
            "A generally safe fat-loss rate is about 0.5-0.75 kg per week for most adults. "
            "Faster rates increase muscle-loss risk, adherence problems, and recovery stress. "
            "Aggressive deficits should be paired with higher protein and resistance training."
        ),
        category="fat_loss",
        tags=["deficit", "weight loss", "safe rate", "fat_loss"],
        goal_applicability=["fat_loss"],
        equipment_applicability=["gym", "home", "bodyweight"],
        source_type="guideline",
        source_url="local-kb://safe-fat-loss-rate",
        trust_score=0.94,
    ),
    KnowledgeDocument(
        id="lean-bulk-surplus",
        title="Lean Bulk Calorie Surplus",
        content=(
            "Lean muscle gain is usually best supported by a modest calorie surplus of roughly "
            "150-300 kcal per day, combined with progressive resistance training and adequate protein. "
            "Very large surpluses increase fat gain without proportionally faster muscle accrual."
        ),
        category="muscle_gain",
        tags=["surplus", "lean bulk", "muscle_gain"],
        goal_applicability=["muscle_gain"],
        equipment_applicability=["gym", "home"],
        source_type="guideline",
        source_url="local-kb://lean-bulk-surplus",
        trust_score=0.93,
    ),
    KnowledgeDocument(
        id="recomposition-protocol",
        title="Body Recomposition Protocol",
        content=(
            "Body recomposition is most realistic for beginners, returning trainees, or those with "
            "higher body fat. Use high protein intake around 1.8-2.4 g/kg, resistance training priority, "
            "and a slight deficit or maintenance calories depending on recovery and performance."
        ),
        category="recomposition",
        tags=["recomposition", "protein", "maintenance", "hypertrophy"],
        goal_applicability=["recomposition"],
        equipment_applicability=["gym", "home", "bodyweight"],
        source_type="guideline",
        source_url="local-kb://recomposition-protocol",
        trust_score=0.92,
    ),
    KnowledgeDocument(
        id="progressive-overload",
        title="Progressive Overload Basics",
        content=(
            "Progressive overload can be achieved by adding load, reps, sets, or improved technique over time. "
            "A practical approach is to increase load by 2.5-5 kg or add 1-2 reps when all target sets are completed "
            "at the top of the prescribed rep range."
        ),
        category="progression",
        tags=["progression", "overload", "strength", "muscle_gain"],
        goal_applicability=["muscle_gain", "strength", "recomposition", "general_fitness"],
        equipment_applicability=["gym", "home", "bodyweight"],
        source_type="curated_note",
        source_url="local-kb://progressive-overload",
        trust_score=0.9,
    ),
    KnowledgeDocument(
        id="protein-intake-guideline",
        title="Protein Intake for Training Goals",
        content=(
            "Protein intakes around 1.6-2.4 g/kg/day support muscle retention and growth across fat loss, "
            "recomposition, and muscle-gain goals. Higher intakes may help during aggressive deficits."
        ),
        category="nutrition",
        tags=["protein", "macro", "nutrition"],
        goal_applicability=["fat_loss", "muscle_gain", "recomposition", "strength"],
        equipment_applicability=["gym", "home", "bodyweight"],
        source_type="guideline",
        source_url="local-kb://protein-intake-guideline",
        trust_score=0.94,
    ),
    KnowledgeDocument(
        id="endurance-progression",
        title="Endurance Progression",
        content=(
            "Endurance adaptations improve with gradual increases in weekly duration or intensity, often using "
            "10 percent weekly progression caps and periodic recovery weeks to reduce overuse risk."
        ),
        category="endurance",
        tags=["endurance", "conditioning", "progression"],
        goal_applicability=["endurance", "general_fitness"],
        equipment_applicability=["gym", "home", "bodyweight"],
        source_type="curated_note",
        source_url="local-kb://endurance-progression",
        trust_score=0.88,
    ),
    KnowledgeDocument(
        id="aggressive-cut-safety",
        title="Aggressive Cut Safety Limits",
        content=(
            "Weight-loss targets above about 1.0 kg per week are usually unrealistic or unsafe for most people. "
            "Such timelines increase lean-mass loss, hormonal disruption, and rebound risk. A longer timeline "
            "with moderate deficit is preferred."
        ),
        category="safety",
        tags=["safety", "aggressive", "fat_loss", "timeline"],
        goal_applicability=["fat_loss"],
        equipment_applicability=["gym", "home", "bodyweight"],
        source_type="guideline",
        source_url="local-kb://aggressive-cut-safety",
        trust_score=0.96,
    ),
]


def seed_default_corpus(store: KnowledgeStore | None = None) -> KnowledgeStore:
    """Persist the default curated corpus if it does not already exist."""
    resolved_store = store or KnowledgeStore()
    if resolved_store.load_documents():
        return resolved_store
    resolved_store.save_documents(_SEED_DOCUMENTS)
    return resolved_store
