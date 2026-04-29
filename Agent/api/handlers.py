import os
import json
import logging
import asyncio
import re
import time
from aiohttp import web, WSMsgType, client_exceptions
from livekit.api import (
    AccessToken,
    VideoGrants,
    LiveKitAPI,
    CreateRoomRequest,
    CreateAgentDispatchRequest,
)
from livekit.protocol import models, room
from core.runtime.readiness import ReadinessState, get_runtime_readiness_tracker

logger = logging.getLogger(__name__)

_room_context_generation = 0
_latest_token_room_context: dict[str, object] = {}
_last_room_by_run_id: dict[str, dict[str, object]] = {}


def _next_room_context_generation() -> int:
    global _room_context_generation
    _room_context_generation += 1
    return _room_context_generation


def _current_room_context_generation() -> int:
    return int(_room_context_generation)


def _set_room_context(context: dict[str, object]) -> dict[str, object]:
    global _latest_token_room_context
    _latest_token_room_context = dict(context)
    return dict(_latest_token_room_context)


def _room_context_snapshot() -> dict[str, object]:
    return dict(_latest_token_room_context)


def reset_room_context_state(*, reason: str) -> dict[str, object]:
    global _last_room_by_run_id
    generation = _next_room_context_generation()
    _last_room_by_run_id = {}
    return _set_room_context(
        {
            "generation": generation,
            "context_state": "empty",
            "reason": reason,
            "room_name": "",
            "participant_name": "",
            "issued_at_ms": None,
            "token_status": None,
            "pid": os.getpid(),
        }
    )


def _publish_token_room_context(
    *,
    room_name: str,
    participant_name: str,
    token_status: int,
    context_state: str,
    reason: str = "",
) -> dict[str, object]:
    generation = _current_room_context_generation() or _next_room_context_generation()
    return _set_room_context(
        {
            "generation": generation,
            "context_state": context_state,
            "reason": reason,
            "room_name": str(room_name),
            "participant_name": str(participant_name),
            "issued_at_ms": int(time.time() * 1000),
            "token_status": int(token_status),
            "pid": os.getpid(),
        }
    )


def _room_context_error_payload(context: dict[str, object]) -> tuple[int, dict[str, object]]:
    current_generation = _current_room_context_generation()
    context_generation = int(context.get("generation") or 0)
    context_state = str(context.get("context_state") or "")
    room_name = str(context.get("room_name") or "")

    if not context:
        error = "room_context_missing"
    elif context_generation != current_generation:
        error = "room_context_stale_generation"
    elif context_state == "token_failed":
        error = "room_context_token_failed"
    else:
        error = "room_context_send_before_token"

    return 409, {
        "error": error,
        "room": room_name,
        "retry_after_ms": 500,
        "details": {
            "context_state": context_state or "missing",
            "reason": str(context.get("reason") or error),
            "generation": context_generation,
            "current_generation": current_generation,
            "room_name": room_name,
            "participant_name": str(context.get("participant_name") or ""),
            "issued_at_ms": context.get("issued_at_ms"),
            "token_status": context.get("token_status"),
            "pid": context.get("pid"),
        },
    }

# Map provider IDs to environment variable names
# Centralized to avoid duplication and inconsistencies
ENV_VAR_MAPPING = {
    'groq': 'GROQ_API_KEY',
    'groq_secondary': 'GROQ_API_KEY_2',
    'groq_tertiary': 'GROQ_API_KEY_3',
    'openai': 'OPENAI_API_KEY',
    'gemini': 'GEMINI_API_KEY',
    'gemini_secondary': 'GEMINI_API_KEY_2',
    'anthropic': 'ANTHROPIC_API_KEY',
    'deepseek': 'DEEPSEEK_API_KEY',
    'mistral': 'MISTRAL_API_KEY',
    'perplexity': 'PERPLEXITY_API_KEY',
    'together': 'TOGETHER_API_KEY',
    'deepgram': 'DEEPGRAM_API_KEY',
    'assemblyai': 'ASSEMBLYAI_API_KEY',
    'cartesia': 'CARTESIA_API_KEY',
    'elevenlabs': 'ELEVENLABS_API_KEY',
    'mem0': 'MEM0_API_KEY',
    'aws_access_key': 'AWS_ACCESS_KEY_ID',
    'aws_secret_key': 'AWS_SECRET_ACCESS_KEY',
    'azure_speech_key': 'AZURE_SPEECH_KEY',
    'azure_speech_region': 'AZURE_SPEECH_REGION',
    'azure_speech_endpoint': 'AZURE_SPEECH_ENDPOINT',
    # LiveKit credentials
    'livekit_active_slot': 'LIVEKIT_ACTIVE_SLOT',
    'livekit_url': 'LIVEKIT_URL',
    'livekit_api_key': 'LIVEKIT_API_KEY',
    'livekit_api_secret': 'LIVEKIT_API_SECRET',
    'livekit_url_2': 'LIVEKIT_URL_2',
    'livekit_api_key_2': 'LIVEKIT_API_KEY_2',
    'livekit_api_secret_2': 'LIVEKIT_API_SECRET_2',
    'livekit_agent_name': 'LIVEKIT_AGENT_NAME',
    # MCP Server
    'n8n_mcp_url': 'N8N_MCP_SERVER_URL',
    # Supabase
    'supabase_url': 'SUPABASE_URL',
    'supabase_anon_key': 'SUPABASE_ANON_KEY',
    'supabase_service_key': 'SUPABASE_SERVICE_KEY',
    # Configuration Settings
    'llmProvider': 'LLM_PROVIDER',
    'llmModel': 'LLM_MODEL',
    'sttProvider': 'STT_PROVIDER',
    'sttModel': 'STT_MODEL',
    'sttLanguage': 'STT_LANGUAGE',
    'ttsProvider': 'TTS_PROVIDER',
    'ttsModel': 'TTS_MODEL',
    'ttsVoice': 'TTS_VOICE', 
    # Connector toggles (phase: status + save)
    'connector_spotify_enabled': 'CONNECTOR_SPOTIFY_ENABLED',
    'connector_youtube_enabled': 'CONNECTOR_YOUTUBE_ENABLED',
    'connector_google_workspace_enabled': 'CONNECTOR_GOOGLE_WORKSPACE_ENABLED',
    'connector_slack_enabled': 'CONNECTOR_SLACK_ENABLED',
    'connector_home_assistant_enabled': 'CONNECTOR_HOME_ASSISTANT_ENABLED',
    'connector_github_enabled': 'CONNECTOR_GITHUB_ENABLED',
}

CONNECTOR_STATUS_KEYS = {
    'spotify': 'connector_spotify_enabled',
    'youtube': 'connector_youtube_enabled',
    'google_workspace': 'connector_google_workspace_enabled',
    'slack': 'connector_slack_enabled',
    'home_assistant': 'connector_home_assistant_enabled',
    'github': 'connector_github_enabled',
}

CONNECTOR_AVAILABILITY = {
    'spotify': {'available': True, 'reason': ''},
    'youtube': {'available': True, 'reason': ''},
    'google_workspace': {'available': False, 'reason': 'OAuth lifecycle not implemented yet.'},
    'slack': {'available': False, 'reason': 'OAuth lifecycle not implemented yet.'},
    'home_assistant': {'available': False, 'reason': 'Backend connector adapter not implemented yet.'},
    'github': {'available': False, 'reason': 'OAuth lifecycle not implemented yet.'},
}

MULTI_SLOT_LLM_PROVIDER_IDS = {
    'groq',
    'gemini',
    'openai',
    'anthropic',
    'deepseek',
    'mistral',
    'perplexity',
    'together',
    'nvidia',
}


def _livekit_slot_suffix(active_slot: str) -> str:
    """Slot 1/auto -> '', slot N -> _N"""
    slot = str(active_slot or "1").strip()
    if not slot.isdigit():
        return ""
    return "" if slot == "1" else f"_{slot}"


def _resolve_livekit_credentials() -> tuple[str, str, str]:
    active_slot = os.getenv("LIVEKIT_ACTIVE_SLOT", "1").strip()
    suffix = _livekit_slot_suffix(active_slot)
    livekit_url = os.getenv(f"LIVEKIT_URL{suffix}", "").strip()
    livekit_api_key = os.getenv(f"LIVEKIT_API_KEY{suffix}", "").strip()
    livekit_api_secret = os.getenv(f"LIVEKIT_API_SECRET{suffix}", "").strip()
    if not (livekit_url and livekit_api_key and livekit_api_secret):
        raise RuntimeError("LiveKit credentials are missing; cannot complete request")
    return livekit_url, livekit_api_key, livekit_api_secret


def _float_env(name: str, default: float, *, minimum: float) -> float:
    raw = str(os.getenv(name, str(default)) or str(default)).strip()
    try:
        return max(minimum, float(raw))
    except Exception:
        return default


def _send_message_poll_interval_s() -> float:
    raw = os.getenv("MAYA_SEND_MESSAGE_ROOM_POLL_INTERVAL_S")
    if raw is None:
        raw = os.getenv("MAYA_SEND_MESSAGE_POLL_INTERVAL_S", "0.2")
    try:
        return max(0.05, float(str(raw).strip()))
    except Exception:
        return 0.2


def _send_message_cold_room_wait_s() -> float:
    return _float_env("MAYA_SEND_MESSAGE_COLD_ROOM_WAIT_S", 35.0, minimum=1.0)


def _send_message_warm_room_wait_s() -> float:
    return _float_env("MAYA_SEND_MESSAGE_WARM_ROOM_WAIT_S", 25.0, minimum=1.0)


def _send_message_first_turn_grace_s() -> float:
    return _float_env("MAYA_SEND_MESSAGE_FIRST_TURN_GRACE_S", 2.0, minimum=0.0)


def _send_message_first_turn_grace_interval_s() -> float:
    return _float_env("MAYA_SEND_MESSAGE_FIRST_TURN_GRACE_POLL_INTERVAL_S", 0.25, minimum=0.05)


def _first_turn_ready_states() -> set[str]:
    return {
        ReadinessState.READY_SESSION_CAPABLE.value,
        ReadinessState.READY_CAPABILITY.value,
    }


def _first_turn_route_gate_status(readiness_snapshot: dict[str, object]) -> dict[str, object]:
    checks = readiness_snapshot.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    state = str(readiness_snapshot.get("state") or "")
    worker_registered = bool(
        checks.get("worker_registered")
        or readiness_snapshot.get("worker_connected")
        or readiness_snapshot.get("worker_registered")
    )
    dispatch_pipeline_ready = bool(
        checks.get("dispatch_pipeline_ready")
        or readiness_snapshot.get("dispatch_pipeline_ready")
    )
    dispatch_claimable_ready = bool(
        checks.get("dispatch_claimable_ready")
        or readiness_snapshot.get("dispatch_claimable_ready")
        or readiness_snapshot.get("last_probe_ok")
    )
    state_ready = state in _first_turn_ready_states()
    return {
        "allowed": bool(
            worker_registered
            and dispatch_pipeline_ready
            and dispatch_claimable_ready
            and state_ready
        ),
        "state": state,
        "worker_registered": worker_registered,
        "dispatch_pipeline_ready": dispatch_pipeline_ready,
        "dispatch_claimable_ready": dispatch_claimable_ready,
        "state_ready": state_ready,
    }


