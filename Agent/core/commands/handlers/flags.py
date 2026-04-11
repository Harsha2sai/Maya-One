from __future__ import annotations

from core.features.flags import FeatureFlag, FeatureLocked


async def handle_flag(args: str, context: dict) -> str:
    """
    /flag enable <FLAG>
    /flag disable <FLAG>
    /flag list
    /flag reset
    """
    feature_flags = context.get("feature_flags")
    if feature_flags is None:
        return "Feature flag system not available."

    parts = str(args or "").strip().split()
    if not parts:
        return "Usage: /flag [enable|disable|list|reset] [FLAG_NAME]"

    sub = parts[0].lower()
    if sub == "list":
        lines = ["Feature Flags:"]
        for flag, enabled in feature_flags.all_flags().items():
            icon = "ON" if enabled else "OFF"
            lock = " (locked)" if flag.value == "AGENT_PETS" else ""
            lines.append(f"  {icon} {flag.value}{lock}")
        return "\n".join(lines)

    if sub == "reset":
        feature_flags.reset_to_defaults()
        return "Feature flags reset to defaults."

    if sub in ("enable", "disable") and len(parts) >= 2:
        flag_name = parts[1].upper()
        try:
            flag = FeatureFlag(flag_name)
        except ValueError:
            valid = ", ".join([f.value for f in FeatureFlag])
            return f"Unknown flag '{flag_name}'. Valid: {valid}"

        try:
            if sub == "enable":
                feature_flags.enable(flag)
                return f"{flag.value} enabled."
            feature_flags.disable(flag)
            return f"{flag.value} disabled."
        except FeatureLocked as exc:
            return str(exc)

    return "Usage: /flag [enable|disable|list|reset] [FLAG_NAME]"

