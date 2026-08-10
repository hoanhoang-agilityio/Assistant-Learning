"""Presenting the version history, and saying what a restore re-checked.

What used to be here as well was ``resolve_version_id`` — a model call that
mapped *"the original plan"* onto a ``version_id``. It is gone, and not because
it was wrong: the supervisor has already read the conversation that phrase came
from, so the judgment it made is one the supervisor is making anyway
(``docs/supervisor-architecture.md`` §1). ``list_versions`` shows the index and
``restore_version`` takes an id from it.

What survives is the part that is not a judgment. The rendering is deterministic
because a model paraphrasing the list could drop or reorder an entry the user is
trying to choose between.
"""

from app.schemas.graph import VersionRef


def render_versions(index: list[VersionRef]) -> str:
    """Render the version index for the prompt and for the user.

    Args:
        index: Version refs, newest first.

    Returns:
        One line per version, the newest marked as current.
    """
    if not index:
        return "No saved versions."

    lines = []
    for position, ref in enumerate(index):
        marker = "  (current)" if position == 0 else ""
        lines.append(f"- {ref['version_id']} · {ref['label']} · saved {ref['created_at']}{marker}")
    return "\n".join(lines)


def describe_verification_reason(stored_hash: str, current_hash: str) -> str:
    """Explain whether an old assessment still applies to the user.

    The profile hash is not used to *skip* re-verification. The verifiers run
    either way — they are pure functions over data already in memory, so skipping
    them saves nothing measurable — and the hash is used for the part that does
    matter: telling the user whether the checks that passed when they approved
    this plan still describe them.

    Args:
        stored_hash: Profile fingerprint from when the version was saved.
        current_hash: Fingerprint of the profile now.

    Returns:
        A short phrase for the answer.
    """
    if stored_hash and stored_hash == current_hash:
        return "Your details are unchanged since this version was saved, so the same checks apply."
    return (
        "Your details have changed since this version was saved, so it was checked again "
        "against your current profile."
    )


__all__ = ["describe_verification_reason", "render_versions"]
