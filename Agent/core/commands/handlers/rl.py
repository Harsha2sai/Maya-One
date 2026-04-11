from __future__ import annotations

from pathlib import Path


async def handle_rl(args: str, context: dict) -> str:
    """
    /rl stats [--days N]
    /rl eval
    /rl export [--days N]
    /rl rate <task_id> <1-5>
    """
    outcome_logger = context.get("outcome_logger")
    evaluator = context.get("evaluator")
    exporter = context.get("training_exporter")

    tokens = str(args or "").strip().split()
    if not tokens:
        return (
            "Usage:\n"
            "  /rl stats [--days N]\n"
            "  /rl eval\n"
            "  /rl export [--days N]\n"
            "  /rl rate <task_id> <1-5>"
        )

    sub = tokens[0].lower()
    if sub == "stats":
        if outcome_logger is None:
            return "Outcome logger not available."
        days = _parse_days(tokens)
        stats = outcome_logger.stats(days=days)
        lines = [
            f"Outcome stats (last {stats['days']} days):",
            f"  Total logged : {stats['total']}",
            f"  Success rate : {stats['success_rate']:.1%}",
            f"  Rated        : {stats['rated']}",
        ]
        if stats["avg_rating"] is not None:
            lines.append(f"  Avg rating   : {stats['avg_rating']}/5")
        if stats["by_route"]:
            lines.append("  By route:")
            for route, count in sorted(stats["by_route"].items(), key=lambda item: -item[1]):
                lines.append(f"    {route:<16} {count}")
        return "\n".join(lines)

    if sub == "eval":
        if evaluator is None:
            return "Evaluator not available."
        result = await evaluator.run()
        lines = [
            (
                f"Benchmark complete: {result.passed}/{result.total} passed "
                f"(score={result.score:.1%})"
            )
        ]
        if result.failed_items:
            lines.append("Failed:")
            for failed in result.failed_items:
                lines.append(f"  - {failed}")
        if result.score >= 0.75:
            lines.append("Above 0.75 threshold - ready for export.")
        else:
            lines.append("Below 0.75 threshold - review failed items.")
        return "\n".join(lines)

    if sub == "export":
        if exporter is None:
            return "Training exporter not available."
        days = _parse_days(tokens)
        output = Path.home() / ".maya" / "training" / "training_set.jsonl"
        count = exporter.export(output_path=output, days=days, success_only=True)
        return (
            f"Exported {count} training examples to:\n"
            f"  {output}\n"
            "Format: Trinity-RFT JSONL (prompt / response / reward)"
        )

    if sub == "rate":
        if outcome_logger is None:
            return "Outcome logger not available."
        if len(tokens) < 3:
            return "Usage: /rl rate <task_id> <1-5>"
        task_id = tokens[1]
        try:
            rating = int(tokens[2])
        except ValueError:
            return "Rating must be an integer 1-5."
        updated = await outcome_logger.rate(task_id=task_id, rating=rating)
        if updated:
            return f"Rating {rating}/5 saved for task {task_id}."
        return f"Task {task_id} not found in today's outcomes."

    return f"Unknown subcommand '{sub}'. Run /rl for usage."


def _parse_days(tokens: list[str]) -> int:
    try:
        idx = tokens.index("--days")
        return int(tokens[idx + 1])
    except (ValueError, IndexError):
        return 7

