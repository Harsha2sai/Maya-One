# Architecture Simplification Plan: Project Maya

## Objectives
- **Maintainability**: Modularize the monolithic `agent.py` and Flutter providers.
- **Scalability**: Implement a Registry Pattern for easy provider additions.
- **Clarity**: Separate concerns between API services, Agent logic, and UI state.

---

## 🏗️ Backend Refactoring (Python)

### 1. Module Extraction
- **`Agent/api/handlers.py`**:
    - Move `handle_token`, `handle_health`, `handle_api_keys`, `handle_get_api_status` here.
    - Centralize the `env_var_mapping` dictionary.
- **`Agent/api/server.py`**:
    - Move `run_token_server` and `cors_middleware` here.
- **`Agent/utils/validation.py`**:
    - Move `validate_mcp_tool_schemas` here.
- **`Agent/providers/factory.py`**:
    - Implement a `ProviderFactory` using the **Registry Pattern**.
    - This will replace the 100+ line `match/if` blocks in the main entrypoint.

### 2. Core Agent Cleanup (`agent.py`)
- Remove all HTTP/Web server code.
- Focus strictly on the `Assistant` class and the LiveKit `entrypoint` function.
- Simplify provider initialization by calling `factory.get_stt(...)`, `factory.get_tts(...)`, etc.

---

## 📱 Frontend Refactoring (Flutter)

### 1. Configuration Separation
- **`lib/core/config/`**:
    - Split `provider_config.dart` into:
        - `llm_config.dart`: LLM providers and models.
        - `stt_config.dart`: STT providers and languages.
        - `tts_config.dart`: TTS providers and voices.
    - Use smaller, type-safe classes instead of giant nested Maps.

### 2. Service Extraction
- **`lib/services/backend_sync_service.dart`**:
    - Extract `syncApiKeysToBackend` and API status checking logic from `SettingsProvider`.
    - This separates "how we sync" from "what we store".

### 3. Provider Simplification
- **`SettingsProvider` & `SessionProvider`**:
    - Clean up bloated methods by delegating tasks to the new services.
    - Reduce boilerplate in JSON parsing and state updates.

---

## 🛡️ Verification & Safety
1. **Incremental Changes**: Refactor one module at a time.
2. **Functionality Check**: Verify:
    - Token generation still works.
    - API keys still sync to `.env`.
    - Voice assistant correctly initializes with EdgeTTS/Groq.
    - Memory/Context persists on shutdown.

---

## 🔍 Perplexity Expert Review Notes
- **Registry Pattern**: Confirmed as the standard for dynamically selecting providers in LLM apps.
- **Separation of Concerns**: Verified that running the API server in a separate process/module prevents blocking the agent's event loop.
- **Type Safety**: Encouraged for both Python (Pydantic/Dataclasses) and Dart to reduce runtime errors.
