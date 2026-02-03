## 📜 The Refactor Contract
> **"This is a structural refactor only: extract, don’t rethink; preserve behavior exactly."**
For every extracted function or class, the observable inputs, outputs, side effects, and exceptions **must remain identical** to the original implementation.

---

## 🛡️ Risk Mitigation & Parity
1. **Dumb Factory**: The `ProviderFactory` will be purely mechanical. It will not have "smart defaults" or "hidden fallback logic." If the config is missing, it should fail exactly as the original code did.
2. **Snapshot Validation**: Before moving code, we will record the exact provider initialization sequence (LLM/STT/TTS) to ensure no drift.
3. **Atomic Changes**: Refactor one module, verify connectivity, and only then move to the next.

---

## 🏗️ Phase 1: Backend Extraction (Simplifying `agent.py`)

### 1.1 Extract API Server & Handlers
- **File**: Create `Agent/api/handlers.py` and `Agent/api/server.py`.
- **Target Logic**:
    - `handle_token`, `handle_api_keys`, `run_token_server`.
- **Simplification**: Use a clean router setup and separate the CORS middleware from the server runner.

### 1.2 Implement Provider Factory (Registry Pattern)
- **File**: Create `Agent/providers/factory.py`.
- **Target Logic**: The giant `if/else` and `try/except` blocks in `entrypoint` that initialize LLM, STT, and TTS.
- **Simplification**:
    - Build a `ProviderRegistry` class.
    - Reduce 150 lines of initialization code to simple `factory.get_llm(name, options)` calls.

### 1.3 Logic Cleanup in `agent.py`
- Refactor the `Assistant` class to remove inline utility methods.
- Simplify `entrypoint` to purely handle Room events and Session setup.

---

## 📱 Phase 2: Frontend Refinement (Simplifying Flutter)

### 2.1 Modularize `ProviderConfig`
- **File**: Split `lib/core/config/provider_config.dart` into `llm_models.dart`, `stt_languages.dart`, and `tts_voices.dart`.
- **Simplification**: Use `final class` definitions instead of nested `Map<String, dynamic>`. This enables compile-time error checking.

### 2.2 Extract `BackendSyncService`
- **File**: Create `lib/services/sync_service.dart`.
- **Target Logic**: Move the `_post` requests to `/api-keys` and `/token` out of the Providers.
- **Simplification**: Centralize error handling and base URL management.

---

## ✅ Phase 3: Verification & Polish
- **Step 1**: Run `python agent.py console` and verify STT/TTS loop.
- **Step 2**: Verify Flutter app can still fetch tokens from port 5050.
- **Step 3**: Verify `.env` sync still works when changing keys in the UI.

---

## 🛠️ Code-Simplifier's Quality Checklist
1. **No Logic Changes**: Every `if` condition and `try/except` logic must remain identical in behavior.
2. **Explicit over Clever**: Avoid complex one-liners; prefer clear, readable functions.
3. **Consistency**: Use the established `logger` patterns across all new files.
4. **De-nesting**: Flatten nested `if` statements into guard clauses where possible.