async def _wait_for_first_turn_route_ready(
    tracker: object,
    *,
    timeout_s: float = 1.0,
    interval_s: float = 0.05,
) -> tuple[bool, dict[str, object]]:
    deadline = time.monotonic() + max(0.0, timeout_s)
    last_snapshot = tracker.snapshot()
    while True:
        gate = _first_turn_route_gate_status(last_snapshot)
        if gate["allowed"]:
            return True, last_snapshot
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False, last_snapshot
        await asyncio.sleep(min(max(0.01, interval_s), remaining))
        last_snapshot = tracker.snapshot()


def _warming_up_payload(readiness_snapshot: dict[str, object], *, room_name: str = "") -> dict[str, object]:
    return {
        "error": "warming_up",
        "retry_after_ms": 1000,
        "room": room_name,
        "details": {
            "state": readiness_snapshot.get("state"),
            "checks": readiness_snapshot.get("checks"),
            "timing": readiness_snapshot.get("timing"),
            "probe": readiness_snapshot.get("probe"),
            "worker_alive": readiness_snapshot.get("worker_alive"),
            "last_probe_ok": readiness_snapshot.get("last_probe_ok"),
            "last_probe_age_ms": readiness_snapshot.get("last_probe_age_ms"),
            "session": readiness_snapshot.get("session"),
            "cycle_id": readiness_snapshot.get("cycle_id"),
        },
    }


def _token_dispatch_retry_attempts() -> int:
    raw = str(os.getenv("MAYA_TOKEN_DISPATCH_RETRY_ATTEMPTS", "2") or "2").strip()
    try:
        return max(1, int(raw))
    except Exception:
        return 2


def _token_dispatch_retry_delay_s() -> float:
    return _float_env("MAYA_TOKEN_DISPATCH_RETRY_DELAY_S", 0.25, minimum=0.0)


def _token_credentials_present_for_slot(suffix: str) -> dict[str, bool]:
    return {
        "livekit_url_present": bool(str(os.getenv(f"LIVEKIT_URL{suffix}", "") or "").strip()),
        "api_key_present": bool(str(os.getenv(f"LIVEKIT_API_KEY{suffix}", "") or "").strip()),
        "secret_present": bool(str(os.getenv(f"LIVEKIT_API_SECRET{suffix}", "") or "").strip()),
    }


def _is_transient_token_dispatch_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            asyncio.TimeoutError,
            TimeoutError,
            client_exceptions.ClientConnectorDNSError,
            client_exceptions.ClientConnectorError,
            client_exceptions.ServerDisconnectedError,
        ),
    ):
        return True
    message = str(exc).lower()
    transient_markers = (
        "temporary failure in name resolution",
        "name or service not known",
        "nodename nor servname provided",
        "server disconnected",
        "connection reset by peer",
        "timed out",
    )
    return any(marker in message for marker in transient_markers)


def _static_send_message_wait_budget(tracker: object) -> dict[str, float | int | str]:
    has_successful_room_join = False
    getter = getattr(tracker, "has_successful_room_join", None)
    if callable(getter):
        try:
            has_successful_room_join = bool(getter())
        except Exception:
            has_successful_room_join = False
    wait_budget_s = _send_message_warm_room_wait_s() if has_successful_room_join else _send_message_cold_room_wait_s()
    room_wait_budget_source = "warm_static" if has_successful_room_join else "cold_static"
    return {
        "wait_budget_s": wait_budget_s,
        "room_wait_budget_source": room_wait_budget_source,
        "successful_room_join_count": 1 if has_successful_room_join else 0,
    }


def _should_apply_first_turn_session_grace(status: dict[str, object]) -> bool:
    room_stage = status.get("room_stage")
    if not isinstance(room_stage, dict):
        return False
    return (
        str(status.get("room_failure_class") or "") == "session_booting"
        and bool(status.get("dispatch_ready"))
        and bool(status.get("agent_present"))
        and room_stage.get("worker_job_claimed_at_ms") is not None
        and room_stage.get("room_joined_at_ms") is not None
        and room_stage.get("session_started_at_ms") is not None
        and room_stage.get("session_ready_at_ms") is None
    )


def _annotate_room_gate_status(
    status: dict[str, object],
    *,
    first_request_arrived_at_ms: int,
    first_request_released_at_ms: int | None = None,
    grace_applied: bool = False,
    grace_elapsed_ms: int = 0,
    grace_attempts: int = 0,
    grace_budget_ms: int = 0,
) -> dict[str, object]:
    room_stage = status.get("room_stage")
    if isinstance(room_stage, dict):
        status["worker_job_claimed_at_ms"] = room_stage.get("worker_job_claimed_at_ms")
        status["room_joined_at_ms"] = room_stage.get("room_joined_at_ms")
        status["session_started_at_ms"] = room_stage.get("session_started_at_ms")
        status["session_ready_at_ms"] = room_stage.get("session_ready_at_ms")
    status["first_request_arrived_at_ms"] = first_request_arrived_at_ms
    status["first_request_released_at_ms"] = first_request_released_at_ms
    status["first_turn_grace_applied"] = grace_applied
    status["first_turn_grace_elapsed_ms"] = grace_elapsed_ms
    status["first_turn_grace_attempts"] = grace_attempts
    status["first_turn_grace_budget_ms"] = grace_budget_ms
    return status


def _provider_id_to_env_var(provider_id: str):
    """Translate Flutter settings keys into backend env var names."""
    pid = str(provider_id or "").strip()
    if not pid:
        return None

    if pid in ENV_VAR_MAPPING:
        return ENV_VAR_MAPPING[pid]

    if pid.endswith('_active_key_slot'):
        provider_prefix = pid[:-len('_active_key_slot')].upper()
        return f"{provider_prefix}_ACTIVE_KEY_SLOT"

    if pid.endswith('_active_slot'):
        provider_prefix = pid[:-len('_active_slot')].upper()
        # LiveKit historically uses LIVEKIT_ACTIVE_SLOT (without _KEY_)
        if provider_prefix == 'LIVEKIT':
            return 'LIVEKIT_ACTIVE_SLOT'
        return f"{provider_prefix}_ACTIVE_KEY_SLOT"

    if pid.endswith('_slot_count'):
        provider_prefix = pid[:-len('_slot_count')].upper()
        return f"{provider_prefix}_SLOT_COUNT"

    if pid.startswith('livekit_') or '_api_key_' in pid:
        return pid.upper()

    # Dynamic multi-key UI sends "groq_2", "gemini_3", "openai_2", etc.
    slot_match = re.fullmatch(r'([a-z0-9]+)_(\d+)', pid)
    if slot_match:
        base_provider, slot_num = slot_match.groups()
        if base_provider in MULTI_SLOT_LLM_PROVIDER_IDS:
            return f"{base_provider.upper()}_API_KEY_{slot_num}"

    return None


def _env_var_to_provider_id(env_var: str) -> str:
    """Translate env var names back into Flutter-facing provider keys."""
    reverse_mapping = {v: k for k, v in ENV_VAR_MAPPING.items()}
    if env_var in reverse_mapping:
        return reverse_mapping[env_var]

    if env_var == 'LIVEKIT_ACTIVE_SLOT':
        return 'livekit_active_slot'

    m = re.fullmatch(r'([A-Z0-9]+)_ACTIVE_KEY_SLOT', env_var)
    if m:
        return f"{m.group(1).lower()}_active_slot"

    m = re.fullmatch(r'([A-Z0-9]+)_SLOT_COUNT', env_var)
    if m:
        return f"{m.group(1).lower()}_slot_count"

    m = re.fullmatch(r'([A-Z0-9]+)_API_KEY_(\d+)', env_var)
    if m:
        return f"{m.group(1).lower()}_{m.group(2)}"

    return env_var.lower()


def _parse_env_bool(raw_value: str) -> bool:
    normalized = str(raw_value or '').strip().lower()
    return normalized in {'1', 'true', 'yes', 'on', 'enabled'}


def _get_ide_runtime_components():
    """Resolve IDE runtime singletons from the global container."""
    from core.runtime.global_agent import GlobalAgentContainer

    session_manager = GlobalAgentContainer.get_ide_session_manager()
    file_service = GlobalAgentContainer.get_ide_file_service()
    action_guard = GlobalAgentContainer.get_ide_action_guard()
    state_bus = GlobalAgentContainer.get_ide_state_bus()
    if not all([session_manager, file_service, action_guard, state_bus]):
        raise RuntimeError("IDE runtime not initialized")
    return session_manager, file_service, action_guard, state_bus


def _get_terminal_manager_component(request):
    """Resolve terminal manager from app attachment or global container."""
    agent = getattr(request.app, "_agent", None)
    if agent is not None:
        manager = getattr(agent, "_terminal_manager", None)
        if manager is not None:
            return manager

    from core.runtime.global_agent import GlobalAgentContainer

    manager = GlobalAgentContainer.get_terminal_manager()
    if manager is None:
        raise RuntimeError("Terminal manager not initialized")
    return manager


def _parse_positive_int(raw_value, *, default: int) -> int:
    try:
        parsed = int(str(raw_value or "").strip())
        if parsed < 0:
            return default
        return parsed
    except Exception:
        return default


def _guard_error_response(decision):
    status = 409 if getattr(decision, "requires_approval", False) else 403
    return web.json_response(
        {
            "error": "action not permitted",
            "decision": {
                "risk": decision.risk,
                "allowed": decision.allowed,
                "requires_approval": decision.requires_approval,
                "policy_reason": decision.policy_reason,
            },
        },
        status=status,
    )


