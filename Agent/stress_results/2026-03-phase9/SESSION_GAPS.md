
## Phase 11 Scope (carry-forward from Phase 10 closure)

### P11-01: ProviderSupervisor wiring — CRITICAL
- File: core/runtime/lifecycle.py:70
- Current: self.provider_supervisor = None
- Fix: instantiate ProviderSupervisor and wire into LLM/TTS/STT call paths
- Priority: HIGHEST — circuit breakers inactive in production

### P11-02: Chroma PersistentClient failure
- Symptom: InternalError code 14, unable to open database file
- Survives path fix and clean reinit — system library mismatch
- Decision required: fix library or formally adopt keyword-only memory

### P11-03: Calendar test coverage restoration
- Commit dbdd2dd removed 70 lines of calendar test logic
- Restore in-memory SQLite fixture pattern
- Target: restore test_calendar_tools.py to Phase 9D coverage level

### P11-04: GAP-S06 watchdog reclaim live validation
- Implementation committed in b1b261c
- Never validated with a real stuck-task scenario
- Add integration test: insert stuck task, run watchdog, confirm FAILED transition
