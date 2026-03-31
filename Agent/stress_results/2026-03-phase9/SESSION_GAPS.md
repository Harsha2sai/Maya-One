
## Phase 11 Scope (carry-forward from Phase 10 closure)

### P11-01: ProviderSupervisor wiring — CRITICAL
- File: core/runtime/lifecycle.py:70
- Current: self.provider_supervisor = None
- Fix: instantiate ProviderSupervisor and wire into LLM/TTS/STT call paths
- Priority: HIGHEST — circuit breakers inactive in production

### P11-02: Memory recall reliability hardening
- Status: CLOSED (2026-03-31)
- Completed:
  - Session-scoped retrieval filter pushed into DB query
  - Context memory injection sanitization + deduplication
  - Profile-fact write metadata + duplicate-write guard
  - Name-recall fallback path (`Your name is Harsha` validated in live smoke)
  - Cleanup script removed poisoned/duplicate rows from Chroma

### P11-03: Calendar test coverage restoration
- Commit dbdd2dd removed 70 lines of calendar test logic
- Restore in-memory SQLite fixture pattern
- Target: restore test_calendar_tools.py to Phase 9D coverage level

### P11-04: GAP-S06 watchdog reclaim live validation
- Implementation committed in b1b261c
- Never validated with a real stuck-task scenario
- Add integration test: insert stuck task, run watchdog, confirm FAILED transition

### Status Update (2026-03-31)
- P11-01 resolved: ProviderSupervisor wiring verified live in runtime logs (`provider_supervisor_configured`) during console agent validation.
- P11-02 resolved: memory pipeline validated end-to-end in tests and live smoke.
- Next active priority: P11-03 (calendar test coverage restoration from `dbdd2dd`).
