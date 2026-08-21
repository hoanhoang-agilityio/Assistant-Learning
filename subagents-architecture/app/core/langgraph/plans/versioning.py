"""Presenting the version history, and saying what a restore re-checked."""

from app.schemas.graph import VersionRef


def render_versions(index: list[VersionRef]) -> str:
    """Render the version index for the prompt and for the user."""
    if not index:
        return "No saved versions."
    lines: list[str] = []
    for position, reference in enumerate(index):
        marker = "  (current)" if position == 0 else ""
        lines.append(
            f"- {reference['version_id']} · {reference['label']} · "
            f"saved {reference['created_at']}{marker}"
        )
    return "\n".join(lines)


def describe_verification_reason(stored_hash: str, current_hash: str) -> str:
    """Explain whether an old assessment still applies to the user."""
    if stored_hash and stored_hash == current_hash:
        return "Your details are unchanged since this version was saved, so the same checks apply."
    return (
        "Your details have changed since this version was saved, so it was checked again "
        "against your current profile."
    )


__all__ = ["describe_verification_reason", "render_versions"]
