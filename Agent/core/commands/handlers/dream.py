from __future__ import annotations

from core.features.flags import FeatureFlag


async def handle_dream(args: str, context: dict) -> str:
    """
    /dream
    /dream --preview
    """
    feature_flags = context.get("feature_flags")
    dream_cycle = context.get("dream_cycle")
    session_id = context.get("session_id", "unknown")
    user_id = context.get("user_id", "default")

    if feature_flags and not feature_flags.is_enabled(FeatureFlag.DREAM_CYCLE):
        return (
            "$dream is currently disabled.\n"
            "Enable it with: /flag enable DREAM_CYCLE"
        )

    if dream_cycle is None:
        return "Dream cycle not available in this runtime."

    preview_mode = "--preview" in str(args or "").split()
    if preview_mode:
        recent = await dream_cycle._fetch_recent(session_id, user_id)
        if len(recent) < dream_cycle.MIN_ENTRIES:
            return (
                f"Not enough to consolidate yet "
                f"({len(recent)}/{dream_cycle.MIN_ENTRIES} entries minimum)."
            )
        return (
            f"Dream preview: {len(recent)} entries would be consolidated.\n"
            "Run /dream without --preview to commit."
        )

    result = await dream_cycle.run(session_id=session_id, user_id=user_id)
    if result.skipped:
        return f"Nothing to consolidate yet. ({result.skip_reason})"

    return (
        "Dream complete.\n"
        f"Consolidated {result.compressed_count} memories into long-term storage.\n"
        f"Preview: {result.summary_preview}"
    )

