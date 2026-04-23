# Phase 39.4.1 — Boundary Recovery (Execution Plan)

## Objective
Recover scheduling follow-up reliability without redesigning router/planner, by fixing entry handling, clarification carryover, and no-state loop behavior.

## Implemented Actions
1. Deterministic scheduling entry guard
- Ensured scheduling marker queries route to scheduling deterministically before fallback routing.

2. Time-only reminder clarification
- `set a reminder for tomorrow` now returns clarification (`What should I remind you about?`) with captured time.

3. Pending clarification carryover (2-turn budget)
- Added ephemeral pending scheduling state:
  - `pending_scheduling_action = { type: set_reminder, time, written_turn }`
- Resume path combines next task-like utterance with pending time.
- Clear-on-success/expiry/cancel behavior included.

4. No-state reminder follow-up fallback
- Reminder follow-up with no `last_action` returns deterministic help text and avoids parser rejection loop.

5. Matcher hardening to avoid cross-state hijack
- Pending reminder continuation no longer intercepts pronoun/profile follow-up language (`tell me more about him`, `what is my name`, etc.).

6. Telemetry
- Added/validated counters:
  - `scheduling_clarification_requested`
  - `scheduling_missing_task_followup_total`
  - `pending_scheduling_resume_total`
  - `pending_scheduling_expired_total`
- Kept `last_action_followup_hit` compatibility.

## Certification Matrix
- P1 Immediate consistency: pass
- P4 Failure path (fresh): pass
- P5b Entity pronoun continuity: pass
- P7 Clarification continuation + reminder follow-up: pass
- P10 Tool-output continuity (`tool_outputs_preserved=1`): pass

## Release
- Commit: `f8fa844c`
- Tag: `v0.54.6`