async def handle_ide_session_open(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json payload"}, status=400)

    workspace_path = str((data or {}).get("workspace_path") or "").strip()
    user_id = str((data or {}).get("user_id") or "unknown").strip() or "unknown"
    if not workspace_path:
        return web.json_response({"error": "workspace_path is required"}, status=400)

    try:
        session_manager, _file_service, _action_guard, state_bus = _get_ide_runtime_components()
        session = session_manager.open_session(workspace_path=workspace_path, user_id=user_id)
        await state_bus.emit(
            "session_opened",
            {
                "session_id": session.session_id,
                "workspace_path": session.workspace_path,
                "user_id": session.user_id,
            },
        )
        return web.json_response(
            {
                "session_id": session.session_id,
                "workspace_path": session.workspace_path,
                "user_id": session.user_id,
                "created_at": session.created_at,
                "status": session.status,
            }
        )
    except Exception as e:
        from core.ide import MaxSessionsExceededError

        if isinstance(e, MaxSessionsExceededError):
            return web.json_response({"error": str(e)}, status=429)
        if isinstance(e, ValueError):
            return web.json_response({"error": str(e)}, status=400)
        logger.error("❌ IDE session open failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_session_close(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json payload"}, status=400)

    session_id = str((data or {}).get("session_id") or "").strip()
    if not session_id:
        return web.json_response({"error": "session_id is required"}, status=400)

    try:
        session_manager, _file_service, _action_guard, state_bus = _get_ide_runtime_components()
        closed = session_manager.close_session(session_id)
        if not closed:
            return web.json_response({"error": "session not found"}, status=404)
        await state_bus.emit("session_closed", {"session_id": session_id})
        return web.json_response({"status": "ok", "closed": True, "session_id": session_id})
    except Exception as e:
        logger.error("❌ IDE session close failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_files_tree(request):
    session_id = str(request.query.get("session_id", "")).strip()
    relative_path = str(request.query.get("relative_path", "")).strip()
    if not session_id:
        return web.json_response({"error": "session_id is required"}, status=400)

    from core.ide import ActionEnvelope, SessionNotFoundError

    try:
        session_manager, file_service, action_guard, state_bus = _get_ide_runtime_components()
        if session_manager.get_session(session_id) is None:
            return web.json_response({"error": "session not found"}, status=404)

        action = ActionEnvelope(
            type="ide_action",
            target="file",
            operation="read",
            arguments={"relative_path": relative_path},
            confidence=1.0,
            reason="list tree",
        )
        decision = action_guard.check(action)
        if not decision.allowed or decision.requires_approval:
            await state_bus.emit(
                "action_blocked",
                {
                    "session_id": session_id,
                    "target": action.target,
                    "operation": action.operation,
                    "path": relative_path,
                    "risk": decision.risk,
                    "reason": decision.policy_reason,
                },
            )
            return _guard_error_response(decision)

        tree = file_service.list_tree(session_id=session_id, relative_path=relative_path)
        await state_bus.emit(
            "file_read",
            {"session_id": session_id, "path": relative_path, "kind": "tree"},
        )
        return web.json_response({"session_id": session_id, "path": relative_path, "entries": tree})
    except Exception as e:
        from core.ide import PathEscapeError

        if isinstance(e, SessionNotFoundError):
            return web.json_response({"error": str(e)}, status=404)
        if isinstance(e, (PathEscapeError, FileNotFoundError, NotADirectoryError)):
            return web.json_response({"error": str(e)}, status=400)
        logger.error("❌ IDE files tree failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_file_read(request):
    session_id = str(request.query.get("session_id", "")).strip()
    relative_path = str(request.query.get("relative_path", "")).strip()
    if not session_id:
        return web.json_response({"error": "session_id is required"}, status=400)
    if not relative_path:
        return web.json_response({"error": "relative_path is required"}, status=400)

    from core.ide import ActionEnvelope, SessionNotFoundError

    try:
        session_manager, file_service, action_guard, state_bus = _get_ide_runtime_components()
        if session_manager.get_session(session_id) is None:
            return web.json_response({"error": "session not found"}, status=404)

        action = ActionEnvelope(
            type="ide_action",
            target="file",
            operation="read",
            arguments={"relative_path": relative_path},
            confidence=1.0,
            reason="file read",
        )
        decision = action_guard.check(action)
        if not decision.allowed or decision.requires_approval:
            await state_bus.emit(
                "action_blocked",
                {
                    "session_id": session_id,
                    "target": action.target,
                    "operation": action.operation,
                    "path": relative_path,
                    "risk": decision.risk,
                    "reason": decision.policy_reason,
                },
            )
            return _guard_error_response(decision)

        content = file_service.read_file(session_id=session_id, relative_path=relative_path)
        await state_bus.emit("file_read", {"session_id": session_id, "path": relative_path})
        return web.json_response(
            {"session_id": session_id, "path": relative_path, "content": content}
        )
    except Exception as e:
        from core.ide import PathEscapeError

        if isinstance(e, SessionNotFoundError):
            return web.json_response({"error": str(e)}, status=404)
        if isinstance(e, (PathEscapeError, FileNotFoundError)):
            return web.json_response({"error": str(e)}, status=400)
        logger.error("❌ IDE file read failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_file_write(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json payload"}, status=400)

    session_id = str((data or {}).get("session_id") or "").strip()
    relative_path = str((data or {}).get("relative_path") or "").strip()
    content = str((data or {}).get("content") or "")
    if not session_id:
        return web.json_response({"error": "session_id is required"}, status=400)
    if not relative_path:
        return web.json_response({"error": "relative_path is required"}, status=400)

    from core.ide import ActionEnvelope, SessionNotFoundError

    try:
        session_manager, file_service, action_guard, state_bus = _get_ide_runtime_components()
        if session_manager.get_session(session_id) is None:
            return web.json_response({"error": "session not found"}, status=404)

        action = ActionEnvelope(
            type="ide_action",
            target="file",
            operation="write",
            arguments={"relative_path": relative_path, "content": content[:1024]},
            confidence=1.0,
            reason="file write",
        )
        decision = action_guard.check(action)
        if not decision.allowed or decision.requires_approval:
            await state_bus.emit(
                "action_blocked",
                {
                    "session_id": session_id,
                    "target": action.target,
                    "operation": action.operation,
                    "path": relative_path,
                    "risk": decision.risk,
                    "reason": decision.policy_reason,
                },
            )
            return _guard_error_response(decision)

        file_service.write_file(session_id=session_id, relative_path=relative_path, content=content)
        await state_bus.emit(
            "file_written",
            {"session_id": session_id, "path": relative_path, "bytes": len(content.encode("utf-8"))},
        )
        return web.json_response({"status": "ok", "session_id": session_id, "path": relative_path})
    except Exception as e:
        from core.ide import PathEscapeError

        if isinstance(e, SessionNotFoundError):
            return web.json_response({"error": str(e)}, status=404)
        if isinstance(e, PathEscapeError):
            return web.json_response({"error": str(e)}, status=400)
        if isinstance(e, IsADirectoryError):
            return web.json_response(
                {"error": "Cannot write to a directory path. Provide a file path."},
                status=400,
            )
        if isinstance(e, NotADirectoryError):
            return web.json_response(
                {"error": "A path component is a directory, not a file. Check your path."},
                status=400,
            )
        logger.error("❌ IDE file write failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_events_stream(request):
    """GET /ide/events/stream — Authoritative IDE runtime event stream (WS)."""
    try:
        _session_manager, _file_service, _action_guard, state_bus = _get_ide_runtime_components()
    except Exception as e:
        return web.json_response({"error": str(e)}, status=503)

    session_id_filter = str(request.query.get("session_id", "")).strip() or None
    after_seq = _parse_positive_int(request.query.get("after_seq"), default=0)
    limit = _parse_positive_int(request.query.get("limit"), default=500)
    limit = max(1, min(limit, 5000))

    ws = web.WebSocketResponse(heartbeat=30.0, autoping=True)
    await ws.prepare(request)

    queue = state_bus.subscribe(session_id=session_id_filter)
    replay = state_bus.get_events_since(
        after_seq=after_seq,
        limit=limit,
        session_id=session_id_filter,
    )

    try:
        for event in replay:
            await ws.send_json(event)

        while not ws.closed:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                if ws.closed:
                    break
                await ws.ping()
                continue

            await ws.send_json(event)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("ide_events_stream_error session_id=%s error=%s", session_id_filter or "-", e)
    finally:
        state_bus.unsubscribe(queue=queue)
        if not ws.closed:
            await ws.close()

    return ws


async def _ensure_room_dispatch(room_name: str) -> None:
    """
    Ensure the room has a dispatch targeting LIVEKIT_AGENT_NAME.
    This is required when workers are registered with a non-empty agent_name.
    """
    # Must match worker default so dispatch works even if .env omits the value.
    agent_name = os.getenv("LIVEKIT_AGENT_NAME", "maya-one").strip()
    if not agent_name:
        return

    livekit_url, livekit_api_key, livekit_api_secret = _resolve_livekit_credentials()

    lk = LiveKitAPI(
        url=livekit_url,
        api_key=livekit_api_key,
        api_secret=livekit_api_secret,
    )
    try:
        # Dispatch requires the room to exist first.
        try:
            await lk.room.create_room(CreateRoomRequest(name=room_name))
        except Exception as e:
            # Room already exists is fine; anything else should bubble up.
            if "already exists" not in str(e).lower():
                raise

        listed = await lk.agent_dispatch.list_dispatch(room_name=room_name)
        already_exists = any(d.agent_name == agent_name for d in listed)
        if already_exists:
            return

        readiness = get_runtime_readiness_tracker()
        readiness_snapshot = readiness.snapshot()
        dispatch_metadata = json.dumps(
            {
                "source": "token_server",
                "dispatch_kind": "real_room",
                "cycle_id": str(readiness_snapshot.get("cycle_id") or ""),
                "worker_attempt_id": str(readiness_snapshot.get("active_worker_attempt") or ""),
                "room": room_name,
                "agent_name": agent_name,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        dispatch_worker_snapshot = {
            "workers_online": 1
            if bool(
                (readiness_snapshot.get("checks") or {}).get("worker_registered")
                or readiness_snapshot.get("worker_connected")
                or readiness_snapshot.get("worker_registered")
            )
            else 0,
            "workers_claimable": 1
            if bool(
                (readiness_snapshot.get("checks") or {}).get("dispatch_claimable_ready")
                or readiness_snapshot.get("dispatch_claimable_ready")
                or readiness_snapshot.get("last_probe_ok")
            )
            else 0,
            "worker_state": str(readiness_snapshot.get("state") or ""),
            "configured_agent_name": agent_name,
        }
        readiness.record_boot_event(
            "dispatch_requested",
            room=room_name,
            agent_name=agent_name,
            source="token_handler",
            dispatch_metadata=dispatch_metadata,
            **dispatch_worker_snapshot,
        )
        readiness.record_boot_event(
            "dispatch_request_sent",
            room=room_name,
            agent_name=agent_name,
            source="token_handler",
            dispatch_kind="real_room",
            dispatch_metadata=dispatch_metadata,
            **dispatch_worker_snapshot,
        )
        dispatch = await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata=dispatch_metadata,
            )
        )
        dispatch_state = getattr(dispatch, "state", None)
        dispatch_jobs = list(getattr(dispatch_state, "jobs", []) or []) if dispatch_state else []
        readiness.record_boot_event(
            "dispatch_ack_received",
            room=room_name,
            agent_name=agent_name,
            source="token_handler",
            dispatch_kind="real_room",
            dispatch_id=str(getattr(dispatch, "id", "") or ""),
            dispatch_metadata=str(getattr(dispatch, "metadata", "") or dispatch_metadata),
            dispatch_job_count=len(dispatch_jobs),
            dispatch_worker_ids=[
                str(getattr(getattr(job, "state", None), "worker_id", "") or "")
                for job in dispatch_jobs
            ],
            **dispatch_worker_snapshot,
        )
        logger.info(f"✅ Dispatch created for room={room_name}, agent={agent_name}")
        readiness.mark_dispatch_created(room_name=room_name, agent_name=agent_name)
        readiness.mark_dispatch_pipeline_ready(source="token_handler")
    finally:
        await lk.aclose()


async def _check_room_session_ready(
    lk: LiveKitAPI,
    room_name: str,
) -> tuple[bool, dict[str, object]]:
    """
    Validate room readiness for /send_message.
    Ready means:
    1) dispatch exists for configured agent name, and
    2) at least one agent participant is present in the room.
    """
    agent_name = os.getenv("LIVEKIT_AGENT_NAME", "maya-one").strip()
    dispatch_ready = False
    agent_present = False
    participant_count = 0

    dispatches = await lk.agent_dispatch.list_dispatch(room_name=room_name)
    if not agent_name:
        dispatch_ready = len(dispatches or []) > 0
    else:
        dispatch_ready = any(getattr(item, "agent_name", "") == agent_name for item in dispatches or [])

    participants_resp = await lk.room.list_participants(
        room.ListParticipantsRequest(room=room_name)
    )
    participants = list(getattr(participants_resp, "participants", []) or [])
    participant_count = len(participants)
    participant_identities = [
        str(getattr(participant, "identity", "") or "")
        for participant in participants
    ]
    agent_present = any(
        str(getattr(participant, "identity", "") or "").startswith("agent-")
        or (agent_name and agent_name in str(getattr(participant, "identity", "") or ""))
        for participant in participants
    )
    room_stage = get_runtime_readiness_tracker().room_stage_snapshot(room_name)
    dispatch_snapshot = [
        {
            "id": str(getattr(item, "id", "") or ""),
            "agent_name": str(getattr(item, "agent_name", "") or ""),
            "metadata": str(getattr(item, "metadata", "") or ""),
            "job_count": len(list(getattr(getattr(item, "state", None), "jobs", []) or [])),
            "worker_ids": [
                str(getattr(getattr(job, "state", None), "worker_id", "") or "")
                for job in list(getattr(getattr(item, "state", None), "jobs", []) or [])
            ],
        }
        for item in dispatches or []
    ]
    room_failure_class = ""
    room_failure_reason = ""
    if room_stage.get("session_failed_at_ms"):
        room_failure_class = "session_failed"
        room_failure_reason = str(room_stage.get("session_failure_reason") or "session_failed")
    elif not room_stage.get("worker_job_claimed_at_ms"):
        room_failure_class = "no_worker_claim"
        room_failure_reason = "no_worker_claim"
    elif not room_stage.get("room_connect_success_at_ms"):
        room_failure_class = "worker_connecting"
        room_failure_reason = str(
            room_stage.get("room_connect_failure_reason") or "worker_connecting"
        )
    elif not room_stage.get("room_joined_at_ms") or not agent_present:
        room_failure_class = "room_joining"
        room_failure_reason = "room_joining"
    elif not room_stage.get("session_started_at_ms") or not room_stage.get("session_ready_at_ms"):
        room_failure_class = "session_booting"
        room_failure_reason = "session_booting"

    return (
        dispatch_ready and agent_present and not room_failure_class,
        {
            "dispatch_ready": dispatch_ready,
            "agent_present": agent_present,
            "participant_count": participant_count,
            "agent_name": agent_name or "",
            "participant_identities": participant_identities,
            "dispatch_snapshot": dispatch_snapshot,
            "room_failure_class": room_failure_class,
            "room_failure_reason": room_failure_reason,
            "room_stage": room_stage,
        },
    )


async def _wait_for_room_session_ready(
    lk: LiveKitAPI,
    room_name: str,
    *,
    wait_budget_s: float,
    interval_s: float = 0.2,
) -> tuple[bool, dict[str, object]]:
    started = time.monotonic()
    started_ms = int(time.time() * 1000)
    deadline = started + max(0.05, wait_budget_s)
    grace_budget_s = _send_message_first_turn_grace_s()
    grace_budget_ms = int(max(0.0, grace_budget_s * 1000.0))
    grace_interval_s = _send_message_first_turn_grace_interval_s()
    status: dict[str, object] = {
        "dispatch_ready": False,
        "agent_present": False,
        "participant_count": 0,
        "attempts": 0,
        "elapsed_ms": 0,
        "wait_budget_ms": int(max(0.0, wait_budget_s * 1000.0)),
        "poll_interval_ms": int(max(0.0, interval_s * 1000.0)),
    }
    attempt_index = 0
    grace_applied = False
    grace_started: float | None = None
    grace_attempts = 0
    while True:
        attempt_index += 1
        ready, status = await _check_room_session_ready(lk, room_name)
        status["attempt_index"] = attempt_index
        status["attempts"] = attempt_index
        status["elapsed_ms"] = max(0, int((time.monotonic() - started) * 1000.0))
        status["wait_budget_ms"] = int(max(0.0, wait_budget_s * 1000.0))
        status["poll_interval_ms"] = int(
            max(0.0, (grace_interval_s if grace_applied else interval_s) * 1000.0)
        )
        if grace_applied:
            grace_attempts += 1
        _annotate_room_gate_status(
            status,
            first_request_arrived_at_ms=started_ms,
            first_request_released_at_ms=None,
            grace_applied=grace_applied,
            grace_elapsed_ms=max(0, int((time.monotonic() - grace_started) * 1000.0))
            if grace_started is not None
            else 0,
            grace_attempts=grace_attempts,
            grace_budget_ms=grace_budget_ms,
        )
        if ready:
            _annotate_room_gate_status(
                status,
                first_request_arrived_at_ms=started_ms,
                first_request_released_at_ms=int(time.time() * 1000),
                grace_applied=grace_applied,
                grace_elapsed_ms=max(0, int((time.monotonic() - grace_started) * 1000.0))
                if grace_started is not None
                else 0,
                grace_attempts=grace_attempts,
                grace_budget_ms=grace_budget_ms,
            )
            return True, status
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if (
                not grace_applied
                and grace_budget_s > 0.0
                and _should_apply_first_turn_session_grace(status)
            ):
                grace_applied = True
                grace_started = time.monotonic()
                deadline = grace_started + grace_budget_s
                status["first_turn_grace_started_at_ms"] = int(time.time() * 1000)
                continue
            status["elapsed_ms"] = max(0, int(time.time() * 1000) - started_ms)
            _annotate_room_gate_status(
                status,
                first_request_arrived_at_ms=started_ms,
                first_request_released_at_ms=int(time.time() * 1000),
                grace_applied=grace_applied,
                grace_elapsed_ms=max(0, int((time.monotonic() - grace_started) * 1000.0))
                if grace_started is not None
                else 0,
                grace_attempts=grace_attempts,
                grace_budget_ms=grace_budget_ms,
            )
            return False, status
        active_interval_s = grace_interval_s if grace_applied else interval_s
        await asyncio.sleep(min(max(0.05, active_interval_s), remaining))

async def handle_token(request):
    """Integrated token generation endpoint"""
    room_name = ""
    participant_name = ""
    started = time.monotonic()
    try:
        data = await request.json()
        room_name = str(data.get('roomName') or "").strip()
        participant_name = str(data.get('participantName') or "").strip()
        metadata = data.get('metadata', {})
        
        if not room_name or not participant_name:
            return web.json_response({'error': 'roomName and participantName required'}, status=400)

        active_slot = os.getenv("LIVEKIT_ACTIVE_SLOT", "1").strip()
        suffix = _livekit_slot_suffix(active_slot)
        tracker = get_runtime_readiness_tracker()
        generation = _current_room_context_generation()
        token_env = _token_credentials_present_for_slot(suffix)
        tracker.record_boot_event(
            "token_request_started",
            room=room_name,
            participant=participant_name,
            generation=generation,
            pid=os.getpid(),
            elapsed_ms=0,
            **token_env,
        )

        route_ready, readiness_snapshot = await _wait_for_first_turn_route_ready(tracker)
        if not route_ready:
            tracker.record_boot_event(
                "token_request_rejected_warming_up",
                room=room_name,
                participant=participant_name,
                generation=generation,
                pid=os.getpid(),
                elapsed_ms=max(0, int((time.monotonic() - started) * 1000.0)),
                state=readiness_snapshot.get("state"),
                cycle_id=readiness_snapshot.get("cycle_id"),
                **token_env,
            )
            return web.json_response(
                _warming_up_payload(readiness_snapshot, room_name=room_name),
                status=503,
            )

        dispatch_attempts = _token_dispatch_retry_attempts()
        retry_delay_s = _token_dispatch_retry_delay_s()
        last_error: Exception | None = None
        attempts_used = 0
        for attempt in range(1, dispatch_attempts + 1):
            attempts_used = attempt
            try:
                # Ensure this room is routed to the configured worker name.
                # If this fails, returning token would create a silent no-agent session.
                await _ensure_room_dispatch(room_name)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                transient = _is_transient_token_dispatch_error(exc)
                if transient and attempt < dispatch_attempts:
                    tracker.record_boot_event(
                        "token_request_retry_scheduled",
                        room=room_name,
                        participant=participant_name,
                        generation=generation,
                        pid=os.getpid(),
                        attempt=attempt,
                        retry_delay_ms=int(max(0.0, retry_delay_s * 1000.0)),
                        exception_type=type(exc).__name__,
                        exception_message=str(exc),
                        elapsed_ms=max(0, int((time.monotonic() - started) * 1000.0)),
                        **token_env,
                    )
                    if retry_delay_s > 0:
                        await asyncio.sleep(retry_delay_s)
                    continue
                raise
        if last_error is not None:
            raise last_error

        token = (
            AccessToken(os.getenv(f"LIVEKIT_API_KEY{suffix}"), os.getenv(f"LIVEKIT_API_SECRET{suffix}"))
            .with_identity(participant_name)
            .with_name(participant_name)
            .with_grants(VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            ))
        )
        
        if metadata:
            token = token.with_metadata(json.dumps(metadata))

        context = _publish_token_room_context(
            room_name=room_name,
            participant_name=participant_name,
            token_status=200,
            context_state="token_issued",
        )
        logger.info(
            "send_message_room_context_updated room=%s participant=%s generation=%s pid=%s",
            room_name,
            participant_name,
            context.get("generation"),
            context.get("pid"),
        )
        tracker.mark_first_token_issued(room_name=str(room_name))
        tracker.record_boot_event(
            "token_request_success",
            room=room_name,
            participant=participant_name,
            generation=context.get("generation"),
            pid=os.getpid(),
            dispatch_attempts=attempts_used,
            elapsed_ms=max(0, int((time.monotonic() - started) * 1000.0)),
            **token_env,
        )
            
        print(f"✅ [Internal] Generated token for {participant_name} in room {room_name}")
        return web.json_response({
            'token': token.to_jwt(),
            'url': os.getenv(f"LIVEKIT_URL{suffix}")
        })
    except Exception as e:
        if room_name and participant_name:
            context = _publish_token_room_context(
                room_name=room_name,
                participant_name=participant_name,
                token_status=500,
                context_state="token_failed",
                reason=str(e),
            )
            logger.warning(
                "send_message_room_context_failed room=%s participant=%s generation=%s pid=%s error=%s",
                room_name,
                participant_name,
                context.get("generation"),
                context.get("pid"),
                e,
            )
        active_slot = os.getenv("LIVEKIT_ACTIVE_SLOT", "1").strip()
        suffix = _livekit_slot_suffix(active_slot)
        token_env = _token_credentials_present_for_slot(suffix)
        get_runtime_readiness_tracker().record_boot_event(
            "token_request_failed",
            room=room_name,
            participant=participant_name,
            generation=_current_room_context_generation(),
            pid=os.getpid(),
            elapsed_ms=max(0, int((time.monotonic() - started) * 1000.0)),
            exception_type=type(e).__name__,
            exception_message=str(e),
            **token_env,
        )
        logger.error(f"❌ Token error: {e}")
        return web.json_response({'error': str(e)}, status=500)


async def handle_send_message(request):
    """Inject a test text message into the latest token-issued LiveKit room."""
    try:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON payload'}, status=400)

        if not isinstance(data, dict):
            return web.json_response({'error': 'Invalid JSON payload'}, status=400)

        message = str(data.get('message') or '').strip()
        if not message:
            return web.json_response({'error': 'message is required'}, status=400)

        user_id = str(data.get('user_id') or '').strip() or 'test_user'
        run_id = str(data.get('run_id') or '').strip()
        room_context = _room_context_snapshot()
        room_name = str(room_context.get("room_name") or "").strip()
        tracker = get_runtime_readiness_tracker()
        tracker.record_boot_event(
            "send_received",
            room=room_name or "",
            user_id=user_id,
            run_id=run_id or "",
        )
        context_generation = int(room_context.get("generation") or 0)
        current_generation = _current_room_context_generation()
        context_state = str(room_context.get("context_state") or "")
        if (
            not room_context
            or context_generation != current_generation
            or context_state != "token_issued"
            or not room_name
        ):
            logger.warning(
                "send_message_rejected_room_context user_id=%s run_id=%s generation=%s current_generation=%s state=%s pid=%s",
                user_id,
                run_id or "-",
                context_generation,
                current_generation,
                context_state or "missing",
                room_context.get("pid"),
            )
            status, payload = _room_context_error_payload(room_context)
            return web.json_response(payload, status=status)

        if run_id:
            previous_entry = _last_room_by_run_id.get(run_id) or {}
            previous_room = str(previous_entry.get("room_name") or "")
            previous_generation = int(previous_entry.get("generation") or 0)
            if previous_room and (
                previous_room != room_name or previous_generation != current_generation
            ):
                logger.warning(
                    "send_message_room_changed run_id=%s previous_room=%s previous_generation=%s new_room=%s generation=%s",
                    run_id,
                    previous_room,
                    previous_generation,
                    room_name,
                    current_generation,
                )
            _last_room_by_run_id[run_id] = {
                "room_name": room_name,
                "generation": current_generation,
                "issued_at_ms": room_context.get("issued_at_ms"),
            }

        runtime_ready = tracker.snapshot()
        if not _first_turn_route_gate_status(runtime_ready)["allowed"]:
            logger.warning(
                "send_message_rejected_warming_up room=%s user_id=%s run_id=%s state=%s cycle_id=%s",
                room_name,
                user_id,
                run_id or "-",
                runtime_ready.get("state"),
                runtime_ready.get("cycle_id"),
            )
            return web.json_response(
                _warming_up_payload(runtime_ready, room_name=room_name),
                status=503,
            )
        livekit_url, livekit_api_key, livekit_api_secret = _resolve_livekit_credentials()

        lk = LiveKitAPI(
            url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret,
        )
        try:
            wait_budget = _static_send_message_wait_budget(tracker)
            wait_budget_s = float(wait_budget["wait_budget_s"])
            poll_interval_s = _send_message_poll_interval_s()
            ready, room_status = await _wait_for_room_session_ready(
                lk,
                room_name,
                wait_budget_s=wait_budget_s,
                interval_s=poll_interval_s,
            )
            if not ready:
                tracker.record_boot_event(
                    "session_not_ready_reason",
                    room=room_name,
                    user_id=user_id,
                    run_id=run_id or "",
                    source="send_message",
                    reason=str(room_status.get("room_failure_reason") or "session_not_ready"),
                    **room_status,
                )
                logger.warning(
                    "send_message_rejected_session_not_ready room=%s user_id=%s run_id=%s class=%s dispatch_ready=%s agent_present=%s participant_count=%s attempts=%s elapsed_ms=%s",
                    room_name,
                    user_id,
                    run_id or "-",
                    room_status.get("room_failure_class"),
                    room_status.get("dispatch_ready"),
                    room_status.get("agent_present"),
                    room_status.get("participant_count"),
                    room_status.get("attempt_index"),
                    room_status.get("elapsed_ms"),
                )
                tracker.record_boot_event(
                    "session_gate_failed",
                    room=room_name,
                    user_id=user_id,
                    run_id=run_id or "",
                    source="send_message",
                    elapsed_ms=room_status.get("elapsed_ms"),
                    room_wait_budget_source=wait_budget.get("room_wait_budget_source"),
                    room_wait_budget_ms=int(max(0.0, wait_budget_s * 1000.0)),
                    room_failure_class=room_status.get("room_failure_class"),
                    first_request_arrived_at_ms=room_status.get("first_request_arrived_at_ms"),
                    first_request_released_at_ms=room_status.get("first_request_released_at_ms"),
                    worker_job_claimed_at_ms=room_status.get("worker_job_claimed_at_ms"),
                    room_joined_at_ms=room_status.get("room_joined_at_ms"),
                    session_started_at_ms=room_status.get("session_started_at_ms"),
                    session_ready_at_ms=room_status.get("session_ready_at_ms"),
                    first_turn_grace_applied=room_status.get("first_turn_grace_applied"),
                    first_turn_grace_elapsed_ms=room_status.get("first_turn_grace_elapsed_ms"),
                )
                return web.json_response(
                    {
                        "error": str(room_status.get("room_failure_class") or "session_not_ready"),
                        "retry_after_ms": 500,
                        "room": room_name,
                        "details": {
                            **room_status,
                            "wait_budget_ms": int(max(0.0, wait_budget_s * 1000.0)),
                            "room_wait_budget_ms": int(max(0.0, wait_budget_s * 1000.0)),
                            "room_wait_budget_source": wait_budget.get("room_wait_budget_source"),
                            "successful_room_join_count": int(wait_budget.get("successful_room_join_count") or 0),
                            "probe": runtime_ready.get("probe"),
                            "worker_state": runtime_ready.get("state"),
                            "worker_alive": runtime_ready.get("worker_alive"),
                            "last_probe_ok": runtime_ready.get("last_probe_ok"),
                            "last_probe_age_ms": runtime_ready.get("last_probe_age_ms"),
                            "session": runtime_ready.get("session"),
                        },
                    },
                    status=503,
                )
            tracker.record_boot_event(
                "session_gate_passed",
                room=room_name,
                user_id=user_id,
                run_id=run_id or "",
                source="send_message",
                elapsed_ms=room_status.get("elapsed_ms"),
                room_wait_budget_source=wait_budget.get("room_wait_budget_source"),
                room_wait_budget_ms=int(max(0.0, wait_budget_s * 1000.0)),
                first_request_arrived_at_ms=room_status.get("first_request_arrived_at_ms"),
                first_request_released_at_ms=room_status.get("first_request_released_at_ms"),
                worker_job_claimed_at_ms=room_status.get("worker_job_claimed_at_ms"),
                room_joined_at_ms=room_status.get("room_joined_at_ms"),
                session_started_at_ms=room_status.get("session_started_at_ms"),
                session_ready_at_ms=room_status.get("session_ready_at_ms"),
                first_turn_grace_applied=room_status.get("first_turn_grace_applied"),
                first_turn_grace_elapsed_ms=room_status.get("first_turn_grace_elapsed_ms"),
            )
            tracker.record_boot_event(
                "worker_job_claimed",
                room=room_name,
                user_id=user_id,
                run_id=run_id or "",
                source="send_message",
            )
            tracker.record_boot_event(
                "worker_job_started",
                room=room_name,
                user_id=user_id,
                run_id=run_id or "",
                source="send_message",
            )
            tracker.mark_first_session_ready(room_name=room_name)

            payload = message.encode("utf-8")
            tracker.record_boot_event(
                "first_response_started",
                room=room_name,
                user_id=user_id,
                run_id=run_id or "",
                bytes=len(payload),
            )
            await lk.room.send_data(
                room.SendDataRequest(
                    room=room_name,
                    data=payload,
                    kind=models.DataPacket.Kind.Value("RELIABLE"),
                    topic="lk.chat",
                )
            )
            tracker.record_boot_event(
                "first_response_completed",
                room=room_name,
                user_id=user_id,
                run_id=run_id or "",
                bytes=len(payload),
            )
        finally:
            await lk.aclose()

        logger.info(
            "send_message_accepted room=%s user_id=%s run_id=%s bytes=%s",
            room_name,
            user_id,
            run_id or "-",
            len(payload),
        )
        return web.json_response(
            {
                'status': 'ok',
                'room': room_name,
                'user_id': user_id,
                'run_id': run_id,
                'bytes': len(payload),
            },
            status=200,
        )
    except Exception as e:
        logger.error(
            "send_message_failed error=%s",
            e,
            exc_info=True,
        )
        return web.json_response({'error': str(e)}, status=500)

async def handle_health(request):
    """Health check endpoint with dependency validation.

    Returns 200 if all critical dependencies are reachable.
    Returns 503 if any critical dependency is unavailable.
    """
    import os
    import sqlite3
    import tempfile

    checks = {}
    healthy = True

    # Check 1: LLM provider key present
    llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if llm_provider == "groq":
        key_present = bool(os.getenv("GROQ_API_KEY", "").strip())
    elif llm_provider == "openai":
        key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
    else:
        key_present = bool(
            os.getenv("GROQ_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
    checks["llm_key"] = "ok" if key_present else "missing"
    if not key_present:
        healthy = False

    # Check 2: SQLite task store writable
    try:
        db_path = os.getenv("SQLITE_DB_PATH", "dev_maya_one.db")
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("SELECT 1")
        conn.close()
        checks["sqlite"] = "ok"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"
        healthy = False

    # Check 3: LiveKit credentials present
    livekit_url = os.getenv("LIVEKIT_URL", "").strip()
    livekit_key = os.getenv("LIVEKIT_API_KEY", "").strip()
    livekit_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
    livekit_ok = bool(livekit_url and livekit_key and livekit_secret)
    checks["livekit_credentials"] = "ok" if livekit_ok else "missing"
    if not livekit_ok:
        healthy = False

    status_code = 200 if healthy else 503
    return web.json_response(
        {
            "status": "ok" if healthy else "degraded",
            "checks": checks,
        },
        status=status_code,
    )

async def handle_ready(request):
    """Readiness check endpoint — stricter than /health.

    Validates that critical runtime dependencies are not just configured
    but actually usable. Returns 503 if any critical check fails.
    """
    readiness = get_runtime_readiness_tracker().snapshot()
    status_code = 200 if bool(readiness.get("ready")) else 503
    return web.json_response(readiness, status=status_code)

async def handle_api_keys(request):
    """Sync API keys from Flutter app to backend .env file"""
    try:
        data = await request.json()
        api_keys = {}

        provided_api_keys = data.get('apiKeys', {})
        if isinstance(provided_api_keys, dict):
            api_keys.update(provided_api_keys)

        provided_config = data.get('config', {})
        if isinstance(provided_config, dict):
            api_keys.update(provided_config)

        if not api_keys:
            return web.json_response({'error': 'No API keys or config provided'}, status=400)
        
        from dotenv import set_key
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        
        # Ensure .env exists
        if not os.path.exists(env_path):
            with open(env_path, 'w') as f:
                f.write("")
        
        def _resolve_gemini_oauth_env(provider_id: str) -> str | None:
            if provider_id in {"gemini", "gemini_1"}:
                return "GEMINI_OAUTH_ACCESS_TOKEN"
            if provider_id in {"gemini_2", "gemini_secondary"}:
                return "GEMINI_OAUTH_ACCESS_TOKEN_2"
            return None

        # Update with new keys
        updated_count = 0
        for provider_id, api_key in api_keys.items():
            # Handle Gemini OAuth access tokens sent as "OAUTH:<token>"
            if isinstance(api_key, str) and api_key.startswith("OAUTH:"):
                oauth_env = _resolve_gemini_oauth_env(provider_id)
                if oauth_env:
                    token = api_key[len("OAUTH:"):].strip()
                    if token:
                        os.environ[oauth_env] = token
                        set_key(env_path, oauth_env, token)
                        updated_count += 1
                        logger.info(f"✅ Updated {oauth_env}")
                        continue

            env_var = _provider_id_to_env_var(provider_id)

            if env_var and api_key is not None:
                # Also set in current environment
                os.environ[env_var] = str(api_key)
                set_key(env_path, env_var, str(api_key))
                updated_count += 1
                logger.info(f"✅ Updated {env_var}")

        if updated_count > 0:
            # Ensure new credentials are picked up by freshly resolved providers.
            try:
                from providers.factory import ProviderFactory
                ProviderFactory.reset_cache()
            except Exception as cache_err:
                logger.warning(f"⚠️ Failed resetting provider cache after API key sync: {cache_err}")

            try:
                from config.settings import reload_settings
                reload_settings()
            except Exception as settings_err:
                logger.warning(f"⚠️ Failed reloading settings after API key sync: {settings_err}")
        
        return web.json_response({
            'success': True,
            'updated': updated_count,
            'message': f'{updated_count} API keys synced to backend'
        })
        
    except Exception as e:
        logger.error(f"❌ API keys sync error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def handle_get_api_status(request):
    """Get status of configured API keys (masked)"""
    try:
        status = {}
        masked = {}
        
        # Base mappings
        mapping = dict(ENV_VAR_MAPPING)

        # Add dynamic mappings from environment
        for env_var in os.environ:
            if (
                env_var.endswith('_API_KEY')
                or '_API_KEY_' in env_var
                or env_var.endswith('_ACTIVE_KEY_SLOT')
                or env_var.endswith('_ACTIVE_SLOT')
                or env_var.endswith('_SLOT_COUNT')
                or env_var.startswith('LIVEKIT_')
            ) and env_var not in mapping.values():
                provider_id = _env_var_to_provider_id(env_var)
                mapping[provider_id] = env_var

        for provider_id, env_var in mapping.items():
            # Filter only pertinent keys for status
            if provider_id in ['llmprovider', 'llmmodel', 'sttprovider', 'sttmodel', 'sttlanguage', 'ttsprovider', 'ttsmodel', 'ttsvoice']:
                continue
                
            value = str(os.getenv(env_var, ''))
            if provider_id.startswith('connector_') and provider_id.endswith('_enabled'):
                status[provider_id] = _parse_env_bool(value)
            else:
                status[provider_id] = bool(value)
            is_control_value = (
                env_var.endswith('_ACTIVE_KEY_SLOT')
                or env_var.endswith('_ACTIVE_SLOT')
                or env_var.endswith('_SLOT_COUNT')
            )
            if is_control_value:
                masked[provider_id] = value
            elif value and len(value) > 8:
                masked[provider_id] = f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"
            elif value:
                masked[provider_id] = '*' * len(value)
            else:
                masked[provider_id] = ''

        # Gemini OAuth tokens should count as configured for status/masking.
        gemini_oauth_1 = os.getenv("GEMINI_OAUTH_ACCESS_TOKEN", "").strip()
        gemini_oauth_2 = os.getenv("GEMINI_OAUTH_ACCESS_TOKEN_2", "").strip()
        if gemini_oauth_1:
            status["gemini"] = True
            if not masked.get("gemini"):
                masked["gemini"] = f"{gemini_oauth_1[:4]}{'*' * max(0, len(gemini_oauth_1) - 8)}{gemini_oauth_1[-4:]}"
        if gemini_oauth_2:
            status["gemini_2"] = True
            if not masked.get("gemini_2"):
                masked["gemini_2"] = f"{gemini_oauth_2[:4]}{'*' * max(0, len(gemini_oauth_2) - 8)}{gemini_oauth_2[-4:]}"
        
        # Add combined LiveKit status (true only if all 3 are configured)
        status['livekit'] = all([
            status.get('livekit_url'),
            status.get('livekit_api_key'),
            status.get('livekit_api_secret')
        ])
        
        # Add combined MCP status
        status['n8n_mcp'] = status.get('n8n_mcp_url', False)
        
        # Add combined Supabase status (true only if all 3 are configured)
        status['supabase'] = all([
            status.get('supabase_url'),
            status.get('supabase_anon_key'),
            status.get('supabase_service_key')
        ])

        connectors = {}
        for connector_id, status_key in CONNECTOR_STATUS_KEYS.items():
            availability = CONNECTOR_AVAILABILITY.get(
                connector_id,
                {'available': False, 'reason': 'Unknown connector.'},
            )
            connectors[connector_id] = {
                'enabled': bool(status.get(status_key, False)),
                'available': bool(availability.get('available', False)),
                'reason': str(availability.get('reason', '') or ''),
            }
        
        return web.json_response({
            'status': status,
            'masked': masked,
            'connectors': connectors,
        })
        
    except Exception as e:
        logger.error(f"❌ API status error: {e}")
        return web.json_response({'error': str(e)}, status=500)
async def handle_upload(request):
    """Handle file uploads from Flutter app"""
    try:
        reader = await request.multipart()
        field = await reader.next()
        
        if not field:
            return web.json_response({'error': 'No file uploaded'}, status=400)
            
        filename = field.filename
        if not filename:
            # Fallback for some clients
            filename = f"upload_{int(asyncio.get_event_loop().time())}"
            
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        
        file_path = os.path.join(uploads_dir, filename)
        
        # Avoid overwriting (basic version)
        if os.path.exists(file_path):
            base, ext = os.path.splitext(filename)
            file_path = os.path.join(uploads_dir, f"{base}_{int(asyncio.get_event_loop().time())}{ext}")
            filename = os.path.basename(file_path)

        size = 0
        with open(file_path, 'wb') as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                f.write(chunk)
        
        logger.info(f"✅ File uploaded: {filename} ({size} bytes)")
        
        # Return the public/local URL
        # Assuming the token server port 5050
        file_url = f"http://localhost:5050/uploads/{filename}"
        
        return web.json_response({
            'success': True,
            'filename': filename,
            'url': file_url,
            'size': size
        })
    except Exception as e:
        logger.error(f"❌ Upload error: {e}")
        return web.json_response({'error': str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal WebSocket Handlers (P12.3)
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_ide_terminal_open(request):
    """POST /ide/terminal/open — Create terminal session, return session_id + token."""
    from core.ide import TerminalManager, TerminalLimitExceededError

    try:
        data = await request.json()
        ide_session_id = data.get("ide_session_id", "")
        user_id = data.get("user_id", "")
        cwd = data.get("cwd", "~")

        if not ide_session_id or not user_id:
            return web.json_response(
                {"error": "Missing ide_session_id or user_id"},
                status=400,
            )

        terminal_manager = _get_terminal_manager_component(request)

        session_id, token, expires_at = await terminal_manager.open_terminal(
            ide_session_id=ide_session_id,
            user_id=user_id,
            cwd=cwd,
        )

        logger.info("terminal_opened session_id=%s user_id=%s", session_id, user_id)
        return web.json_response({
            "status": "ok",
            "session_id": session_id,
            "token": token,
            "expires_at": expires_at,
            "ws_url": f"/ws/terminal?session_id={session_id}&token={token}",
        })
    except TerminalLimitExceededError as e:
        logger.warning("terminal_limit_exceeded user_id=%s", user_id)
        return web.json_response({"error": str(e)}, status=429)
    except Exception as e:
        logger.error("❌ Terminal open failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_terminal_close(request):
    """POST /ide/terminal/close — Close terminal session."""
    try:
        data = await request.json()
        session_id = data.get("session_id", "")

        if not session_id:
            return web.json_response(
                {"error": "Missing session_id"},
                status=400,
            )

        terminal_manager = _get_terminal_manager_component(request)

        success = await terminal_manager.close_terminal(session_id)
        if not success:
            return web.json_response(
                {"error": "Session not found or already closed"},
                status=404,
            )

        logger.info("terminal_closed session_id=%s", session_id)
        return web.json_response({"status": "ok", "session_id": session_id})
    except Exception as e:
        logger.error("❌ Terminal close failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_terminal_resize(request):
    """POST /ide/terminal/resize — Resize terminal."""
    try:
        data = await request.json()
        session_id = data.get("session_id", "")
        rows = data.get("rows", 24)
        cols = data.get("cols", 80)

        if not session_id:
            return web.json_response(
                {"error": "Missing session_id"},
                status=400,
            )

        terminal_manager = _get_terminal_manager_component(request)

        success = await terminal_manager.resize_terminal(session_id, rows, cols)
        if not success:
            return web.json_response(
                {"error": "Session not found or resize failed"},
                status=404,
            )

        return web.json_response({"status": "ok", "session_id": session_id})
    except Exception as e:
        logger.error("❌ Terminal resize failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_terminal_websocket(request):
    """WebSocket endpoint for terminal streaming."""
    from core.ide import TerminalManager

    session_id = request.query.get("session_id", "")
    token = request.query.get("token", "")

    if not session_id or not token:
        return web.json_response(
            {"error": "Missing session_id or token"},
            status=400,
        )

    try:
        terminal_manager = _get_terminal_manager_component(request)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=503)

    # Validate token
    session = await terminal_manager.validate_token(token)
    if session is None or session.session_id != session_id:
        return web.json_response(
            {"error": "Invalid token or session"},
            status=401,
        )

    ws = web.WebSocketResponse(
        heartbeat=30.0,
        autoping=True,
    )
    await ws.prepare(request)

    logger.info("terminal_ws_connected session_id=%s", session_id)
    session.reconnect_count += 1

    # Send initial acknowledgement with current offset
    await ws.send_json({
        "type": "connected",
        "session_id": session_id,
        "reconnect_count": session.reconnect_count,
        "offset": session.write_offset,
    })

    # Send any buffered output since last known offset (for reconnects)
    last_offset = session.write_offset
    try:
        # Background: stream output + handle input
        input_task = asyncio.create_task(
            _terminal_input_handler(ws, terminal_manager, session_id)
        )
        output_task = asyncio.create_task(
            _terminal_output_handler(ws, terminal_manager, session_id, last_offset)
        )

        done, pending = await asyncio.wait(
            [input_task, output_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel remaining task
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.warning("terminal_ws_error session_id=%s error=%s", session_id, e)
    finally:
        logger.info("terminal_ws_disconnected session_id=%s", session_id)
        await ws.close()

    return ws


async def _terminal_input_handler(
    ws,
    terminal_manager,
    session_id: str,
):
    """Handle input from WebSocket client to PTY."""
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    data = {}
                msg_type = data.get("type")

                if msg_type == "input":
                    # Terminal input
                    text = data.get("text", "")
                    await terminal_manager.write_input(session_id, text)

                elif msg_type == "resize":
                    # Resize event
                    rows = data.get("rows", 24)
                    cols = data.get("cols", 80)
                    await terminal_manager.resize_terminal(session_id, rows, cols)

                elif msg_type == "ping":
                    # Client ping -> pong
                    await ws.send_json({"type": "pong", "ts": data.get("ts")})

            elif msg.type == WSMsgType.BINARY:
                # Binary input (raw bytes)
                text = msg.data.decode("utf-8", errors="replace")
                await terminal_manager.write_input(session_id, text)

            elif msg.type == WSMsgType.ERROR:
                logger.warning("terminal_ws_error session_id=%s", session_id)
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("terminal_input_error session_id=%s error=%s", session_id, e)


async def _terminal_output_handler(
    ws,
    terminal_manager,
    session_id: str,
    start_offset: int,
):
    """Stream output from PTY ring buffer to WebSocket."""
    try:
        last_offset = start_offset

        while True:
            # Get new output since last offset
            chunks, new_offset = await terminal_manager.get_output_since(
                session_id, last_offset
            )

            for write_idx, chunk in chunks:
                await ws.send_json({
                    "type": "output",
                    "text": chunk,
                    "offset": write_idx,
                })

            last_offset = new_offset

            # Small sleep to avoid busy loop
            await asyncio.sleep(0.05)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("terminal_output_error session_id=%s error=%s", session_id, e)


# ═══════════════════════════════════════════════════════════════════════════════
# Pending Action API Handlers (P13)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_pending_action_components():
    from core.runtime.global_agent import GlobalAgentContainer

    action_guard = GlobalAgentContainer.get_ide_action_guard()
    pending_store = GlobalAgentContainer.get_pending_action_store()
    state_bus = GlobalAgentContainer.get_ide_state_bus()
    if not all([action_guard, pending_store, state_bus]):
        raise RuntimeError("Pending action runtime not initialized")
    return action_guard, pending_store, state_bus


def _parse_action_type(action_type: str) -> tuple[str, str]:
    normalized = str(action_type or "").strip()
    if ":" in normalized:
        target, operation = normalized.split(":", 1)
        return target.strip(), operation.strip()
    if "_" in normalized:
        target, operation = normalized.split("_", 1)
        return target.strip(), operation.strip()
    return normalized, normalized


def _normalize_action_envelope(raw: dict):
    from core.ide import ActionEnvelope

    action = raw.get("action")
    if isinstance(action, dict):
        target = str(action.get("target", "")).strip()
        operation = str(action.get("operation", "")).strip()
        arguments = dict(action.get("arguments") or {})
        envelope = ActionEnvelope(
            type="ide_action",
            target=target,
            operation=operation,
            arguments=arguments,
            confidence=float(action.get("confidence") or 1.0),
            reason=str(action.get("reason") or "request"),
        )
        target_id = str(arguments.get("target_id") or arguments.get("task_id") or target or operation).strip()
        return envelope, target_id

    legacy_type = str(raw.get("action_type") or "").strip()
    target, operation = _parse_action_type(legacy_type)
    payload = dict(raw.get("payload") or {})
    target_id = str(raw.get("target_id") or payload.get("target_id") or payload.get("task_id") or "").strip()
    if not target_id:
        target_id = target or operation
    envelope = ActionEnvelope(
        type="ide_action",
        target=target,
        operation=operation,
        arguments=payload,
        confidence=1.0,
        reason="legacy request",
    )
    return envelope, target_id


def _serialize_pending_action(action) -> dict:
    return {
        "action_id": action.action_id,
        "action_type": action.action_type,
        "target_id": action.target_id,
        "risk": action.risk,
        "policy_reason": action.policy_reason,
        "requested_at": action.requested_at,
        "expires_at": action.expires_at,
        "user_id": action.user_id,
        "session_id": action.session_id,
        "trace_id": action.trace_id,
        "task_id": action.task_id,
        "payload": dict(action.payload or {}),
    }


def _serialize_audit_event(event) -> dict:
    return {
        "action_id": event.action_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "user_id": event.user_id,
        "session_id": event.session_id,
        "action_type": event.action_type,
        "risk": event.risk,
        "idempotency_key": event.idempotency_key,
        "decided_by": event.decided_by,
        "decided_at": event.decided_at,
        "execution_result": event.execution_result,
        "error": event.error,
        "trace_id": event.trace_id,
        "task_id": event.task_id,
    }


def _action_idempotency_fallback(data: dict, envelope) -> str:
    existing = str(data.get("idempotency_key") or "").strip()
    if existing:
        return existing
    base = f"{data.get('user_id','')}::{data.get('session_id','')}::{envelope.target}:{envelope.operation}::{json.dumps(envelope.arguments, sort_keys=True)}"
    return str(abs(hash(base)))


async def _execute_ide_action(*, envelope, session_id: str, user_id: str, timeout_seconds: float = 10.0):
    from core.runtime.global_agent import GlobalAgentContainer

    async def _run():
        target = envelope.target.lower().strip()
        operation = envelope.operation.lower().strip()
        arguments = dict(envelope.arguments or {})
        state_bus = GlobalAgentContainer.get_ide_state_bus()

        if target == "agent":
            event_type = {
                "task_retry": "task_retry_requested",
                "retry": "task_retry_requested",
                "task_cancel": "task_cancel_requested",
                "cancel": "task_cancel_requested",
                "approve": "task_approval_requested",
                "deny": "task_denial_requested",
                "spawn": "agent_spawn_requested",
                "agent_spawn": "agent_spawn_requested",
            }.get(operation, "task_action_requested")
            await state_bus.emit(
                event_type,
                {
                    "session_id": session_id,
                    "task_id": str(arguments.get("task_id") or ""),
                    "agent_id": "approval-center",
                    "status": "requested",
                    "payload": {"operation": operation, "arguments": arguments, "user_id": user_id},
                },
            )

            if operation in {"spawn", "agent_spawn"}:
                from core.tools.agent_tools import spawn_subagent

                agent_type = str(arguments.get("agent_type") or "").strip().lower()
                task = str(arguments.get("task") or "").strip()
                use_worktree = bool(arguments.get("use_worktree", False))
                if not agent_type:
                    raise ValueError("agent_type is required for spawn action")
                if not task:
                    raise ValueError("task is required for spawn action")

                await state_bus.emit(
                    "agent_spawn_executing",
                    {
                        "session_id": session_id,
                        "task_id": str(arguments.get("task_id") or ""),
                        "agent_id": "approval-center",
                        "status": "executing",
                        "payload": {
                            "operation": operation,
                            "agent_type": agent_type,
                            "task": task,
                            "use_worktree": use_worktree,
                            "user_id": user_id,
                        },
                    },
                )
                spawn_result = await spawn_subagent(
                    agent_type=agent_type,
                    task=task,
                    wait=False,
                    use_worktree=use_worktree,
                )
                success = not str(spawn_result).startswith("Error:")
                await state_bus.emit(
                    "agent_spawn_finished",
                    {
                        "session_id": session_id,
                        "task_id": str(arguments.get("task_id") or ""),
                        "agent_id": "approval-center",
                        "status": "success" if success else "failed",
                        "payload": {
                            "operation": operation,
                            "agent_type": agent_type,
                            "task": task,
                            "use_worktree": use_worktree,
                            "spawn_result": spawn_result,
                            "user_id": user_id,
                        },
                    },
                )
                return {
                    "executed": success,
                    "target": target,
                    "operation": operation,
                    "result": spawn_result,
                }

            return {"executed": True, "target": target, "operation": operation}

        if target == "terminal" and operation == "exec":
            manager = GlobalAgentContainer.get_terminal_manager()
            terminal_session_id = str(
                arguments.get("terminal_session_id") or arguments.get("session_id") or ""
            ).strip()
            command = str(arguments.get("command") or arguments.get("cmd") or "").strip()
            if manager is None:
                raise RuntimeError("terminal manager unavailable")
            if not terminal_session_id:
                raise ValueError("terminal_session_id is required")
            if not command:
                raise ValueError("command is required")
            ok = await manager.write_input(terminal_session_id, f"{command}\n")
            if not ok:
                raise RuntimeError("terminal session not found or write failed")
            return {"executed": True, "target": target, "operation": operation, "terminal_session_id": terminal_session_id}

        if target in {"mcp", "plugin", "setting"}:
            return _apply_config_mutation(target=target, operation=operation, arguments=arguments)

        return {"executed": False, "target": target, "operation": operation, "reason": "unsupported executable action"}

    return await asyncio.wait_for(_run(), timeout=timeout_seconds)


def _apply_config_mutation(*, target: str, operation: str, arguments: dict) -> dict:
    target = target.lower().strip()
    operation = operation.lower().strip()

    # P13 keeps mutating actions guarded and explicit. Mutations update runtime env only.
    if target == "mcp":
        if operation in {"set_url", "update"}:
            url = str(arguments.get("url") or arguments.get("value") or "").strip()
            if not url:
                raise ValueError("url is required")
            previous = os.getenv("N8N_MCP_SERVER_URL", "")
            os.environ["N8N_MCP_SERVER_URL"] = url
            return {"executed": True, "previous": previous, "current": url}
        if operation in {"toggle", "enable", "disable"}:
            enabled = operation in {"toggle", "enable"}
            if "enabled" in arguments:
                enabled = bool(arguments.get("enabled"))
            os.environ["CONNECTOR_GOOGLE_WORKSPACE_ENABLED"] = "true" if enabled else "false"
            return {"executed": True, "enabled": enabled}
        raise ValueError(f"unsupported mcp operation: {operation}")

    if target == "setting":
        key = str(arguments.get("key") or "").strip()
        if not key:
            raise ValueError("setting key is required")
        env_var = _provider_id_to_env_var(key) or key.upper()
        previous = os.getenv(env_var, "")
        if operation in {"set", "toggle", "enable", "disable"}:
            if operation == "set":
                value = str(arguments.get("value") or "")
            elif operation in {"enable", "disable"}:
                value = "true" if operation == "enable" else "false"
            else:
                requested = arguments.get("value", arguments.get("enabled", True))
                value = "true" if bool(requested) else "false"
            os.environ[env_var] = value
            return {"executed": True, "env_var": env_var, "previous": previous, "current": value}
        raise ValueError(f"unsupported setting operation: {operation}")

    if target == "plugin":
        plugin_name = str(arguments.get("name") or arguments.get("plugin") or "").strip()
        if not plugin_name:
            raise ValueError("plugin name is required")
        if operation in {"install", "enable", "disable", "toggle"}:
            return {"executed": True, "plugin": plugin_name, "operation": operation}
        raise ValueError(f"unsupported plugin operation: {operation}")

    raise ValueError(f"unsupported target for mutation: {target}")


def _build_mcp_inventory() -> dict:
    from core.runtime.global_agent import GlobalAgentContainer

    plugin_loader = GlobalAgentContainer.get_plugin_loader()
    loaded_plugins = sorted((plugin_loader.loaded() or {}).keys()) if plugin_loader else []
    discovered_plugins = sorted(plugin_loader.discover()) if plugin_loader else []

    connectors = {}
    for connector_id, status_key in CONNECTOR_STATUS_KEYS.items():
        availability = CONNECTOR_AVAILABILITY.get(
            connector_id,
            {"available": False, "reason": "Unknown connector."},
        )
        env_key = ENV_VAR_MAPPING.get(status_key, status_key.upper())
        connectors[connector_id] = {
            "enabled": _parse_env_bool(os.getenv(env_key, "")),
            "available": bool(availability.get("available", False)),
            "reason": str(availability.get("reason", "") or ""),
        }

    return {
        "mcp_servers": {
            "n8n": {
                "url": str(os.getenv("N8N_MCP_SERVER_URL", "")).strip(),
                "configured": bool(str(os.getenv("N8N_MCP_SERVER_URL", "")).strip()),
            }
        },
        "plugins": {
            "loaded": loaded_plugins,
            "discovered": discovered_plugins,
        },
        "connectors": connectors,
    }


async def handle_ide_action_request(request):
    """POST /ide/action/request — Submit action request (guarded execution)."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json payload"}, status=400)

    user_id = str((data or {}).get("user_id") or "").strip()
    session_id = str((data or {}).get("session_id") or "").strip()
    trace_id = str((data or {}).get("trace_id") or "").strip() or None
    task_id = str((data or {}).get("task_id") or "").strip() or None
    if not user_id or not session_id:
        return web.json_response({"error": "user_id and session_id are required"}, status=400)

    try:
        envelope, target_id = _normalize_action_envelope(data or {})
        idempotency_key = _action_idempotency_fallback(data or {}, envelope)
        action_type = f"{envelope.target}:{envelope.operation}"
        action_guard, pending_store, state_bus = _get_pending_action_components()

        decision = action_guard.check(envelope)
        if not decision.allowed:
            await state_bus.emit(
                "action_blocked",
                {
                    "session_id": session_id,
                    "trace_id": trace_id,
                    "task_id": task_id,
                    "agent_id": "approval-center",
                    "status": "blocked",
                    "payload": {
                        "action_type": action_type,
                        "target_id": target_id,
                        "risk": decision.risk,
                        "policy_reason": decision.policy_reason,
                    },
                },
            )
            return _guard_error_response(decision)

        if decision.requires_approval:
            pending = await pending_store.request(
                user_id=user_id,
                session_id=session_id,
                action_type=action_type,
                target_id=target_id,
                payload={"action": {"target": envelope.target, "operation": envelope.operation, "arguments": envelope.arguments}},
                risk=decision.risk,
                policy_reason=decision.policy_reason,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                task_id=task_id,
            )
            return web.json_response(
                {
                    "action_id": pending.action_id,
                    "status": "pending",
                    "risk": pending.risk,
                    "policy_reason": pending.policy_reason,
                    "requires_approval": True,
                }
            )

        try:
            execution = await _execute_ide_action(
                envelope=envelope,
                session_id=session_id,
                user_id=user_id,
                timeout_seconds=10.0,
            )
        except asyncio.TimeoutError:
            return web.json_response(
                {"error": "action execution timed out", "status": "failed", "action_type": action_type},
                status=504,
            )

        return web.json_response(
            {
                "action_id": f"exec_{idempotency_key[:16]}",
                "status": "executed",
                "result": execution,
                "risk": decision.risk,
                "requires_approval": False,
            }
        )
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        logger.error("❌ Action request failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_action_pending(request):
    """GET /ide/action/pending — List pending actions."""
    try:
        user_id = str(request.query.get("user_id", "")).strip() or None
        _action_guard, pending_store, _state_bus = _get_pending_action_components()
        actions = await pending_store.get_pending(user_id=user_id)
        return web.json_response({"actions": [_serialize_pending_action(action) for action in actions]})
    except Exception as e:
        logger.error("❌ Action pending fetch failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_action_audit(request):
    """GET /ide/action/audit — List action audit events."""
    try:
        user_id = str(request.query.get("user_id", "")).strip() or None
        session_id = str(request.query.get("session_id", "")).strip() or None
        limit = _parse_positive_int(request.query.get("limit"), default=200)
        _action_guard, pending_store, _state_bus = _get_pending_action_components()
        events = await pending_store.get_audit_events(user_id=user_id, session_id=session_id, limit=limit)
        return web.json_response({"events": [_serialize_audit_event(event) for event in events]})
    except Exception as e:
        logger.error("❌ Action audit fetch failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_action_approve(request):
    """POST /ide/action/approve — Approve and execute pending action."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json payload"}, status=400)

    action_id = str((data or {}).get("action_id") or "").strip()
    decided_by = str((data or {}).get("decided_by") or "").strip()
    reason = str((data or {}).get("reason") or "").strip()
    if not action_id or not decided_by:
        return web.json_response({"error": "action_id and decided_by are required"}, status=400)

    try:
        _action_guard, pending_store, _state_bus = _get_pending_action_components()
        action = await pending_store.approve(
            action_id=action_id,
            decided_by=decided_by,
            execution_result={"approval_reason": reason},
        )
        if action is None:
            return web.json_response({"error": "Action not found or already processed"}, status=404)

        payload_action = dict((action.payload or {}).get("action") or {})
        target = str(payload_action.get("target") or "").strip()
        operation = str(payload_action.get("operation") or "").strip()
        arguments = dict(payload_action.get("arguments") or {})
        if not target or not operation:
            target, operation = _parse_action_type(action.action_type)
            arguments = dict(action.payload or {})

        from core.ide import ActionEnvelope

        envelope = ActionEnvelope(
            type="ide_action",
            target=target,
            operation=operation,
            arguments=arguments,
            confidence=1.0,
            reason="approved action execution",
        )
        try:
            result = await _execute_ide_action(
                envelope=envelope,
                session_id=action.session_id,
                user_id=action.user_id,
                timeout_seconds=15.0,
            )
            await pending_store.record_execution_result(
                action=action,
                succeeded=True,
                execution_result=result,
            )
            return web.json_response(
                {
                    "action_id": action.action_id,
                    "status": "executed",
                    "executed_at": time.monotonic(),
                    "result": result,
                }
            )
        except asyncio.TimeoutError:
            await pending_store.record_execution_result(
                action=action,
                succeeded=False,
                error="execution timeout",
            )
            return web.json_response(
                {"error": "action execution timed out", "action_id": action.action_id, "status": "failed"},
                status=504,
            )
        except Exception as exec_err:
            await pending_store.record_execution_result(
                action=action,
                succeeded=False,
                error=str(exec_err),
            )
            return web.json_response(
                {"error": str(exec_err), "action_id": action.action_id, "status": "failed"},
                status=500,
            )
    except Exception as e:
        logger.error("❌ Action approve failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_action_deny(request):
    """POST /ide/action/deny — Deny pending action."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json payload"}, status=400)

    action_id = str((data or {}).get("action_id") or "").strip()
    decided_by = str((data or {}).get("decided_by") or "").strip()
    reason = str((data or {}).get("reason") or "").strip()
    if not action_id or not decided_by or not reason:
        return web.json_response(
            {"error": "action_id, decided_by, and reason are required"},
            status=400,
        )

    try:
        _action_guard, pending_store, _state_bus = _get_pending_action_components()
        success = await pending_store.deny(
            action_id=action_id,
            decided_by=decided_by,
            reason=reason,
        )
        if not success:
            return web.json_response({"error": "Action not found or already processed"}, status=404)

        return web.json_response(
            {
                "action_id": action_id,
                "status": "denied",
                "decided_by": decided_by,
                "reason": reason,
            }
        )
    except Exception as e:
        logger.error("❌ Action deny failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_action_cancel(request):
    """POST /ide/action/cancel — Cancel own pending action."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json payload"}, status=400)

    action_id = str((data or {}).get("action_id") or "").strip()
    user_id = str((data or {}).get("user_id") or "").strip()
    if not action_id or not user_id:
        return web.json_response({"error": "action_id and user_id are required"}, status=400)

    try:
        _action_guard, pending_store, _state_bus = _get_pending_action_components()
        success = await pending_store.cancel(action_id=action_id, user_id=user_id)
        if not success:
            return web.json_response({"error": "Action not found or not owned by user"}, status=403)

        return web.json_response(
            {
                "action_id": action_id,
                "status": "cancelled",
            }
        )
    except Exception as e:
        logger.error("❌ Action cancel failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_mcp_inventory(request):
    """GET /ide/mcp/inventory — MCP/plugin inventory for IDE control surface."""
    try:
        return web.json_response(_build_mcp_inventory())
    except Exception as e:
        logger.error("❌ MCP inventory failed: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def handle_ide_mcp_mutate(request):
    """POST /ide/mcp/mutate — Guarded MCP/plugin/setting mutation request."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json payload"}, status=400)

    user_id = str((data or {}).get("user_id") or "").strip()
    session_id = str((data or {}).get("session_id") or "").strip()
    if not user_id or not session_id:
        return web.json_response({"error": "user_id and session_id are required"}, status=400)

    action = dict((data or {}).get("action") or {})
    target = str(action.get("target") or "").strip().lower()
    if target not in {"mcp", "plugin", "setting"}:
        return web.json_response({"error": "action.target must be one of mcp|plugin|setting"}, status=400)

    # Reuse generic action request path for guard + pending + execution behavior.
    class _LocalRequest:
        def __init__(self, payload):
            self._payload = payload

        async def json(self):
            return self._payload

    return await handle_ide_action_request(_LocalRequest(data))
