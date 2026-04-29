import json
import logging
import os
import threading
import time
import uuid
import math
import statistics
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

_B5_STARTUP_GATE_TIMEOUT_CLASSES = {
    "transport_attach_timeout",
    "audio_output_start_timeout",
    "pipeline_timeout",
    "transport_frame_timeout",
    "first_audio_packet_timeout",
    "first_pcm_frame_timeout",
    "callback_path_miss",
    "unknown_media_bind_timeout",
    "unknown_timeout",
}


class ReadinessState(str, Enum):
    BOOTING = "BOOTING"
    TOKEN_READY = "TOKEN_READY"
    WORKER_CONNECTING = "WORKER_CONNECTING"
    READY_INFRA = "READY_INFRA"
    SESSION_WARMING = "SESSION_WARMING"
    READY_SESSION_CAPABLE = "READY_SESSION_CAPABLE"
    CAPABILITY_INITIALIZING = "CAPABILITY_INITIALIZING"
    READY_CAPABILITY = "READY_CAPABILITY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _classify_listener_order(
    *,
    attach_ts_ms: float | None,
    emit_ts_ms: float | None,
    consume_ts_ms: float | None,
) -> str:
    if (
        emit_ts_ms is not None
        and attach_ts_ms is not None
        and emit_ts_ms < attach_ts_ms
    ):
        return "event_emitted_before_listener"
    if emit_ts_ms is None:
        return "event_never_emitted"
    if consume_ts_ms is None:
        return "event_emitted_not_consumed"
    return "event_attached_and_consumed"


def _classify_b5_startup_gate(room_state: dict[str, Any]) -> str:
    listener_ordering = _classify_listener_order(
        attach_ts_ms=room_state.get("listener_attach_ts_ms"),
        emit_ts_ms=room_state.get("track_subscribed_emit_ts_ms"),
        consume_ts_ms=room_state.get("track_subscribed_consume_ts_ms"),
    )
    if listener_ordering == "event_emitted_before_listener":
        return "event_emitted_before_listener"
    participant_or_track_missing = (
        room_state.get("participant_visible_ts_ms") is None
        or room_state.get("track_published_ts_ms") is None
    )
    failure_timeout_class = str(room_state.get("session_failure_timeout_class") or "")
    if failure_timeout_class in {"participant_missing_timeout", "publish_timeout"}:
        return "participant_or_track_never_visible"
    if (
        listener_ordering == "event_emitted_not_consumed"
        or (
            room_state.get("track_subscribed_emit_ts_ms") is not None
            and room_state.get("track_subscribed_consume_ts_ms") is None
        )
        or failure_timeout_class == "subscription_timeout"
    ):
        return "subscription_never_completed"
    if failure_timeout_class in _B5_STARTUP_GATE_TIMEOUT_CLASSES:
        return "bind_gate_timeout"
    if (
        room_state.get("teardown_begin_ts_ms") is not None
        or room_state.get("teardown_ipc_closed_ts_ms") is not None
    ):
        return "teardown_interrupted_startup"
    if participant_or_track_missing:
        return "participant_or_track_never_visible"
    return "unknown_startup_gate"


@dataclass
class RuntimeReadinessTracker:
    state: ReadinessState = ReadinessState.BOOTING
    boot_started_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    cycle_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    api_up: bool = False
    token_server_up: bool = False
    worker_connected: bool = False
    dispatch_pipeline_ready: bool = False
    capability_init_started: bool = False
    capability_ready: bool = False
    capability_failure_reason: str | None = None
    last_claim_probe_ok: bool = False
    idle_process_ready: bool = False
    last_claim_probe_at_ms: int | None = None
    last_claim_probe_error: str | None = None
    claim_probe_started_at_ms: int | None = None
    claim_probe_claimed_at_ms: int | None = None
    claimable_ready_at_ms: int | None = None
    idle_process_ready_at_ms: int | None = None
    claim_probe_room_name: str | None = None
    claim_probe_stage: str | None = None
    claim_probe_status: str | None = None
    claim_probe_timeout_budget_ms: int | None = None
    claim_probe_failure_reason: str | None = None
    infra_ready_at_ms: int | None = None
    fatal_startup_fault: bool = False
    last_worker_heartbeat_ms: int = 0
    first_worker_heartbeat_seen: bool = False
    core_ready_at_ms: int | None = None
    worker_connect_stage: str = "idle"
    worker_connect_attempt: int = 0
    active_worker_attempt: str = ""
    last_invalidated_worker_attempt: str = ""
    worker_connect_started_at_ms: int | None = None
    worker_conn_task_started_at_ms: int | None = None
    worker_connected_at_ms: int | None = None
    worker_registered_at_ms: int | None = None
    worker_connect_error_at_ms: int | None = None
    worker_connect_error_type: str | None = None
    worker_connect_error_message: str | None = None
    worker_connect_timeout_reason: str | None = None
    worker_connect_retry_reason: str | None = None
    worker_connect_error_stage: str | None = None
    worker_attempt_timing_ms: dict[str, int | None] = field(default_factory=dict)
    worker_attempt_stage_status: dict[str, str] = field(default_factory=dict)
    inference_stage_timing_ms: dict[str, int | None] = field(default_factory=dict)
    inference_stage_status: dict[str, str] = field(default_factory=dict)
    inference_runner_timing_ms: dict[str, dict[str, int | None]] = field(default_factory=dict)
    inference_runner_names: list[str] = field(default_factory=list)
    stale_worker_started_count: int = 0
    stale_worker_registered_count: int = 0
    stale_worker_claim_count: int = 0
    late_active_worker_registered_count: int = 0
    last_stale_callback_ms: int | None = None
    last_late_active_callback_ms: int | None = None
    last_worker_claim_at_ms: int | None = None
    last_room_joined_at_ms: int | None = None
    last_session_started_at_ms: int | None = None
    last_session_ready_at_ms: int | None = None
    last_session_failure_at_ms: int | None = None
    last_session_failure_reason: str | None = None
    last_worker_disconnect_at_ms: int | None = None
    active_session_count: int = 0
    enhanced_turn_detection_ready: bool = False
    enhanced_turn_detection_mode: str = ""
    eou_registration_state: str = "idle"
    eou_registration_error: str = ""
    eou_init_thread_handoff_count: int = 0
    eou_init_main_thread_success: int = 0
    eou_init_main_thread_fail: int = 0
    eou_upgrade_success: int = 0
    onnx_init_state: str = "idle"
    onnx_init_error: str = ""
    onnx_init_started_at_ms: int | None = None
    onnx_background_ready_at_ms: int | None = None
    onnx_first_use_wait_ms: int | None = None
    sessions_started_on_stt: int = 0
    sessions_upgraded_to_eou: int = 0
    sessions_completed_without_eou: int = 0
    upgrade_failures: int = 0
    turn_detection_upgrade_durations_ms: list[int] = field(default_factory=list)
    capability_init_started_at_ms: int | None = None
    capability_ready_at_ms: int | None = None
    global_init_started_at_ms: int | None = None
    global_init_completed_at_ms: int | None = None
    global_init_total_ms: int | None = None
    global_init_stage_order: list[str] = field(default_factory=list)
    global_init_stage_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    semantic_memory_ready: bool = False
    semantic_memory_warming: bool = False
    semantic_memory_boot_mode: str = ""
    semantic_memory_error: str = ""
    semantic_memory_warmup_started_at_ms: int | None = None
    semantic_memory_ready_at_ms: int | None = None
    semantic_memory_query_degraded_count: int = 0
    semantic_memory_add_deferred_count: int = 0
    llm_fallback_ready: bool = False
    llm_fallback_warming: bool = False
    llm_fallback_boot_mode: str = ""
    llm_fallback_error: str = ""
    llm_fallback_warmup_started_at_ms: int | None = None
    llm_fallback_ready_at_ms: int | None = None
    last_transition_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    mode: str = "unknown"
    version: str = "dev"
    timeline_enabled: bool = field(default_factory=lambda: _bool_env("MAYA_BOOT_TIMELINE_ENABLED", True))
    boot_events_path: str = field(default_factory=lambda: os.getenv(
        "MAYA_BOOT_EVENTS_PATH",
        "reports/phase40_2/boot_events.jsonl",
    ))

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _boot_events_synced_offset: int = field(default=0, repr=False)
    _room_stage_by_room: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    @staticmethod
    def _empty_worker_attempt_timing() -> dict[str, int | None]:
        return {
            "attempt_started_at_ms": None,
            "credentials_begin_at_ms": None,
            "credentials_end_at_ms": None,
            "server_created_at_ms": None,
            "server_run_enter_at_ms": None,
            "worker_run_enter_at_ms": None,
            "worker_network_connect_begin_at_ms": None,
            "worker_auth_begin_at_ms": None,
            "worker_registration_begin_at_ms": None,
            "plugin_preload_begin_at_ms": None,
            "plugin_preload_end_at_ms": None,
            "inference_executor_start_begin_at_ms": None,
            "inference_executor_start_end_at_ms": None,
            "inference_executor_initialize_begin_at_ms": None,
            "inference_executor_initialize_end_at_ms": None,
            "http_server_start_begin_at_ms": None,
            "http_server_start_end_at_ms": None,
            "proc_pool_start_begin_at_ms": None,
            "proc_pool_start_end_at_ms": None,
            "proc_pool_process_created_at_ms": None,
            "proc_pool_process_started_at_ms": None,
            "proc_pool_process_ready_at_ms": None,
            "worker_conn_task_scheduled_at_ms": None,
            "worker_started_at_ms": None,
            "worker_started_event_at_ms": None,
            "worker_registered_at_ms": None,
            "worker_registered_event_at_ms": None,
            "worker_heartbeat_first_seen_at_ms": None,
            "claim_probe_sent_at_ms": None,
            "claim_probe_claimed_at_ms": None,
            "claim_probe_passed_at_ms": None,
            "runtime_ready_at_ms": None,
        }

    @staticmethod
    def _boot_stage_definitions() -> list[tuple[str, str]]:
        return [
            ("credentials_begin", "credentials_begin_at_ms"),
            ("credentials_end", "credentials_end_at_ms"),
            ("server_created", "server_created_at_ms"),
            ("worker_run_enter", "worker_run_enter_at_ms"),
            ("worker_network_connect_begin", "worker_network_connect_begin_at_ms"),
            ("worker_auth_begin", "worker_auth_begin_at_ms"),
            ("worker_registration_begin", "worker_registration_begin_at_ms"),
            ("plugin_preload_begin", "plugin_preload_begin_at_ms"),
            ("plugin_preload_end", "plugin_preload_end_at_ms"),
            ("inference_executor_start_begin", "inference_executor_start_begin_at_ms"),
            ("inference_executor_start_end", "inference_executor_start_end_at_ms"),
            ("inference_executor_initialize_begin", "inference_executor_initialize_begin_at_ms"),
            ("inference_executor_initialize_end", "inference_executor_initialize_end_at_ms"),
            ("http_server_start_begin", "http_server_start_begin_at_ms"),
            ("http_server_start_end", "http_server_start_end_at_ms"),
            ("proc_pool_start_begin", "proc_pool_start_begin_at_ms"),
            ("proc_pool_process_created", "proc_pool_process_created_at_ms"),
            ("proc_pool_process_started", "proc_pool_process_started_at_ms"),
            ("proc_pool_process_ready", "proc_pool_process_ready_at_ms"),
            ("proc_pool_start_end", "proc_pool_start_end_at_ms"),
            ("worker_conn_task_scheduled", "worker_conn_task_scheduled_at_ms"),
            ("worker_started_event", "worker_started_event_at_ms"),
            ("worker_registered_event", "worker_registered_event_at_ms"),
            ("worker_heartbeat_first_seen", "worker_heartbeat_first_seen_at_ms"),
        ]

    @staticmethod
    def _empty_inference_stage_timing() -> dict[str, int | None]:
        return {
            "inference_runner_registration_begin_at_ms": None,
            "inference_runner_registration_end_at_ms": None,
            "inference_proc_spawn_begin_at_ms": None,
            "inference_proc_spawn_end_at_ms": None,
            "inference_child_boot_begin_at_ms": None,
            "inference_child_handshake_begin_at_ms": None,
            "inference_child_handshake_end_at_ms": None,
            "inference_runner_construct_begin_at_ms": None,
            "inference_runner_construct_end_at_ms": None,
            "inference_provider_import_begin_at_ms": None,
            "inference_provider_import_end_at_ms": None,
            "inference_import_onnxruntime_begin_at_ms": None,
            "inference_import_onnxruntime_end_at_ms": None,
            "inference_import_transformers_begin_at_ms": None,
            "inference_import_transformers_end_at_ms": None,
            "inference_model_registry_load_begin_at_ms": None,
            "inference_model_registry_load_end_at_ms": None,
            "inference_network_credential_probe_begin_at_ms": None,
            "inference_network_credential_probe_end_at_ms": None,
            "inference_capability_probe_begin_at_ms": None,
            "inference_capability_probe_end_at_ms": None,
            "inference_hf_cache_lookup_begin_at_ms": None,
            "inference_hf_cache_lookup_end_at_ms": None,
            "inference_onnx_session_begin_at_ms": None,
            "inference_onnx_session_end_at_ms": None,
            "inference_tokenizer_load_begin_at_ms": None,
            "inference_tokenizer_load_end_at_ms": None,
            "inference_runner_initialize_end_at_ms": None,
            "inference_child_ready_at_ms": None,
        }

    @staticmethod
    def _coerce_event_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return False

    @staticmethod
    def _empty_global_init_stage_state(stage_name: str) -> dict[str, Any]:
        return {
            "stage": stage_name,
            "status": "pending",
            "criticality": "",
            "required_before_first_send": False,
            "required_before_first_voice_turn": False,
            "required_before_memory_query": False,
            "required_before_tool_use": False,
            "begin_cumulative_elapsed_ms": None,
            "cumulative_elapsed_ms": None,
            "stage_elapsed_ms": None,
        }

    def _global_init_stage_entry_locked(self, stage_name: str) -> dict[str, Any]:
        normalized_stage = str(stage_name or "").strip() or "unknown"
        entry = self.global_init_stage_state.get(normalized_stage)
        if entry is None:
            entry = self._empty_global_init_stage_state(normalized_stage)
            self.global_init_stage_state[normalized_stage] = entry
            self.global_init_stage_order.append(normalized_stage)
        return entry

    def _update_global_init_stage_metadata_locked(
        self,
        stage_state: dict[str, Any],
        details: dict[str, Any],
    ) -> None:
        if "criticality" in details and details.get("criticality") is not None:
            stage_state["criticality"] = str(details.get("criticality") or "")
        for key in (
            "required_before_first_send",
            "required_before_first_voice_turn",
            "required_before_memory_query",
            "required_before_tool_use",
        ):
            if key in details:
                stage_state[key] = self._coerce_event_bool(details.get(key))

    def _record_global_init_event_locked(
        self,
        stage: str,
        ts_ms: int,
        details: dict[str, Any],
    ) -> None:
        cumulative_elapsed_ms = None
        cumulative_elapsed_raw = details.get("cumulative_elapsed_ms")
        if cumulative_elapsed_raw is not None:
            try:
                cumulative_elapsed_ms = max(0, int(float(cumulative_elapsed_raw)))
            except Exception:
                cumulative_elapsed_ms = None

        if stage == "global_init_begin":
            self.global_init_started_at_ms = ts_ms
            return

        if stage == "semantic_memory_boot_deferred":
            self.semantic_memory_boot_mode = str(details.get("boot_mode") or self.semantic_memory_boot_mode or "deferred")
            self.semantic_memory_warming = True
            self.semantic_memory_ready = False
            return

        if stage == "semantic_memory_warmup_started":
            self.semantic_memory_boot_mode = str(details.get("boot_mode") or self.semantic_memory_boot_mode or "deferred")
            self.semantic_memory_warming = True
            self.semantic_memory_ready = False
            self.semantic_memory_error = ""
            self.semantic_memory_warmup_started_at_ms = ts_ms
            return

        if stage == "semantic_memory_ready":
            self.semantic_memory_boot_mode = str(details.get("boot_mode") or self.semantic_memory_boot_mode or "")
            self.semantic_memory_warming = False
            self.semantic_memory_ready = True
            self.semantic_memory_error = ""
            self.semantic_memory_ready_at_ms = ts_ms
            return

        if stage == "semantic_memory_warmup_failed":
            self.semantic_memory_boot_mode = str(details.get("boot_mode") or self.semantic_memory_boot_mode or "")
            self.semantic_memory_warming = False
            self.semantic_memory_ready = False
            self.semantic_memory_error = str(details.get("error") or details.get("error_type") or "")
            return

        if stage == "semantic_memory_query_degraded":
            self.semantic_memory_query_degraded_count += 1
            return

        if stage == "semantic_memory_add_deferred":
            self.semantic_memory_add_deferred_count += 1
            return

        if stage == "llm_fallback_boot_deferred":
            self.llm_fallback_boot_mode = str(details.get("boot_mode") or self.llm_fallback_boot_mode or "deferred")
            self.llm_fallback_warming = True
            self.llm_fallback_ready = False
            return

        if stage == "llm_fallback_warmup_started":
            self.llm_fallback_boot_mode = str(details.get("boot_mode") or self.llm_fallback_boot_mode or "deferred")
            self.llm_fallback_warming = True
            self.llm_fallback_ready = False
            self.llm_fallback_error = ""
            self.llm_fallback_warmup_started_at_ms = ts_ms
            return

        if stage == "llm_fallback_ready":
            self.llm_fallback_boot_mode = str(details.get("boot_mode") or self.llm_fallback_boot_mode or "")
            self.llm_fallback_warming = False
            self.llm_fallback_ready = True
            self.llm_fallback_error = ""
            self.llm_fallback_ready_at_ms = ts_ms
            return

        if stage == "llm_fallback_warmup_failed":
            self.llm_fallback_boot_mode = str(details.get("boot_mode") or self.llm_fallback_boot_mode or "")
            self.llm_fallback_warming = False
            self.llm_fallback_ready = False
            self.llm_fallback_error = str(details.get("error") or details.get("error_type") or "")
            return

        if stage == "global_init_end":
            self.global_init_completed_at_ms = ts_ms
            if cumulative_elapsed_ms is not None:
                self.global_init_total_ms = cumulative_elapsed_ms
            elif (
                self.global_init_started_at_ms is not None
                and self.global_init_completed_at_ms is not None
            ):
                self.global_init_total_ms = max(
                    0,
                    int(self.global_init_completed_at_ms) - int(self.global_init_started_at_ms),
                )
            return

        if stage not in {"global_init_stage_begin", "global_init_stage_end"}:
            return

        stage_state = self._global_init_stage_entry_locked(details.get("stage_name") or "")
        self._update_global_init_stage_metadata_locked(stage_state, details)

        if stage == "global_init_stage_begin":
            stage_state["status"] = "in_progress"
            if cumulative_elapsed_ms is not None:
                stage_state["begin_cumulative_elapsed_ms"] = cumulative_elapsed_ms
            return

        stage_state["status"] = "completed"
        if cumulative_elapsed_ms is not None:
            stage_state["cumulative_elapsed_ms"] = cumulative_elapsed_ms
        stage_elapsed_ms = None
        stage_elapsed_raw = details.get("stage_elapsed_ms")
        if stage_elapsed_raw is not None:
            try:
                stage_elapsed_ms = max(0, int(float(stage_elapsed_raw)))
            except Exception:
                stage_elapsed_ms = None
        if stage_elapsed_ms is None:
            begin_elapsed_ms = stage_state.get("begin_cumulative_elapsed_ms")
            if begin_elapsed_ms is not None and cumulative_elapsed_ms is not None:
                stage_elapsed_ms = max(0, int(cumulative_elapsed_ms) - int(begin_elapsed_ms))
        stage_state["stage_elapsed_ms"] = stage_elapsed_ms

    @staticmethod
    def _inference_stage_definitions() -> list[tuple[str, str]]:
        return [
            ("inference_runner_registration_begin", "inference_runner_registration_begin_at_ms"),
            ("inference_runner_registration_end", "inference_runner_registration_end_at_ms"),
            ("inference_proc_spawn_begin", "inference_proc_spawn_begin_at_ms"),
            ("inference_proc_spawn_end", "inference_proc_spawn_end_at_ms"),
            ("inference_child_boot_begin", "inference_child_boot_begin_at_ms"),
            ("inference_child_handshake_begin", "inference_child_handshake_begin_at_ms"),
            ("inference_child_handshake_end", "inference_child_handshake_end_at_ms"),
            ("inference_runner_construct_begin", "inference_runner_construct_begin_at_ms"),
            ("inference_runner_construct_end", "inference_runner_construct_end_at_ms"),
            ("inference_provider_import_begin", "inference_provider_import_begin_at_ms"),
            ("inference_provider_import_end", "inference_provider_import_end_at_ms"),
            ("inference_import_onnxruntime_begin", "inference_import_onnxruntime_begin_at_ms"),
            ("inference_import_onnxruntime_end", "inference_import_onnxruntime_end_at_ms"),
            ("inference_import_transformers_begin", "inference_import_transformers_begin_at_ms"),
            ("inference_import_transformers_end", "inference_import_transformers_end_at_ms"),
            ("inference_model_registry_load_begin", "inference_model_registry_load_begin_at_ms"),
            ("inference_model_registry_load_end", "inference_model_registry_load_end_at_ms"),
            ("inference_network_credential_probe_begin", "inference_network_credential_probe_begin_at_ms"),
            ("inference_network_credential_probe_end", "inference_network_credential_probe_end_at_ms"),
            ("inference_capability_probe_begin", "inference_capability_probe_begin_at_ms"),
            ("inference_capability_probe_end", "inference_capability_probe_end_at_ms"),
            ("inference_hf_cache_lookup_begin", "inference_hf_cache_lookup_begin_at_ms"),
            ("inference_hf_cache_lookup_end", "inference_hf_cache_lookup_end_at_ms"),
            ("inference_onnx_session_begin", "inference_onnx_session_begin_at_ms"),
            ("inference_onnx_session_end", "inference_onnx_session_end_at_ms"),
            ("inference_tokenizer_load_begin", "inference_tokenizer_load_begin_at_ms"),
            ("inference_tokenizer_load_end", "inference_tokenizer_load_end_at_ms"),
            ("inference_runner_initialize_end", "inference_runner_initialize_end_at_ms"),
            ("inference_child_ready", "inference_child_ready_at_ms"),
        ]

    @classmethod
    def _empty_worker_attempt_stage_status(cls) -> dict[str, str]:
        return {stage: "pending" for stage, _field in cls._boot_stage_definitions()}

    @classmethod
    def _empty_inference_stage_status(cls) -> dict[str, str]:
        return {stage: "pending" for stage, _field in cls._inference_stage_definitions()}

    @staticmethod
    def _stage_field_names(stage: str) -> tuple[str, ...]:
        stage_map = {
            "credentials_begin": ("credentials_begin_at_ms",),
            "credentials_end": ("credentials_end_at_ms",),
            "server_created": ("server_created_at_ms",),
            "server_run_enter": ("server_run_enter_at_ms", "worker_run_enter_at_ms"),
            "worker_run_enter": ("worker_run_enter_at_ms", "server_run_enter_at_ms"),
            "worker_network_connect_begin": ("worker_network_connect_begin_at_ms",),
            "worker_auth_begin": ("worker_auth_begin_at_ms",),
            "worker_registration_begin": ("worker_registration_begin_at_ms",),
            "plugin_preload_begin": ("plugin_preload_begin_at_ms",),
            "plugin_preload_end": ("plugin_preload_end_at_ms",),
            "inference_executor_start_begin": ("inference_executor_start_begin_at_ms",),
            "inference_executor_start_end": ("inference_executor_start_end_at_ms",),
            "inference_executor_initialize_begin": ("inference_executor_initialize_begin_at_ms",),
            "inference_executor_initialize_end": ("inference_executor_initialize_end_at_ms",),
            "http_server_start_begin": ("http_server_start_begin_at_ms",),
            "http_server_start_end": ("http_server_start_end_at_ms",),
            "proc_pool_start_begin": ("proc_pool_start_begin_at_ms",),
            "proc_pool_start_end": ("proc_pool_start_end_at_ms",),
            "proc_pool_process_created": ("proc_pool_process_created_at_ms",),
            "proc_pool_process_started": ("proc_pool_process_started_at_ms",),
            "proc_pool_process_ready": ("proc_pool_process_ready_at_ms",),
            "worker_conn_task_scheduled": ("worker_conn_task_scheduled_at_ms",),
            "worker_started": ("worker_started_at_ms", "worker_started_event_at_ms"),
            "worker_started_event": ("worker_started_event_at_ms", "worker_started_at_ms"),
            "worker_registered": ("worker_registered_at_ms", "worker_registered_event_at_ms"),
            "worker_registered_event": ("worker_registered_event_at_ms", "worker_registered_at_ms"),
            "worker_heartbeat_first_seen": ("worker_heartbeat_first_seen_at_ms",),
            "claim_probe_sent": ("claim_probe_sent_at_ms",),
            "claim_probe_claimed": ("claim_probe_claimed_at_ms",),
            "claim_probe_passed": ("claim_probe_passed_at_ms",),
            "runtime_ready": ("runtime_ready_at_ms",),
        }
        return stage_map.get(stage, ())

    @staticmethod
    def _inference_stage_field_names(stage: str) -> tuple[str, ...]:
        stage_map = {
            "inference_runner_registration_begin": ("inference_runner_registration_begin_at_ms",),
            "inference_runner_registration_end": ("inference_runner_registration_end_at_ms",),
            "inference_proc_spawn_begin": ("inference_proc_spawn_begin_at_ms",),
            "inference_proc_spawn_end": ("inference_proc_spawn_end_at_ms",),
            "inference_child_boot_begin": ("inference_child_boot_begin_at_ms",),
            "inference_child_handshake_begin": ("inference_child_handshake_begin_at_ms",),
            "inference_child_handshake_end": ("inference_child_handshake_end_at_ms",),
            "inference_runner_construct_begin": ("inference_runner_construct_begin_at_ms",),
            "inference_runner_construct_end": ("inference_runner_construct_end_at_ms",),
            "inference_provider_import_begin": ("inference_provider_import_begin_at_ms",),
            "inference_provider_import_end": ("inference_provider_import_end_at_ms",),
            "inference_import_onnxruntime_begin": ("inference_import_onnxruntime_begin_at_ms",),
            "inference_import_onnxruntime_end": ("inference_import_onnxruntime_end_at_ms",),
            "inference_import_transformers_begin": ("inference_import_transformers_begin_at_ms",),
            "inference_import_transformers_end": ("inference_import_transformers_end_at_ms",),
            "inference_model_registry_load_begin": ("inference_model_registry_load_begin_at_ms",),
            "inference_model_registry_load_end": ("inference_model_registry_load_end_at_ms",),
            "inference_network_credential_probe_begin": ("inference_network_credential_probe_begin_at_ms",),
            "inference_network_credential_probe_end": ("inference_network_credential_probe_end_at_ms",),
            "inference_capability_probe_begin": ("inference_capability_probe_begin_at_ms",),
            "inference_capability_probe_end": ("inference_capability_probe_end_at_ms",),
            "inference_hf_cache_lookup_begin": ("inference_hf_cache_lookup_begin_at_ms",),
            "inference_hf_cache_lookup_end": ("inference_hf_cache_lookup_end_at_ms",),
            "inference_onnx_session_begin": ("inference_onnx_session_begin_at_ms",),
            "inference_onnx_session_end": ("inference_onnx_session_end_at_ms",),
            "inference_tokenizer_load_begin": ("inference_tokenizer_load_begin_at_ms",),
            "inference_tokenizer_load_end": ("inference_tokenizer_load_end_at_ms",),
            "inference_runner_initialize_end": ("inference_runner_initialize_end_at_ms",),
            "inference_child_ready": ("inference_child_ready_at_ms",),
        }
        return stage_map.get(stage, ())

    def _mark_worker_attempt_stage_locked(self, stage: str, at_ms: int) -> None:
        field_names = self._stage_field_names(stage)
        if not field_names:
            return
        for field_name in field_names:
            self.worker_attempt_timing_ms[field_name] = at_ms
        if stage == "server_run_enter":
            self.worker_attempt_stage_status["worker_run_enter"] = "done"
        elif stage == "worker_started":
            self.worker_attempt_stage_status["worker_started_event"] = "done"
        elif stage == "worker_registered":
            self.worker_attempt_stage_status["worker_registered_event"] = "done"
        else:
            self.worker_attempt_stage_status[stage] = "done"

    def _mark_inference_stage_locked(
        self,
        stage: str,
        *,
        at_ms: int,
        runner_name: str = "",
    ) -> None:
        field_names = self._inference_stage_field_names(stage)
        if not field_names:
            return
        for field_name in field_names:
            self.inference_stage_timing_ms[field_name] = at_ms
        if stage in self.inference_stage_status:
            self.inference_stage_status[stage] = "done"
        normalized_runner_name = str(runner_name or "").strip()
        if normalized_runner_name:
            if normalized_runner_name not in self.inference_runner_names:
                self.inference_runner_names.append(normalized_runner_name)
                self.inference_runner_names.sort()
            runner_timing = self.inference_runner_timing_ms.setdefault(
                normalized_runner_name,
                self._empty_inference_stage_timing(),
            )
            for field_name in field_names:
                runner_timing[field_name] = at_ms

    def _mark_inference_stage_skipped_locked(
        self,
        stage: str,
        *,
        reason: str,
        runner_name: str = "",
    ) -> None:
        if stage in self.inference_stage_status:
            self.inference_stage_status[stage] = "skipped"
        normalized_runner_name = str(runner_name or "").strip()
        if normalized_runner_name:
            if normalized_runner_name not in self.inference_runner_names:
                self.inference_runner_names.append(normalized_runner_name)
                self.inference_runner_names.sort()
            runner_status = self.inference_runner_timing_ms.setdefault(
                normalized_runner_name,
                self._empty_inference_stage_timing(),
            )
            _ = runner_status
        self._emit_boot_event(
            "inference_stage_skipped",
            {"stage_name": stage, "reason": reason, "runner_name": normalized_runner_name},
        )

    def _emit_boot_event(self, stage: str, details: dict[str, Any] | None = None) -> None:
        if not self.timeline_enabled:
            return
        payload = {
            "cycle_id": self.cycle_id,
            "stage": stage,
            "timestamp_ms": int(time.time() * 1000),
            "elapsed_ms_since_boot": max(0, int(time.time() * 1000) - self.boot_started_at_ms),
            "state": self.state.value,
            "details": details or {},
        }
        path = Path(self.boot_events_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def start_cycle(self, *, mode: str, version: str) -> None:
        with self._lock:
            self.state = ReadinessState.BOOTING
            self.boot_started_at_ms = int(time.time() * 1000)
            self.cycle_id = uuid.uuid4().hex[:12]
            self.api_up = True
            self.token_server_up = False
            self.worker_connected = False
            self.dispatch_pipeline_ready = False
            self.capability_init_started = False
            self.capability_ready = False
            self.capability_failure_reason = None
            self.last_claim_probe_ok = False
            self.idle_process_ready = False
            self.last_claim_probe_at_ms = None
            self.last_claim_probe_error = None
            self.claim_probe_started_at_ms = None
            self.claim_probe_claimed_at_ms = None
            self.claimable_ready_at_ms = None
            self.idle_process_ready_at_ms = None
            self.claim_probe_room_name = None
            self.claim_probe_stage = None
            self.claim_probe_status = None
            self.claim_probe_timeout_budget_ms = None
            self.claim_probe_failure_reason = None
            self.infra_ready_at_ms = None
            self.fatal_startup_fault = False
            self.last_worker_heartbeat_ms = 0
            self.first_worker_heartbeat_seen = False
            self.core_ready_at_ms = None
            self.worker_connect_stage = "idle"
            self.worker_connect_attempt = 0
            self.active_worker_attempt = ""
            self.last_invalidated_worker_attempt = ""
            self.worker_connect_started_at_ms = None
            self.worker_conn_task_started_at_ms = None
            self.worker_connected_at_ms = None
            self.worker_registered_at_ms = None
            self.worker_connect_error_at_ms = None
            self.worker_connect_error_type = None
            self.worker_connect_error_message = None
            self.worker_connect_timeout_reason = None
            self.worker_connect_retry_reason = None
            self.worker_connect_error_stage = None
            self.worker_attempt_timing_ms = self._empty_worker_attempt_timing()
            self.worker_attempt_stage_status = self._empty_worker_attempt_stage_status()
            self.inference_stage_timing_ms = self._empty_inference_stage_timing()
            self.inference_stage_status = self._empty_inference_stage_status()
            self.inference_runner_timing_ms = {}
            self.inference_runner_names = []
            self.stale_worker_started_count = 0
            self.stale_worker_registered_count = 0
            self.stale_worker_claim_count = 0
            self.late_active_worker_registered_count = 0
            self.last_stale_callback_ms = None
            self.last_late_active_callback_ms = None
            self.last_worker_claim_at_ms = None
            self.last_room_joined_at_ms = None
            self.last_session_started_at_ms = None
            self.last_session_ready_at_ms = None
            self.last_session_failure_at_ms = None
            self.last_session_failure_reason = None
            self.last_worker_disconnect_at_ms = None
            self.active_session_count = 0
            self.enhanced_turn_detection_ready = False
            self.enhanced_turn_detection_mode = ""
            self.eou_registration_state = "idle"
            self.eou_registration_error = ""
            self.eou_init_thread_handoff_count = 0
            self.eou_init_main_thread_success = 0
            self.eou_init_main_thread_fail = 0
            self.eou_upgrade_success = 0
            self.onnx_init_state = "idle"
            self.onnx_init_error = ""
            self.onnx_init_started_at_ms = None
            self.onnx_background_ready_at_ms = None
            self.onnx_first_use_wait_ms = None
            self.sessions_started_on_stt = 0
            self.sessions_upgraded_to_eou = 0
            self.sessions_completed_without_eou = 0
            self.upgrade_failures = 0
            self.turn_detection_upgrade_durations_ms = []
            self.capability_init_started_at_ms = None
            self.capability_ready_at_ms = None
            self.global_init_started_at_ms = None
            self.global_init_completed_at_ms = None
            self.global_init_total_ms = None
            self.global_init_stage_order = []
            self.global_init_stage_state = {}
            self.semantic_memory_ready = False
            self.semantic_memory_warming = False
            self.semantic_memory_boot_mode = ""
            self.semantic_memory_error = ""
            self.semantic_memory_warmup_started_at_ms = None
            self.semantic_memory_ready_at_ms = None
            self.semantic_memory_query_degraded_count = 0
            self.semantic_memory_add_deferred_count = 0
            self.llm_fallback_ready = False
            self.llm_fallback_warming = False
            self.llm_fallback_boot_mode = ""
            self.llm_fallback_error = ""
            self.llm_fallback_warmup_started_at_ms = None
            self.llm_fallback_ready_at_ms = None
            self.last_transition_ms = int(time.time() * 1000)
            self.mode = mode
            self.version = version
            self._room_stage_by_room = {}
            path = Path(self.boot_events_path)
            try:
                self._boot_events_synced_offset = path.stat().st_size
            except FileNotFoundError:
                self._boot_events_synced_offset = 0
            self._emit_boot_event("api_started", {"mode": mode, "version": version})

    def transition(self, new_state: ReadinessState, *, reason: str) -> None:
        with self._lock:
            if self.state == new_state:
                return
            self.state = new_state
            self.last_transition_ms = int(time.time() * 1000)
            self._emit_boot_event("state_transition", {"to": new_state.value, "reason": reason})

    def mark_token_server_started(self, *, host: str, port: int) -> None:
        with self._lock:
            self.token_server_up = True
            self._emit_boot_event("token_server_started", {"host": host, "port": port})
            if self.state == ReadinessState.BOOTING:
                self.transition(ReadinessState.TOKEN_READY, reason="token_server_started")

    def record_boot_event(self, stage: str, **details: Any) -> None:
        with self._lock:
            if not self.timeline_enabled:
                now_ms = int(time.time() * 1000)
                payload = {
                    "cycle_id": self.cycle_id,
                    "stage": stage,
                    "timestamp_ms": now_ms,
                    "elapsed_ms_since_boot": max(0, now_ms - self.boot_started_at_ms),
                    "state": self.state.value,
                    "details": details,
                }
                path = Path(self.boot_events_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
                self._sync_boot_events_locked()
                return
            self._emit_boot_event(stage, details)

    def mark_capability_init_started(self, *, source: str) -> None:
        with self._lock:
            if not self.capability_init_started:
                self.capability_init_started = True
                self.capability_init_started_at_ms = int(time.time() * 1000)
                self.capability_failure_reason = None
                self._emit_boot_event("capability_init_started", {"source": source})
            if self.state == ReadinessState.TOKEN_READY:
                self.transition(ReadinessState.CAPABILITY_INITIALIZING, reason="capability_init_started")

    def mark_worker_bootstrapping(self, **details: Any) -> None:
        with self._lock:
            self._emit_boot_event("worker_bootstrap_called", details)

    def mark_worker_connecting(self, **details: Any) -> None:
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.worker_connected = False
            self.worker_connect_stage = "idle"
            self.worker_connect_attempt += 1
            self.active_worker_attempt = str(details.get("worker_attempt_id") or "")
            self.worker_connect_started_at_ms = now_ms
            self.worker_conn_task_started_at_ms = None
            self.worker_connected_at_ms = None
            self.worker_registered_at_ms = None
            self.worker_connect_error_at_ms = None
            self.worker_connect_error_type = None
            self.worker_connect_error_message = None
            self.worker_connect_timeout_reason = None
            self.worker_connect_retry_reason = None
            self.worker_connect_error_stage = None
            self.worker_attempt_timing_ms = self._empty_worker_attempt_timing()
            self.worker_attempt_stage_status = self._empty_worker_attempt_stage_status()
            self.inference_stage_timing_ms = self._empty_inference_stage_timing()
            self.inference_stage_status = self._empty_inference_stage_status()
            self.inference_runner_timing_ms = {}
            self.inference_runner_names = []
            self.worker_attempt_timing_ms["attempt_started_at_ms"] = now_ms
            self._emit_boot_event("worker_connect_attempt_started", details)
            self.transition(ReadinessState.WORKER_CONNECTING, reason="worker_connect_attempt_started")

    def mark_worker_connected(self, **details: Any) -> None:
        with self._lock:
            now_ms = int(time.time() * 1000)
            self.worker_connect_stage = "conn_task_started"
            if details.get("worker_attempt_id"):
                self.active_worker_attempt = str(details.get("worker_attempt_id") or "")
            self.worker_conn_task_started_at_ms = now_ms
            self._mark_worker_attempt_stage_locked("worker_started_event", now_ms)
            self.worker_connected = False
            self._emit_boot_event("worker_conn_task_started", details)
            self._emit_boot_event("worker_started_event", details)

    def mark_worker_registered(self, **details: Any) -> None:
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.worker_connected = True
            self.worker_connected_at_ms = now_ms
            self.worker_registered_at_ms = now_ms
            self.worker_connect_stage = "registered"
            self.active_worker_attempt = str(details.get("worker_attempt_id") or self.active_worker_attempt or "")
            self._mark_worker_attempt_stage_locked("worker_registered_event", now_ms)
            self.worker_connect_error_at_ms = None
            self.worker_connect_error_type = None
            self.worker_connect_error_message = None
            self.worker_connect_timeout_reason = None
            self.worker_connect_retry_reason = None
            self.worker_connect_error_stage = None
            self.last_worker_heartbeat_ms = now_ms
            self._emit_boot_event("worker_registered", details)
            self._emit_boot_event("readiness_worker_registered_with_livekit", details)
            if not self.fatal_startup_fault and self.token_server_up:
                self._declare_infra_ready_locked(now_ms)

    def mark_worker_attempt_stage(self, stage: str, *, worker_attempt_id: str, at_ms: int | None = None) -> None:
        field_names = self._stage_field_names(stage)
        if not field_names:
            return
        with self._lock:
            if self.active_worker_attempt != str(worker_attempt_id or ""):
                return
            self._mark_worker_attempt_stage_locked(stage, at_ms or int(time.time() * 1000))

    def mark_worker_attempt_stage_skipped(
        self,
        stage: str,
        *,
        worker_attempt_id: str,
        reason: str,
    ) -> None:
        with self._lock:
            if self.active_worker_attempt != str(worker_attempt_id or ""):
                return
            if stage in self.worker_attempt_stage_status:
                self.worker_attempt_stage_status[stage] = "skipped"
                self._emit_boot_event(
                    "worker_attempt_stage_skipped",
                    {
                        "worker_attempt_id": worker_attempt_id,
                        "stage": stage,
                        "reason": reason,
                    },
                )

    def mark_worker_attempt_invalidated(
        self,
        *,
        worker_attempt_id: str,
        reason: str,
        at_ms: int | None = None,
        **details: Any,
    ) -> None:
        with self._lock:
            now_ms = at_ms or int(time.time() * 1000)
            self.last_invalidated_worker_attempt = str(worker_attempt_id or "")
            if self.active_worker_attempt == worker_attempt_id:
                self.active_worker_attempt = ""
            self.worker_connected = False
            self.worker_connect_stage = "failed"
            payload = {
                "worker_attempt_id": worker_attempt_id,
                "reason": reason,
            }
            payload.update(details)
            self._emit_boot_event("worker_attempt_invalidated", payload)
            self.transition(ReadinessState.FAILED, reason="worker_attempt_invalidated")

    def mark_stale_worker_callback(
        self,
        *,
        stage: str,
        worker_attempt_id: str,
        late_ms: int | None = None,
        **details: Any,
    ) -> None:
        with self._lock:
            now_ms = int(time.time() * 1000)
            self.last_stale_callback_ms = now_ms
            if stage == "worker_started":
                self.stale_worker_started_count += 1
            elif stage == "worker_registered":
                self.stale_worker_registered_count += 1
            else:
                self.stale_worker_claim_count += 1
            payload = {
                "worker_attempt_id": worker_attempt_id,
                "late_ms": late_ms or 0,
            }
            payload.update(details)
            self._emit_boot_event(f"stale_{stage}_ignored", payload)

    def mark_late_active_worker_registered(
        self,
        *,
        worker_attempt_id: str,
        late_ms: int,
        **details: Any,
    ) -> None:
        with self._lock:
            self.late_active_worker_registered_count += 1
            self.last_late_active_callback_ms = int(time.time() * 1000)
            payload = {
                "worker_attempt_id": worker_attempt_id,
                "late_ms": late_ms,
            }
            payload.update(details)
            self._emit_boot_event("late_active_worker_registered", payload)

    def mark_worker_disconnected(self, *, reason: str) -> None:
        with self._lock:
            self.worker_connected = False
            self.last_worker_disconnect_at_ms = int(time.time() * 1000)
            self.active_session_count = 0
            self._invalidate_claim_probe_locked(reason=reason, emit_event=True)
            self._emit_boot_event("worker_disconnected", {"reason": reason})
            if self.fatal_startup_fault:
                self.transition(ReadinessState.FAILED, reason="fatal_startup_fault")
            elif self._worker_connect_error_active_locked():
                self.transition(ReadinessState.FAILED, reason="worker_connect_error")
            else:
                fallback_state = ReadinessState.TOKEN_READY if self.token_server_up else ReadinessState.BOOTING
                self.transition(fallback_state, reason="worker_disconnected")

    def mark_worker_heartbeat(self) -> None:
        with self._lock:
            self.last_worker_heartbeat_ms = int(time.time() * 1000)
            if not self.first_worker_heartbeat_seen:
                self.first_worker_heartbeat_seen = True
                self._mark_worker_attempt_stage_locked("worker_heartbeat_first_seen", self.last_worker_heartbeat_ms)
                self._emit_boot_event("worker_heartbeat_first_seen", {})

    def mark_worker_connect_timeout(self, **details: Any) -> None:
        with self._lock:
            timeout_reason = details.get("timeout_reason")
            if timeout_reason is not None:
                self.worker_connect_timeout_reason = str(timeout_reason or "")
            connect_phase = details.get("connect_phase")
            if connect_phase is not None:
                self.worker_connect_error_stage = str(connect_phase or "")
            self._emit_boot_event("worker_connect_timeout", details)

    def mark_worker_connect_error(
        self,
        *,
        exception_type: str,
        exception_message: str,
        **details: Any,
    ) -> None:
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.worker_connected = False
            self.worker_connect_stage = "failed"
            self.worker_connect_error_at_ms = now_ms
            self.worker_connect_error_type = exception_type
            self.worker_connect_error_message = exception_message
            retry_reason = details.get("retry_reason")
            if retry_reason is not None:
                self.worker_connect_retry_reason = str(retry_reason or "")
            connect_phase = details.get("connect_phase")
            if connect_phase is not None:
                self.worker_connect_error_stage = str(connect_phase or "")
            payload = {
                "exception_type": exception_type,
                "exception_message": exception_message,
            }
            payload.update(details)
            self._emit_boot_event("worker_connect_error", payload)
            self.transition(ReadinessState.FAILED, reason="worker_connect_error")

    def mark_worker_run_returned(self, **details: Any) -> None:
        with self._lock:
            self._emit_boot_event("worker_run_returned", details)

    def mark_worker_run_exception(self, **details: Any) -> None:
        with self._lock:
            self._emit_boot_event("worker_run_exception", details)

    def mark_worker_exception_type(self, exception_type: str, **details: Any) -> None:
        with self._lock:
            payload = {"exception_type": exception_type}
            payload.update(details)
            self._emit_boot_event("worker_exception_type", payload)

    def mark_dispatch_pipeline_ready(self, *, source: str) -> None:
        with self._lock:
            self.dispatch_pipeline_ready = True
            self._emit_boot_event("dispatch_pipeline_ready", {"source": source})

    def mark_claim_probe_started(self, *, room_name: str, reason: str) -> None:
        with self._lock:
            self.claim_probe_started_at_ms = int(time.time() * 1000)
            self.worker_attempt_timing_ms["claim_probe_sent_at_ms"] = self.claim_probe_started_at_ms
            self.claim_probe_claimed_at_ms = None
            self.claim_probe_room_name = room_name
            self.claim_probe_stage = "claim_probe_started"
            self.claim_probe_status = "running"
            self.claim_probe_timeout_budget_ms = None
            self.claim_probe_failure_reason = None
            self._emit_boot_event("claim_probe_started", {"room_name": room_name, "reason": reason})

    def mark_claim_probe_stage(
        self,
        *,
        room_name: str,
        stage: str,
        status: str = "running",
        timeout_budget_ms: int | None = None,
    ) -> None:
        with self._lock:
            self.claim_probe_room_name = room_name
            self.claim_probe_stage = stage
            self.claim_probe_status = status
            if timeout_budget_ms is not None:
                self.claim_probe_timeout_budget_ms = timeout_budget_ms

    def mark_claim_probe_claimed(self, *, room_name: str) -> None:
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.claim_probe_room_name = room_name
            self.claim_probe_claimed_at_ms = now_ms
            self.worker_attempt_timing_ms["claim_probe_claimed_at_ms"] = now_ms
            self.claim_probe_stage = "worker_job_claimed"
            self.claim_probe_status = "claimed"
            self.claim_probe_failure_reason = None

    def mark_claim_probe_passed(self, *, room_name: str, participant_count: int | None = None) -> None:
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.last_claim_probe_ok = True
            self.last_claim_probe_at_ms = now_ms
            self.worker_attempt_timing_ms["claim_probe_passed_at_ms"] = now_ms
            self.last_claim_probe_error = None
            self.claim_probe_room_name = room_name
            self.claim_probe_stage = "claim_probe_passed"
            self.claim_probe_status = "passed"
            self.claim_probe_failure_reason = None
            if self.claimable_ready_at_ms is None:
                self.claimable_ready_at_ms = now_ms
            self._emit_boot_event(
                "claim_probe_passed",
                {"room_name": room_name, "participant_count": participant_count},
            )
            if self._session_capable_ready_locked(now_ms):
                if self.core_ready_at_ms is None:
                    self.core_ready_at_ms = now_ms
                    self.worker_attempt_timing_ms["runtime_ready_at_ms"] = now_ms
                    self._emit_boot_event("ready_core_declared", {"reason": "claim_probe_passed"})
                if self.capability_ready:
                    self.transition(ReadinessState.READY_CAPABILITY, reason="claim_probe_passed")
                else:
                    self.transition(ReadinessState.READY_SESSION_CAPABLE, reason="claim_probe_passed")

    def mark_claim_probe_failed(
        self,
        *,
        reason: str,
        room_name: str | None = None,
        stage: str = "claim_probe_failed",
        timeout_budget_ms: int | None = None,
    ) -> None:
        with self._lock:
            self.last_claim_probe_ok = False
            self.last_claim_probe_at_ms = int(time.time() * 1000)
            self.last_claim_probe_error = reason
            self.claim_probe_room_name = room_name
            self.claim_probe_stage = stage
            self.claim_probe_status = "failed"
            self.claim_probe_failure_reason = reason
            if timeout_budget_ms is not None:
                self.claim_probe_timeout_budget_ms = timeout_budget_ms
            self._emit_boot_event(
                "claim_probe_failed",
                {"reason": reason, "room_name": room_name or ""},
            )

    def mark_claim_probe_invalidated(self, *, reason: str) -> None:
        with self._lock:
            self._invalidate_claim_probe_locked(reason=reason, emit_event=True)

    def mark_capability_ready(self) -> None:
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.capability_init_started = True
            self.capability_ready = True
            self.capability_failure_reason = None
            if self.capability_ready_at_ms is None:
                self.capability_ready_at_ms = now_ms
                self._emit_boot_event("capability_ready_declared", {})
            if self._session_capable_ready_locked(now_ms):
                self.transition(ReadinessState.READY_CAPABILITY, reason="capability_ready")

    def mark_capability_failed(self, *, reason: str) -> None:
        with self._lock:
            self.capability_init_started = True
            self.capability_ready = False
            self.capability_failure_reason = reason
            self._emit_boot_event("capability_init_failed", {"reason": reason})

    def mark_fatal_startup_fault(self, *, reason: str) -> None:
        with self._lock:
            self.fatal_startup_fault = True
            self._invalidate_claim_probe_locked(reason=reason, emit_event=False)
            self._emit_boot_event("fatal_startup_fault", {"reason": reason})
            self.transition(ReadinessState.FAILED, reason=reason)

    def mark_first_token_issued(self, *, room_name: str) -> None:
        with self._lock:
            self._emit_boot_event("first_token_issued", {"room": room_name})

    def mark_dispatch_created(self, *, room_name: str, agent_name: str) -> None:
        with self._lock:
            self._emit_boot_event("dispatch_created", {"room": room_name, "agent_name": agent_name})

    def mark_first_session_ready(self, *, room_name: str) -> None:
        with self._lock:
            self._emit_boot_event("room_session_ready", {"room": room_name})
            self._emit_boot_event("first_session_ready", {"room": room_name})

    def mark_enhanced_turn_detection_pending(
        self,
        *,
        requested_mode: str,
        active_mode: str,
        fallback_reason: str,
        **details: Any,
    ) -> None:
        with self._lock:
            self.enhanced_turn_detection_ready = False
            self.enhanced_turn_detection_mode = str(active_mode or "")
            payload = {
                "requested_mode": requested_mode,
                "active_mode": active_mode,
                "fallback_reason": fallback_reason,
            }
            payload.update(details)
            self._emit_boot_event("turn_detection_background_pending", payload)

    def mark_eou_init_thread_handoff(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.eou_init_thread_handoff_count += 1
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("eou_init_thread_handoff", payload)

    def mark_eou_registration_started(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.eou_registration_state = "starting"
            self.eou_registration_error = ""
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("eou_registration_started", payload)

    def mark_eou_registration_reused_inflight(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.eou_registration_state = "starting"
            self.eou_registration_error = ""
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("eou_registration_reused_inflight", payload)

    def mark_eou_registration_reused_cached(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.eou_registration_state = "ready"
            self.eou_registration_error = ""
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("eou_registration_reused_cached", payload)

    def mark_eou_registration_completed(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.eou_registration_state = "ready"
            self.eou_registration_error = ""
            self.eou_init_main_thread_success += 1
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("eou_registration_completed", payload)

    def mark_eou_registration_failed(self, *, error: str, mode: str = "", **details: Any) -> None:
        with self._lock:
            self.eou_registration_state = "failed"
            self.eou_registration_error = str(error or "")
            self.eou_init_main_thread_fail += 1
            payload = {"mode": mode, "error": error}
            payload.update(details)
            self._emit_boot_event("eou_registration_failed", payload)

    def mark_onnx_init_started(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.onnx_init_state = "starting"
            self.onnx_init_error = ""
            self.onnx_init_started_at_ms = int(time.time() * 1000)
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("onnx_init_started", payload)

    def mark_onnx_init_reused_inflight(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("onnx_init_reused_inflight", payload)

    def mark_onnx_init_reused_cached(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("onnx_init_reused_cached", payload)

    def mark_onnx_init_completed(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.enhanced_turn_detection_ready = True
            self.enhanced_turn_detection_mode = str(mode or "")
            self.onnx_init_state = "ready"
            self.onnx_init_error = ""
            self.onnx_background_ready_at_ms = int(time.time() * 1000)
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("onnx_init_completed", payload)

    def mark_onnx_init_failed(self, *, error: str, mode: str = "", **details: Any) -> None:
        with self._lock:
            self.enhanced_turn_detection_ready = False
            self.onnx_init_state = "failed"
            self.onnx_init_error = str(error or "")
            payload = {"mode": mode, "error": error}
            payload.update(details)
            self._emit_boot_event("onnx_init_failed", payload)

    def mark_session_started_on_stt(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.sessions_started_on_stt += 1
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("session_started_on_stt", payload)

    def mark_turn_detection_upgrade_deferred_busy(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("turn_detection_upgrade_deferred_busy", payload)

    def mark_turn_detection_upgrade_success(self, *, wait_ms: int, mode: str = "", **details: Any) -> None:
        with self._lock:
            duration_ms = max(0, int(wait_ms))
            self.enhanced_turn_detection_ready = True
            if mode:
                self.enhanced_turn_detection_mode = str(mode)
            self.sessions_upgraded_to_eou += 1
            self.eou_upgrade_success += 1
            self.turn_detection_upgrade_durations_ms.append(duration_ms)
            payload = {"mode": mode, "wait_ms": duration_ms}
            payload.update(details)
            self._emit_boot_event("turn_detection_upgraded_to_eou", payload)

    def mark_turn_detection_upgrade_failed(self, *, error: str, mode: str = "", **details: Any) -> None:
        with self._lock:
            self.upgrade_failures += 1
            payload = {"mode": mode, "error": error}
            payload.update(details)
            self._emit_boot_event("turn_detection_upgrade_failed", payload)

    def mark_session_completed_without_eou(self, *, mode: str, **details: Any) -> None:
        with self._lock:
            self.sessions_completed_without_eou += 1
            payload = {"mode": mode}
            payload.update(details)
            self._emit_boot_event("session_completed_without_eou", payload)

    def mark_bootstrap_complete(self, *, ok: bool, details: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._emit_boot_event("bootstrap_complete", {"ok": ok, **(details or {})})

    def _claim_probe_ttl_ms(self) -> int:
        raw = str(os.getenv("MAYA_CLAIM_PROBE_TTL_MS", "30000") or "30000").strip()
        try:
            return max(1, int(raw))
        except Exception:
            return 30000

    def _claim_probe_min_interval_ms(self) -> int:
        raw = str(os.getenv("MAYA_CLAIM_PROBE_MIN_INTERVAL_MS", "10000") or "10000").strip()
        try:
            return max(0, int(raw))
        except Exception:
            return 10000

    def _worker_alive_locked(self, now_ms: int) -> tuple[bool, int | None]:
        ttl_ms = int(float(os.getenv("MAYA_WORKER_HEARTBEAT_TTL_MS", "45000")))
        heartbeat_age_ms = max(0, now_ms - self.last_worker_heartbeat_ms) if self.last_worker_heartbeat_ms else None
        worker_heartbeat_fresh = bool(
            self.worker_connected
            and self.last_worker_heartbeat_ms
            and heartbeat_age_ms is not None
            and heartbeat_age_ms <= ttl_ms
        )
        return worker_heartbeat_fresh, heartbeat_age_ms

    def _infra_ready_locked(self, now_ms: int) -> bool:
        worker_heartbeat_fresh, _ = self._worker_alive_locked(now_ms)
        return bool(
            self.api_up
            and self.token_server_up
            and worker_heartbeat_fresh
            and not self.fatal_startup_fault
        )

    def _claim_probe_valid_locked(self, now_ms: int) -> tuple[bool, int | None]:
        if not self.last_claim_probe_ok or self.last_claim_probe_at_ms is None:
            return False, None
        age_ms = max(0, now_ms - self.last_claim_probe_at_ms)
        if age_ms > self._claim_probe_ttl_ms():
            return False, age_ms
        return True, age_ms

    def _session_subsystem_healthy_locked(self, now_ms: int) -> bool:
        if self.fatal_startup_fault:
            return False
        if self.last_session_failure_at_ms is None:
            return True
        if self.worker_connected_at_ms is not None and self.last_session_failure_at_ms < self.worker_connected_at_ms:
            return True
        if self.last_session_ready_at_ms is not None and self.last_session_ready_at_ms >= self.last_session_failure_at_ms:
            return True
        return False

    def _worker_connect_error_active_locked(self) -> bool:
        if self.worker_connect_error_at_ms is None:
            return False
        if self.worker_registered_at_ms is None:
            return True
        return self.worker_connect_error_at_ms >= self.worker_registered_at_ms

    def _session_capable_ready_locked(self, now_ms: int) -> bool:
        claim_probe_valid, _ = self._claim_probe_valid_locked(now_ms)
        dispatch_claimable_ready = claim_probe_valid or self.idle_process_ready
        return bool(
            self._infra_ready_locked(now_ms)
            and self.dispatch_pipeline_ready
            and dispatch_claimable_ready
            and self._session_subsystem_healthy_locked(now_ms)
        )

    def _declare_infra_ready_locked(self, now_ms: int) -> None:
        if self.infra_ready_at_ms is None:
            self.infra_ready_at_ms = now_ms
            self._emit_boot_event("infra_ready_declared", {})
        if self._session_capable_ready_locked(now_ms):
            if self.core_ready_at_ms is None:
                self.core_ready_at_ms = now_ms
                self.worker_attempt_timing_ms["runtime_ready_at_ms"] = now_ms
                self._emit_boot_event("ready_core_declared", {"reason": "session_capable"})
            self.transition(ReadinessState.READY_SESSION_CAPABLE, reason="session_capable")
        else:
            self.transition(ReadinessState.READY_INFRA, reason="infra_ready")

    def _invalidate_claim_probe_locked(self, *, reason: str, emit_event: bool) -> None:
        self.last_claim_probe_ok = False
        self.last_claim_probe_error = reason
        self.claim_probe_stage = "claim_probe_invalidated"
        self.claim_probe_status = "invalidated"
        self.claim_probe_failure_reason = reason
        if emit_event:
            self._emit_boot_event("claim_probe_invalidated", {"reason": reason})

    def claim_probe_valid(self) -> bool:
        with self._lock:
            return self._claim_probe_valid_locked(int(time.time() * 1000))[0]

    def claim_probe_needs_refresh(self) -> bool:
        now_ms = int(time.time() * 1000)
        with self._lock:
            if not self._infra_ready_locked(now_ms):
                return False
            if (
                self.claim_probe_started_at_ms is not None
                and (now_ms - self.claim_probe_started_at_ms) < self._claim_probe_min_interval_ms()
            ):
                return False
            valid, _ = self._claim_probe_valid_locked(now_ms)
            return not valid

    def _sync_boot_events_locked(self) -> None:
        path = Path(self.boot_events_path)
        if not path.exists():
            return
        try:
            file_size = path.stat().st_size
        except FileNotFoundError:
            return
        if self._boot_events_synced_offset > file_size:
            self._boot_events_synced_offset = 0
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(self._boot_events_synced_offset)
            lines = handle.readlines()
            self._boot_events_synced_offset = handle.tell()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if not isinstance(item, dict):
                continue
            stage = str(item.get("stage") or "")
            ts_ms = int(item.get("timestamp_ms") or 0)
            details = item.get("details")
            if not isinstance(details, dict):
                details = {}
            item_cycle_id = str(item.get("cycle_id") or "")
            dispatch_cycle_id = str(details.get("dispatch_cycle_id") or "")
            if item_cycle_id != self.cycle_id and dispatch_cycle_id != self.cycle_id:
                continue
            source = str(details.get("source") or "")
            room_name = str(details.get("room") or details.get("room_name") or "")
            event_attempt_id = str(
                details.get("worker_attempt_id")
                or details.get("session_owner_attempt_id")
                or details.get("room_owner_attempt_id")
                or ""
            )
            if stage == "worker_disconnected":
                self.last_worker_disconnect_at_ms = ts_ms
                self.active_session_count = 0
                continue
            if source == "worker_prewarm" and stage == "worker_prewarm_complete":
                self.idle_process_ready = True
                if self.idle_process_ready_at_ms is None:
                    self.idle_process_ready_at_ms = ts_ms
                if self.claimable_ready_at_ms is None:
                    self.claimable_ready_at_ms = ts_ms
                continue
            if source == "global_agent":
                self._record_global_init_event_locked(stage, ts_ms, details)
                continue
            if source == "inference_runner":
                if event_attempt_id and event_attempt_id != self.active_worker_attempt:
                    continue
                runner_name = str(details.get("runner_name") or "")
                if stage == "inference_stage_skipped":
                    stage_name = str(details.get("stage_name") or "")
                    if stage_name in self.inference_stage_status:
                        self.inference_stage_status[stage_name] = "skipped"
                        if runner_name:
                            if runner_name not in self.inference_runner_names:
                                self.inference_runner_names.append(runner_name)
                                self.inference_runner_names.sort()
                            self.inference_runner_timing_ms.setdefault(
                                runner_name,
                                self._empty_inference_stage_timing(),
                            )
                    continue
                if self._inference_stage_field_names(stage):
                    self._mark_inference_stage_locked(
                        stage,
                        at_ms=ts_ms,
                        runner_name=runner_name,
                    )
                continue
            if source != "worker_session" or not room_name:
                continue
            if event_attempt_id and event_attempt_id != self.active_worker_attempt:
                continue
            room_state = self._room_stage_by_room.setdefault(
                room_name,
                {
                    "room": room_name,
                    "listener_attach_ts_ms": None,
                    "participant_visible_ts_ms": None,
                    "track_published_ts_ms": None,
                    "track_subscribed_emit_ts_ms": None,
                    "track_subscribed_consume_ts_ms": None,
                    "startup_gate_classification": "",
                    "teardown_begin_ts_ms": None,
                    "teardown_ipc_closed_ts_ms": None,
                },
            )

            def _apply_lineage_details(*, mark_seen: bool = False) -> None:
                path_precedence = {
                    "": 0,
                    "attached": 1,
                    "received": 2,
                    "processed": 3,
                    "emitted": 4,
                    "fired": 5,
                    "discarded": 5,
                    "path_miss": 5,
                    "registered_but_no_active_source": 5,
                    "replaced": 5,
                    "replaced_after_registration": 5,
                }
                lineage_keys = (
                    "active_room_io_id",
                    "active_audio_output_id",
                    "attached_callback_target_id",
                    "callback_fired_source_id",
                    "callback_processed_source_id",
                    "callback_emitted_source_id",
                    "callback_discard_reason",
                    "lineage_switch_count",
                    "lineage_path_state",
                    "lineage_instance_mismatch",
                    "active_audio_output_chain_ids",
                    "active_audio_output_chain_classes",
                    "attached_callback_target_chain_ids",
                    "attached_callback_target_chain_classes",
                    "callback_fired_source_chain_ids",
                    "callback_fired_source_chain_classes",
                    "callback_processed_source_chain_ids",
                    "callback_processed_source_chain_classes",
                    "callback_emitted_source_chain_ids",
                    "callback_emitted_source_chain_classes",
                    "lineage_active_to_attached_link",
                    "lineage_attached_to_fired_link",
                )
                for key in lineage_keys:
                    value = details.get(key)
                    if value in (None, "", []):
                        continue
                    if key == "lineage_path_state":
                        current = str(room_state.get(key) or "")
                        if path_precedence.get(str(value), 0) < path_precedence.get(current, 0):
                            continue
                    room_state[key] = value
                if mark_seen:
                    if room_state.get("active_audio_output_seen_at_ms") is None and details.get("active_audio_output_id"):
                        room_state["active_audio_output_seen_at_ms"] = ts_ms
                    if room_state.get("attached_callback_target_seen_at_ms") is None and details.get("attached_callback_target_id"):
                        room_state["attached_callback_target_seen_at_ms"] = ts_ms
                    if room_state.get("callback_fired_source_seen_at_ms") is None and details.get("callback_fired_source_id"):
                        room_state["callback_fired_source_seen_at_ms"] = ts_ms
                    if room_state.get("callback_processed_source_seen_at_ms") is None and details.get("callback_processed_source_id"):
                        room_state["callback_processed_source_seen_at_ms"] = ts_ms
                    if room_state.get("callback_emitted_source_seen_at_ms") is None and details.get("callback_emitted_source_id"):
                        room_state["callback_emitted_source_seen_at_ms"] = ts_ms
                    if details.get("callback_discard_reason"):
                        room_state["callback_discarded_at_ms"] = ts_ms

            if stage == "worker_job_claimed":
                self.last_worker_claim_at_ms = ts_ms
                room_state["worker_job_claimed_at_ms"] = ts_ms
            elif stage == "phase1_runtime_build_begin":
                room_state["phase1_runtime_build_begin_at_ms"] = ts_ms
            elif stage == "phase1_runtime_build_end":
                room_state["phase1_runtime_build_end_at_ms"] = ts_ms
            elif stage == "phase1_runtime_llm_begin":
                room_state["phase1_runtime_llm_begin_at_ms"] = ts_ms
            elif stage == "phase1_runtime_llm_end":
                room_state["phase1_runtime_llm_end_at_ms"] = ts_ms
            elif stage == "phase1_runtime_stt_begin":
                room_state["phase1_runtime_stt_begin_at_ms"] = ts_ms
            elif stage == "phase1_runtime_stt_end":
                room_state["phase1_runtime_stt_end_at_ms"] = ts_ms
            elif stage == "phase1_runtime_tts_begin":
                room_state["phase1_runtime_tts_begin_at_ms"] = ts_ms
            elif stage == "phase1_runtime_tts_end":
                room_state["phase1_runtime_tts_end_at_ms"] = ts_ms
            elif stage == "phase1_runtime_vad_begin":
                room_state["phase1_runtime_vad_begin_at_ms"] = ts_ms
            elif stage == "phase1_runtime_vad_end":
                room_state["phase1_runtime_vad_end_at_ms"] = ts_ms
            elif stage == "room_connect_started":
                room_state["room_connect_started_at_ms"] = ts_ms
            elif stage == "room_connect_success":
                room_state["room_connect_success_at_ms"] = ts_ms
            elif stage == "room_connect_timeout":
                room_state["room_connect_timeout_at_ms"] = ts_ms
                room_state["room_connect_failure_reason"] = str(details.get("exception_type") or "room_connect_timeout")
            elif stage in {"room_connect_exception", "room_connect_cancelled"}:
                room_state["room_connect_failure_at_ms"] = ts_ms
                room_state["room_connect_failure_reason"] = str(
                    details.get("exception_type") or stage
                )
            elif stage == "room_joined":
                self.last_room_joined_at_ms = ts_ms
                room_state["room_joined_at_ms"] = ts_ms
            elif stage == "session_prestart_turn_detection_resolve_begin":
                room_state["session_prestart_turn_detection_resolve_begin_at_ms"] = ts_ms
            elif stage == "session_prestart_turn_detection_resolve_end":
                room_state["session_prestart_turn_detection_resolve_end_at_ms"] = ts_ms
            elif stage == "session_prestart_endpointing_resolve_begin":
                room_state["session_prestart_endpointing_resolve_begin_at_ms"] = ts_ms
            elif stage == "session_prestart_endpointing_resolve_end":
                room_state["session_prestart_endpointing_resolve_end_at_ms"] = ts_ms
            elif stage == "session_prestart_voice_agent_config_begin":
                room_state["session_prestart_voice_agent_config_begin_at_ms"] = ts_ms
            elif stage == "session_prestart_voice_agent_config_end":
                room_state["session_prestart_voice_agent_config_end_at_ms"] = ts_ms
            elif stage == "voice_agent_create_begin":
                room_state["voice_agent_create_begin_at_ms"] = ts_ms
            elif stage == "voice_agent_create_complete":
                room_state["voice_agent_create_complete_at_ms"] = ts_ms
            elif stage == "session_object_create_begin":
                room_state["session_object_create_begin_at_ms"] = ts_ms
            elif stage == "session_object_create_end":
                room_state["session_object_create_end_at_ms"] = ts_ms
            elif stage == "session_start_invoked":
                room_state["session_start_invoked_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or "")
            elif stage == "session_start_media_bind_probe_register_begin":
                room_state["session_start_media_bind_probe_register_begin_at_ms"] = ts_ms
                room_state["media_bind_probe_registration_state"] = str(details.get("media_bind_probe_registration_state") or "registering")
                room_state["media_bind_probe_source_path"] = str(details.get("media_bind_probe_source_path") or room_state.get("media_bind_probe_source_path") or "")
                room_state["media_bind_probe_room_io_id"] = str(details.get("media_bind_probe_room_io_id") or room_state.get("media_bind_probe_room_io_id") or "")
                room_state["media_bind_probe_audio_output_id"] = str(details.get("media_bind_probe_audio_output_id") or room_state.get("media_bind_probe_audio_output_id") or "")
                _apply_lineage_details(mark_seen=False)
            elif stage == "session_start_media_bind_probe_register_complete":
                room_state["session_start_media_bind_probe_register_complete_at_ms"] = ts_ms
                room_state["media_bind_probe_registration_state"] = str(details.get("media_bind_probe_registration_state") or "complete")
                room_state["media_bind_probe_source_path"] = str(details.get("media_bind_probe_source_path") or room_state.get("media_bind_probe_source_path") or "")
                room_state["media_bind_probe_room_io_id"] = str(details.get("media_bind_probe_room_io_id") or room_state.get("media_bind_probe_room_io_id") or "")
                room_state["media_bind_probe_audio_output_id"] = str(details.get("media_bind_probe_audio_output_id") or room_state.get("media_bind_probe_audio_output_id") or "")
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_transport_attach_begin":
                room_state["session_start_transport_attach_begin_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_transport_attach_complete":
                room_state["session_start_transport_attach_complete_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_listener_attach_complete":
                room_state["listener_attach_ts_ms"] = room_state.get("listener_attach_ts_ms") or ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_participant_visible":
                room_state["participant_visible_ts_ms"] = room_state.get("participant_visible_ts_ms") or ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_track_published":
                room_state["track_published_ts_ms"] = room_state.get("track_published_ts_ms") or ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_track_subscribed":
                room_state["track_subscribed_consume_ts_ms"] = room_state.get("track_subscribed_consume_ts_ms") or ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_teardown_begin":
                room_state["teardown_begin_ts_ms"] = room_state.get("teardown_begin_ts_ms") or ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_teardown_ipc_closed":
                room_state["teardown_ipc_closed_ts_ms"] = room_state.get("teardown_ipc_closed_ts_ms") or ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_room_media_bind_begin":
                room_state["session_start_room_media_bind_begin_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_media_bind_participant_detected":
                room_state["session_start_media_bind_participant_detected_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_local_track_subscribed_event":
                room_state["session_start_media_bind_local_track_subscribed_event_at_ms"] = ts_ms
                room_state["track_subscribed_emit_ts_ms"] = room_state.get("track_subscribed_emit_ts_ms") or ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_track_published":
                room_state["session_start_media_bind_track_published_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_track_subscribed":
                room_state["session_start_media_bind_track_subscribed_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_audio_output_started":
                room_state["session_start_media_bind_audio_output_started_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_synced_audio_frame_received":
                room_state["session_start_media_bind_synced_audio_frame_received_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_synced_audio_frame_emitted":
                room_state["session_start_media_bind_synced_audio_frame_emitted_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_participant_audio_frame_received":
                room_state["session_start_media_bind_participant_audio_frame_received_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_participant_audio_frame_processed":
                room_state["session_start_media_bind_participant_audio_frame_processed_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_first_audio_packet":
                room_state["session_start_media_bind_first_audio_packet_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_first_frame_seen_at_transport":
                room_state["session_start_media_bind_first_frame_seen_at_transport_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_first_frame_processed_at_transport":
                room_state["session_start_media_bind_first_frame_processed_at_transport_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_first_pcm_frame":
                room_state["session_start_media_bind_first_pcm_frame_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["interactive_start_probe_seen"] = True
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_audio_frame_discarded":
                room_state["session_start_media_bind_audio_frame_discarded_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_lineage_event":
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_media_bind_probe_path_miss":
                room_state["session_start_media_bind_probe_path_miss_at_ms"] = ts_ms
                room_state["media_bind_probe_registration_state"] = "path_miss"
                room_state["media_bind_timeout_class"] = "callback_path_miss"
                room_state["last_media_bind_probe_stage"] = stage
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_room_media_bind_complete":
                room_state["session_start_room_media_bind_complete_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
                if not room_state.get("last_media_bind_probe_stage"):
                    room_state["media_bind_timeout_class"] = "callback_path_miss"
                _apply_lineage_details(mark_seen=True)
            elif stage == "session_start_agent_graph_begin":
                room_state["session_start_agent_graph_begin_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_agent_graph_complete":
                room_state["session_start_agent_graph_complete_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_audio_pipeline_begin":
                room_state["session_start_audio_pipeline_begin_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_audio_pipeline_complete":
                room_state["session_start_audio_pipeline_complete_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_client_events_begin":
                room_state["session_start_client_events_begin_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_client_events_complete":
                room_state["session_start_client_events_complete_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_start_first_stream_ready":
                room_state["session_start_first_stream_ready_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_started":
                self.last_session_started_at_ms = ts_ms
                room_state["session_started_at_ms"] = ts_ms
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            elif stage == "session_ready":
                self.last_session_ready_at_ms = ts_ms
                room_state["session_ready_at_ms"] = ts_ms
            elif stage == "turn_detection_background_pending":
                self.enhanced_turn_detection_ready = False
                self.enhanced_turn_detection_mode = str(details.get("active_mode") or "")
                room_state["turn_detection_mode"] = self.enhanced_turn_detection_mode
            elif stage == "eou_init_thread_handoff":
                self.eou_init_thread_handoff_count += 1
            elif stage == "eou_registration_started":
                self.eou_registration_state = "starting"
                self.eou_registration_error = ""
            elif stage == "eou_registration_reused_inflight":
                self.eou_registration_state = "starting"
                self.eou_registration_error = ""
            elif stage == "eou_registration_reused_cached":
                self.eou_registration_state = "ready"
                self.eou_registration_error = ""
            elif stage == "eou_registration_completed":
                self.eou_registration_state = "ready"
                self.eou_registration_error = ""
                self.eou_init_main_thread_success += 1
            elif stage == "eou_registration_failed":
                self.eou_registration_state = "failed"
                self.eou_registration_error = str(details.get("error") or "")
                self.eou_init_main_thread_fail += 1
            elif stage == "onnx_init_started":
                self.onnx_init_state = "starting"
                self.onnx_init_error = ""
                self.onnx_init_started_at_ms = ts_ms
            elif stage == "onnx_init_completed":
                self.onnx_init_state = "ready"
                self.enhanced_turn_detection_ready = True
                self.enhanced_turn_detection_mode = str(details.get("mode") or self.enhanced_turn_detection_mode or "")
                self.onnx_init_error = ""
                self.onnx_background_ready_at_ms = ts_ms
                room_state["turn_detection_mode"] = self.enhanced_turn_detection_mode
            elif stage == "onnx_init_failed":
                self.onnx_init_state = "failed"
                self.enhanced_turn_detection_ready = False
                self.onnx_init_error = str(details.get("error") or "")
            elif stage == "session_started_on_stt":
                self.sessions_started_on_stt += 1
                room_state["turn_detection_mode"] = str(details.get("mode") or "stt")
            elif stage == "turn_detection_upgraded_to_eou":
                self.sessions_upgraded_to_eou += 1
                self.eou_upgrade_success += 1
                self.enhanced_turn_detection_ready = True
                self.enhanced_turn_detection_mode = str(details.get("mode") or self.enhanced_turn_detection_mode or "")
                wait_ms = details.get("wait_ms")
                if wait_ms is not None:
                    try:
                        self.turn_detection_upgrade_durations_ms.append(max(0, int(wait_ms)))
                    except Exception:
                        pass
                room_state["turn_detection_mode"] = self.enhanced_turn_detection_mode
            elif stage == "turn_detection_upgrade_failed":
                self.upgrade_failures += 1
            elif stage == "session_completed_without_eou":
                self.sessions_completed_without_eou += 1
            elif stage in {"participant_present", "first_participant_joined"}:
                room_state["first_participant_joined_at_ms"] = ts_ms
                room_state["participant_identity"] = str(details.get("identity") or "")
            elif stage == "session_failed":
                reason = str(details.get("reason") or details.get("error") or "session_failed")
                self.last_session_failure_at_ms = ts_ms
                self.last_session_failure_reason = reason
                room_state["session_failed_at_ms"] = ts_ms
                room_state["session_failure_reason"] = reason
                room_state["session_failure_taxonomy"] = str(details.get("failure_taxonomy") or "")
                room_state["session_failure_timeout_class"] = str(details.get("failure_timeout_class") or "")
                if room_state["session_failure_timeout_class"] in {
                    "participant_missing_timeout",
                    "publish_timeout",
                    "subscription_timeout",
                    "audio_output_start_timeout",
                    "first_audio_packet_timeout",
                    "first_pcm_frame_timeout",
                    "callback_path_miss",
                    "unknown_media_bind_timeout",
                }:
                    room_state["media_bind_timeout_class"] = room_state["session_failure_timeout_class"]
                room_state["session_failure_last_stage"] = str(details.get("last_stage") or "")
                room_state["session_failure_observed_stages"] = list(details.get("observed_stages") or [])
                room_state["session_start_id"] = str(details.get("session_start_id") or room_state.get("session_start_id") or "")
            room_state["startup_gate_classification"] = _classify_b5_startup_gate(room_state)
        self.active_session_count = sum(
            1
            for room_state in self._room_stage_by_room.values()
            if room_state.get("session_ready_at_ms")
            and (
                room_state.get("session_failed_at_ms") is None
                or int(room_state["session_ready_at_ms"]) >= int(room_state["session_failed_at_ms"])
            )
        )

    @staticmethod
    def _room_state_duration(room_state: dict[str, Any], begin_key: str, end_key: str) -> int | None:
        begin_value = room_state.get(begin_key)
        end_value = room_state.get(end_key)
        if begin_value is None or end_value is None:
            return None
        return max(0, int(end_value) - int(begin_value))

    def _room_state_timing_summary(self, room_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "phase1_runtime_build_ms": self._room_state_duration(
                room_state, "phase1_runtime_build_begin_at_ms", "phase1_runtime_build_end_at_ms"
            ),
            "phase1_runtime_llm_ms": self._room_state_duration(
                room_state, "phase1_runtime_llm_begin_at_ms", "phase1_runtime_llm_end_at_ms"
            ),
            "phase1_runtime_stt_ms": self._room_state_duration(
                room_state, "phase1_runtime_stt_begin_at_ms", "phase1_runtime_stt_end_at_ms"
            ),
            "phase1_runtime_tts_ms": self._room_state_duration(
                room_state, "phase1_runtime_tts_begin_at_ms", "phase1_runtime_tts_end_at_ms"
            ),
            "phase1_runtime_vad_ms": self._room_state_duration(
                room_state, "phase1_runtime_vad_begin_at_ms", "phase1_runtime_vad_end_at_ms"
            ),
            "voice_agent_create_ms": self._room_state_duration(
                room_state, "voice_agent_create_begin_at_ms", "voice_agent_create_complete_at_ms"
            ),
            "session_object_create_ms": self._room_state_duration(
                room_state, "session_object_create_begin_at_ms", "session_object_create_end_at_ms"
            ),
            "pre_session_start_gap_ms": self._room_state_duration(
                room_state, "session_object_create_end_at_ms", "session_start_invoked_at_ms"
            ),
            "session_start_transport_attach_ms": self._room_state_duration(
                room_state,
                "session_start_transport_attach_begin_at_ms",
                "session_start_transport_attach_complete_at_ms",
            ),
            "session_start_room_media_bind_ms": self._room_state_duration(
                room_state,
                "session_start_room_media_bind_begin_at_ms",
                "session_start_room_media_bind_complete_at_ms",
            ),
            "participant_wait_ms": self._room_state_duration(
                room_state,
                "session_start_room_media_bind_begin_at_ms",
                "session_start_media_bind_participant_detected_at_ms",
            ),
            "publish_wait_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_participant_detected_at_ms",
                "session_start_media_bind_track_published_at_ms",
            ),
            "local_track_subscribed_wait_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_track_published_at_ms",
                "session_start_media_bind_local_track_subscribed_event_at_ms",
            ),
            "subscribe_wait_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_track_published_at_ms",
                "session_start_media_bind_track_subscribed_at_ms",
            ),
            "audio_output_start_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_track_subscribed_at_ms",
                "session_start_media_bind_audio_output_started_at_ms",
            ),
            "first_audio_packet_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_audio_output_started_at_ms",
                "session_start_media_bind_first_audio_packet_at_ms",
            ),
            "synced_audio_frame_wait_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_track_subscribed_at_ms",
                "session_start_media_bind_synced_audio_frame_received_at_ms",
            ),
            "participant_audio_frame_wait_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_synced_audio_frame_received_at_ms",
                "session_start_media_bind_participant_audio_frame_received_at_ms",
            ),
            "transport_frame_ingress_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_participant_audio_frame_processed_at_ms",
                "session_start_media_bind_first_frame_seen_at_transport_at_ms",
            ),
            "transport_frame_processed_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_first_frame_seen_at_transport_at_ms",
                "session_start_media_bind_first_frame_processed_at_transport_at_ms",
            ),
            "first_pcm_frame_ms": self._room_state_duration(
                room_state,
                "session_start_media_bind_first_audio_packet_at_ms",
                "session_start_media_bind_first_pcm_frame_at_ms",
            ),
            "active_to_attached_ms": self._room_state_duration(
                room_state,
                "active_audio_output_seen_at_ms",
                "attached_callback_target_seen_at_ms",
            ),
            "attached_to_fired_ms": self._room_state_duration(
                room_state,
                "attached_callback_target_seen_at_ms",
                "callback_fired_source_seen_at_ms",
            ),
            "total_media_bind_ms": self._room_state_duration(
                room_state,
                "session_start_room_media_bind_begin_at_ms",
                "session_start_room_media_bind_complete_at_ms",
            ),
            "session_start_agent_graph_ms": self._room_state_duration(
                room_state,
                "session_start_agent_graph_begin_at_ms",
                "session_start_agent_graph_complete_at_ms",
            ),
            "session_start_audio_pipeline_ms": self._room_state_duration(
                room_state,
                "session_start_audio_pipeline_begin_at_ms",
                "session_start_audio_pipeline_complete_at_ms",
            ),
            "session_start_client_events_ms": self._room_state_duration(
                room_state,
                "session_start_client_events_begin_at_ms",
                "session_start_client_events_complete_at_ms",
            ),
            "session_start_first_stream_ready_ms": self._room_state_duration(
                room_state,
                "session_start_invoked_at_ms",
                "session_start_first_stream_ready_at_ms",
            ),
            "teardown_to_ipc_close_ms": self._room_state_duration(
                room_state,
                "teardown_begin_ts_ms",
                "teardown_ipc_closed_ts_ms",
            ),
            "teardown_to_callback_gap_ms": self._room_state_duration(
                room_state,
                "teardown_begin_ts_ms",
                "teardown_ipc_closed_ts_ms",
            ),
        }

    def room_stage_snapshot(self, room_name: str) -> dict[str, Any]:
        with self._lock:
            self._sync_boot_events_locked()
            room_state = dict(self._room_stage_by_room.get(room_name, {}))
            timing = self._room_state_timing_summary(room_state)
            return {
                "room": room_name,
                "worker_job_claimed_at_ms": room_state.get("worker_job_claimed_at_ms"),
                "phase1_runtime_build_begin_at_ms": room_state.get("phase1_runtime_build_begin_at_ms"),
                "phase1_runtime_build_end_at_ms": room_state.get("phase1_runtime_build_end_at_ms"),
                "phase1_runtime_llm_begin_at_ms": room_state.get("phase1_runtime_llm_begin_at_ms"),
                "phase1_runtime_llm_end_at_ms": room_state.get("phase1_runtime_llm_end_at_ms"),
                "phase1_runtime_stt_begin_at_ms": room_state.get("phase1_runtime_stt_begin_at_ms"),
                "phase1_runtime_stt_end_at_ms": room_state.get("phase1_runtime_stt_end_at_ms"),
                "phase1_runtime_tts_begin_at_ms": room_state.get("phase1_runtime_tts_begin_at_ms"),
                "phase1_runtime_tts_end_at_ms": room_state.get("phase1_runtime_tts_end_at_ms"),
                "phase1_runtime_vad_begin_at_ms": room_state.get("phase1_runtime_vad_begin_at_ms"),
                "phase1_runtime_vad_end_at_ms": room_state.get("phase1_runtime_vad_end_at_ms"),
                "room_connect_started_at_ms": room_state.get("room_connect_started_at_ms"),
                "room_connect_success_at_ms": room_state.get("room_connect_success_at_ms"),
                "room_connect_timeout_at_ms": room_state.get("room_connect_timeout_at_ms"),
                "room_connect_failure_at_ms": room_state.get("room_connect_failure_at_ms"),
                "room_connect_failure_reason": room_state.get("room_connect_failure_reason", ""),
                "room_joined_at_ms": room_state.get("room_joined_at_ms"),
                "session_prestart_turn_detection_resolve_begin_at_ms": room_state.get("session_prestart_turn_detection_resolve_begin_at_ms"),
                "session_prestart_turn_detection_resolve_end_at_ms": room_state.get("session_prestart_turn_detection_resolve_end_at_ms"),
                "session_prestart_endpointing_resolve_begin_at_ms": room_state.get("session_prestart_endpointing_resolve_begin_at_ms"),
                "session_prestart_endpointing_resolve_end_at_ms": room_state.get("session_prestart_endpointing_resolve_end_at_ms"),
                "session_prestart_voice_agent_config_begin_at_ms": room_state.get("session_prestart_voice_agent_config_begin_at_ms"),
                "session_prestart_voice_agent_config_end_at_ms": room_state.get("session_prestart_voice_agent_config_end_at_ms"),
                "voice_agent_create_begin_at_ms": room_state.get("voice_agent_create_begin_at_ms"),
                "voice_agent_create_complete_at_ms": room_state.get("voice_agent_create_complete_at_ms"),
                "session_object_create_begin_at_ms": room_state.get("session_object_create_begin_at_ms"),
                "session_object_create_end_at_ms": room_state.get("session_object_create_end_at_ms"),
                "session_start_id": room_state.get("session_start_id", ""),
                "session_start_invoked_at_ms": room_state.get("session_start_invoked_at_ms"),
                "session_start_media_bind_probe_register_begin_at_ms": room_state.get("session_start_media_bind_probe_register_begin_at_ms"),
                "session_start_media_bind_probe_register_complete_at_ms": room_state.get("session_start_media_bind_probe_register_complete_at_ms"),
                "session_start_transport_attach_begin_at_ms": room_state.get("session_start_transport_attach_begin_at_ms"),
                "session_start_transport_attach_complete_at_ms": room_state.get("session_start_transport_attach_complete_at_ms"),
                "listener_attach_ts_ms": room_state.get("listener_attach_ts_ms"),
                "track_subscribed_emit_ts_ms": room_state.get("track_subscribed_emit_ts_ms"),
                "track_subscribed_consume_ts_ms": room_state.get("track_subscribed_consume_ts_ms"),
                "startup_gate_classification": room_state.get("startup_gate_classification", ""),
                "teardown_begin_ts_ms": room_state.get("teardown_begin_ts_ms"),
                "teardown_ipc_closed_ts_ms": room_state.get("teardown_ipc_closed_ts_ms"),
                "session_start_room_media_bind_begin_at_ms": room_state.get("session_start_room_media_bind_begin_at_ms"),
                "session_start_media_bind_participant_detected_at_ms": room_state.get("session_start_media_bind_participant_detected_at_ms"),
                "session_start_media_bind_local_track_subscribed_event_at_ms": room_state.get("session_start_media_bind_local_track_subscribed_event_at_ms"),
                "session_start_media_bind_track_published_at_ms": room_state.get("session_start_media_bind_track_published_at_ms"),
                "session_start_media_bind_track_subscribed_at_ms": room_state.get("session_start_media_bind_track_subscribed_at_ms"),
                "session_start_media_bind_audio_output_started_at_ms": room_state.get("session_start_media_bind_audio_output_started_at_ms"),
                "session_start_media_bind_synced_audio_frame_received_at_ms": room_state.get("session_start_media_bind_synced_audio_frame_received_at_ms"),
                "session_start_media_bind_synced_audio_frame_emitted_at_ms": room_state.get("session_start_media_bind_synced_audio_frame_emitted_at_ms"),
                "session_start_media_bind_participant_audio_frame_received_at_ms": room_state.get("session_start_media_bind_participant_audio_frame_received_at_ms"),
                "session_start_media_bind_participant_audio_frame_processed_at_ms": room_state.get("session_start_media_bind_participant_audio_frame_processed_at_ms"),
                "session_start_media_bind_first_audio_packet_at_ms": room_state.get("session_start_media_bind_first_audio_packet_at_ms"),
                "session_start_media_bind_first_frame_seen_at_transport_at_ms": room_state.get("session_start_media_bind_first_frame_seen_at_transport_at_ms"),
                "session_start_media_bind_first_frame_processed_at_transport_at_ms": room_state.get("session_start_media_bind_first_frame_processed_at_transport_at_ms"),
                "session_start_media_bind_first_pcm_frame_at_ms": room_state.get("session_start_media_bind_first_pcm_frame_at_ms"),
                "session_start_media_bind_audio_frame_discarded_at_ms": room_state.get("session_start_media_bind_audio_frame_discarded_at_ms"),
                "session_start_room_media_bind_complete_at_ms": room_state.get("session_start_room_media_bind_complete_at_ms"),
                "media_bind_probe_registration_state": room_state.get("media_bind_probe_registration_state", ""),
                "media_bind_probe_source_path": room_state.get("media_bind_probe_source_path", ""),
                "media_bind_probe_room_io_id": room_state.get("media_bind_probe_room_io_id", ""),
                "media_bind_probe_audio_output_id": room_state.get("media_bind_probe_audio_output_id", ""),
                "active_room_io_id": room_state.get("active_room_io_id", ""),
                "active_audio_output_id": room_state.get("active_audio_output_id", ""),
                "attached_callback_target_id": room_state.get("attached_callback_target_id", ""),
                "callback_fired_source_id": room_state.get("callback_fired_source_id", ""),
                "callback_processed_source_id": room_state.get("callback_processed_source_id", ""),
                "callback_emitted_source_id": room_state.get("callback_emitted_source_id", ""),
                "callback_discard_reason": room_state.get("callback_discard_reason", ""),
                "lineage_switch_count": int(room_state.get("lineage_switch_count") or 0),
                "lineage_path_state": room_state.get("lineage_path_state", ""),
                "lineage_instance_mismatch": bool(room_state.get("lineage_instance_mismatch")),
                "active_audio_output_chain_ids": list(room_state.get("active_audio_output_chain_ids", [])),
                "active_audio_output_chain_classes": list(room_state.get("active_audio_output_chain_classes", [])),
                "attached_callback_target_chain_ids": list(room_state.get("attached_callback_target_chain_ids", [])),
                "attached_callback_target_chain_classes": list(room_state.get("attached_callback_target_chain_classes", [])),
                "callback_fired_source_chain_ids": list(room_state.get("callback_fired_source_chain_ids", [])),
                "callback_fired_source_chain_classes": list(room_state.get("callback_fired_source_chain_classes", [])),
                "callback_processed_source_chain_ids": list(room_state.get("callback_processed_source_chain_ids", [])),
                "callback_processed_source_chain_classes": list(room_state.get("callback_processed_source_chain_classes", [])),
                "callback_emitted_source_chain_ids": list(room_state.get("callback_emitted_source_chain_ids", [])),
                "callback_emitted_source_chain_classes": list(room_state.get("callback_emitted_source_chain_classes", [])),
                "active_audio_output_seen_at_ms": room_state.get("active_audio_output_seen_at_ms"),
                "attached_callback_target_seen_at_ms": room_state.get("attached_callback_target_seen_at_ms"),
                "callback_fired_source_seen_at_ms": room_state.get("callback_fired_source_seen_at_ms"),
                "callback_processed_source_seen_at_ms": room_state.get("callback_processed_source_seen_at_ms"),
                "callback_emitted_source_seen_at_ms": room_state.get("callback_emitted_source_seen_at_ms"),
                "callback_discarded_at_ms": room_state.get("callback_discarded_at_ms"),
                "lineage_active_to_attached_link": room_state.get("lineage_active_to_attached_link", ""),
                "lineage_attached_to_fired_link": room_state.get("lineage_attached_to_fired_link", ""),
                "interactive_start_probe_seen": bool(room_state.get("interactive_start_probe_seen")),
                "last_media_bind_probe_stage": room_state.get("last_media_bind_probe_stage", ""),
                "media_bind_timeout_class": room_state.get("media_bind_timeout_class", ""),
                "session_start_agent_graph_begin_at_ms": room_state.get("session_start_agent_graph_begin_at_ms"),
                "session_start_agent_graph_complete_at_ms": room_state.get("session_start_agent_graph_complete_at_ms"),
                "session_start_audio_pipeline_begin_at_ms": room_state.get("session_start_audio_pipeline_begin_at_ms"),
                "session_start_audio_pipeline_complete_at_ms": room_state.get("session_start_audio_pipeline_complete_at_ms"),
                "session_start_client_events_begin_at_ms": room_state.get("session_start_client_events_begin_at_ms"),
                "session_start_client_events_complete_at_ms": room_state.get("session_start_client_events_complete_at_ms"),
                "session_start_first_stream_ready_at_ms": room_state.get("session_start_first_stream_ready_at_ms"),
                "session_started_at_ms": room_state.get("session_started_at_ms"),
                "session_ready_at_ms": room_state.get("session_ready_at_ms"),
                "first_participant_joined_at_ms": room_state.get("first_participant_joined_at_ms"),
                "participant_identity": room_state.get("participant_identity", ""),
                "session_failed_at_ms": room_state.get("session_failed_at_ms"),
                "session_failure_reason": room_state.get("session_failure_reason", ""),
                "session_failure_taxonomy": room_state.get("session_failure_taxonomy", ""),
                "session_failure_timeout_class": room_state.get("session_failure_timeout_class", ""),
                "session_failure_last_stage": room_state.get("session_failure_last_stage", ""),
                "session_failure_observed_stages": list(room_state.get("session_failure_observed_stages", [])),
                **timing,
            }

    def recent_connect_durations_ms(self, *, limit: int = 20) -> list[float]:
        with self._lock:
            self._sync_boot_events_locked()
            durations: list[float] = []
            for room_state in self._room_stage_by_room.values():
                started = room_state.get("room_connect_started_at_ms")
                succeeded = room_state.get("room_connect_success_at_ms")
                if started is None or succeeded is None:
                    continue
                try:
                    duration_ms = float(succeeded) - float(started)
                except Exception:
                    continue
                if duration_ms >= 0:
                    durations.append(duration_ms)
            durations.sort()
            if limit > 0:
                return durations[-limit:]
            return durations

    def has_successful_room_join(self) -> bool:
        with self._lock:
            self._sync_boot_events_locked()
            return any(room_state.get("room_joined_at_ms") for room_state in self._room_stage_by_room.values())

    def snapshot(self) -> dict[str, Any]:
        now_ms = int(time.time() * 1000)
        with self._lock:
            self._sync_boot_events_locked()
            worker_heartbeat_fresh, heartbeat_age_ms = self._worker_alive_locked(now_ms)
            claim_probe_valid, claim_probe_age_ms = self._claim_probe_valid_locked(now_ms)
            if self.last_claim_probe_ok and not claim_probe_valid:
                reason = "ttl_expired" if claim_probe_age_ms is not None else "claim_probe_invalid"
                self._invalidate_claim_probe_locked(reason=reason, emit_event=False)
            infra_ready = self._infra_ready_locked(now_ms)
            session_subsystem_healthy = self._session_subsystem_healthy_locked(now_ms)
            checks = {
                "api_up": self.api_up,
                "token_server_up": self.token_server_up,
                "worker_heartbeat_fresh": worker_heartbeat_fresh,
                "worker_alive": worker_heartbeat_fresh,
                "worker_registered": self.worker_connected,
                "worker_connect_error": self._worker_connect_error_active_locked(),
                "dispatch_pipeline_ready": self.dispatch_pipeline_ready,
                "idle_process_ready": self.idle_process_ready,
                "session_subsystem_healthy": session_subsystem_healthy,
                "capability_ready": self.capability_ready,
                "claim_probe_valid": claim_probe_valid,
                "last_claim_probe_ok": claim_probe_valid,
                "dispatch_claimable_ready": claim_probe_valid or self.idle_process_ready,
                "fatal_startup_fault": self.fatal_startup_fault,
            }
            ready_predicates = {
                "api_up": self.api_up,
                "token_server_up": self.token_server_up,
                "worker_heartbeat_fresh": worker_heartbeat_fresh,
                "dispatch_pipeline_ready": self.dispatch_pipeline_ready,
                "dispatch_claimable_ready": claim_probe_valid or self.idle_process_ready,
                "session_subsystem_healthy": session_subsystem_healthy,
            }
            core_ready = self._session_capable_ready_locked(now_ms)
            capability_ready = self.capability_ready
            if self.fatal_startup_fault:
                state = ReadinessState.FAILED.value
            elif self._worker_connect_error_active_locked():
                state = ReadinessState.FAILED.value
            elif capability_ready and core_ready:
                state = ReadinessState.READY_CAPABILITY.value
            elif core_ready:
                state = ReadinessState.READY_SESSION_CAPABLE.value
            elif self.last_session_failure_at_ms is not None and not session_subsystem_healthy:
                state = ReadinessState.DEGRADED.value
            elif infra_ready:
                if self.last_worker_claim_at_ms or self.last_room_joined_at_ms or self.last_session_started_at_ms:
                    state = ReadinessState.SESSION_WARMING.value
                else:
                    state = ReadinessState.READY_INFRA.value
            elif self.state in {
                ReadinessState.READY_SESSION_CAPABLE,
                ReadinessState.READY_CAPABILITY,
            }:
                state = ReadinessState.DEGRADED.value
            elif self.state in {
                ReadinessState.DEGRADED,
            }:
                state = ReadinessState.DEGRADED.value
            else:
                state = self.state.value
            if core_ready and self.core_ready_at_ms is None:
                self.core_ready_at_ms = now_ms
                self._mark_worker_attempt_stage_locked("runtime_ready", now_ms)
                self._emit_boot_event("ready_core_declared", {"reason": "dispatch_claimable"})
            attempt_started_at_ms = self.worker_attempt_timing_ms.get("attempt_started_at_ms")

            def _attempt_relative(field_name: str) -> int | None:
                field_value = self.worker_attempt_timing_ms.get(field_name)
                if field_value is None or attempt_started_at_ms is None:
                    return None
                return max(0, int(field_value) - int(attempt_started_at_ms))

            registration_ms = None
            if (
                self.worker_attempt_timing_ms.get("server_run_enter_at_ms") is not None
                and self.worker_attempt_timing_ms.get("worker_registered_at_ms") is not None
            ):
                registration_ms = max(
                    0,
                    int(self.worker_attempt_timing_ms["worker_registered_at_ms"])
                    - int(self.worker_attempt_timing_ms["server_run_enter_at_ms"]),
                )
            registered_to_ready_ms = None
            if (
                self.worker_attempt_timing_ms.get("worker_registered_at_ms") is not None
                and self.worker_attempt_timing_ms.get("runtime_ready_at_ms") is not None
            ):
                registered_to_ready_ms = max(
                    0,
                    int(self.worker_attempt_timing_ms["runtime_ready_at_ms"])
                    - int(self.worker_attempt_timing_ms["worker_registered_at_ms"]),
                )
            boot_stage_sequence = []
            boot_blocker_stage = None
            for stage_name, field_name in self._boot_stage_definitions():
                status = self.worker_attempt_stage_status.get(stage_name, "pending")
                elapsed_ms = _attempt_relative(field_name)
                boot_stage_sequence.append(
                    {
                        "stage": stage_name,
                        "status": status,
                        "required": True,
                        "elapsed_ms": elapsed_ms,
                    }
                )
                if boot_blocker_stage is None and status not in {"done", "skipped"}:
                    boot_blocker_stage = stage_name

            global_init_stage_timing: dict[str, dict[str, Any]] = {}
            global_init_stage_sequence: list[dict[str, Any]] = []
            global_init_dependency_map: dict[str, dict[str, Any]] = {}
            global_init_total_ms = self.global_init_total_ms
            global_init_slowest_stage = ""
            global_init_slowest_stage_ms = -1
            for stage_name in self.global_init_stage_order:
                stage_state = dict(self.global_init_stage_state.get(stage_name) or {})
                if not stage_state:
                    continue
                stage_elapsed_ms = stage_state.get("stage_elapsed_ms")
                if stage_elapsed_ms is None:
                    begin_elapsed_ms = stage_state.get("begin_cumulative_elapsed_ms")
                    end_elapsed_ms = stage_state.get("cumulative_elapsed_ms")
                    if begin_elapsed_ms is not None and end_elapsed_ms is not None:
                        stage_elapsed_ms = max(0, int(end_elapsed_ms) - int(begin_elapsed_ms))
                cumulative_elapsed_ms = stage_state.get("cumulative_elapsed_ms")
                if cumulative_elapsed_ms is None:
                    cumulative_elapsed_ms = stage_state.get("begin_cumulative_elapsed_ms")
                timing_entry = {
                    "status": str(stage_state.get("status") or "pending"),
                    "criticality": str(stage_state.get("criticality") or ""),
                    "cumulative_elapsed_ms": cumulative_elapsed_ms,
                    "stage_elapsed_ms": stage_elapsed_ms,
                }
                dependency_entry = {
                    "criticality": str(stage_state.get("criticality") or ""),
                    "required_before_first_send": bool(stage_state.get("required_before_first_send")),
                    "required_before_first_voice_turn": bool(stage_state.get("required_before_first_voice_turn")),
                    "required_before_memory_query": bool(stage_state.get("required_before_memory_query")),
                    "required_before_tool_use": bool(stage_state.get("required_before_tool_use")),
                }
                global_init_stage_timing[stage_name] = timing_entry
                global_init_dependency_map[stage_name] = dependency_entry
                global_init_stage_sequence.append(
                    {
                        "stage": stage_name,
                        **timing_entry,
                        **dependency_entry,
                    }
                )
                if cumulative_elapsed_ms is not None and global_init_total_ms is None:
                    global_init_total_ms = int(cumulative_elapsed_ms)
                if stage_elapsed_ms is not None and int(stage_elapsed_ms) > global_init_slowest_stage_ms:
                    global_init_slowest_stage_ms = int(stage_elapsed_ms)
                    global_init_slowest_stage = stage_name
            llm_init_stage_timing = {
                stage_name: dict(stage_payload)
                for stage_name, stage_payload in global_init_stage_timing.items()
                if stage_name.startswith("llm_init.")
            }
            llm_init_total_ms = None
            top_level_llm_init = global_init_stage_timing.get("llm_init")
            if isinstance(top_level_llm_init, dict):
                llm_init_total_ms = top_level_llm_init.get("stage_elapsed_ms")
            llm_init_slowest_stage = ""
            llm_init_slowest_stage_ms = -1
            for stage_name, stage_payload in llm_init_stage_timing.items():
                if not isinstance(stage_payload, dict):
                    continue
                stage_elapsed_ms = stage_payload.get("stage_elapsed_ms")
                if stage_elapsed_ms is None:
                    continue
                if int(stage_elapsed_ms) > llm_init_slowest_stage_ms:
                    llm_init_slowest_stage_ms = int(stage_elapsed_ms)
                    llm_init_slowest_stage = stage_name

            def _inference_relative(field_name: str) -> int | None:
                field_value = self.inference_stage_timing_ms.get(field_name)
                if field_value is None or attempt_started_at_ms is None:
                    return None
                return max(0, int(field_value) - int(attempt_started_at_ms))

            def _duration(begin_field: str, end_field: str) -> int | None:
                begin_value = self.inference_stage_timing_ms.get(begin_field)
                end_value = self.inference_stage_timing_ms.get(end_field)
                if begin_value is None or end_value is None:
                    return None
                return max(0, int(end_value) - int(begin_value))

            inference_stage_sequence = []
            for stage_name, field_name in self._inference_stage_definitions():
                inference_stage_sequence.append(
                    {
                        "stage": stage_name,
                        "status": self.inference_stage_status.get(stage_name, "pending"),
                        "elapsed_ms": _inference_relative(field_name),
                    }
                )

            inference_stage_timing = {
                "inference_runner_registration_begin_ms": _inference_relative("inference_runner_registration_begin_at_ms"),
                "inference_runner_registration_end_ms": _inference_relative("inference_runner_registration_end_at_ms"),
                "inference_proc_spawn_begin_ms": _inference_relative("inference_proc_spawn_begin_at_ms"),
                "inference_proc_spawn_end_ms": _inference_relative("inference_proc_spawn_end_at_ms"),
                "inference_child_boot_begin_ms": _inference_relative("inference_child_boot_begin_at_ms"),
                "inference_child_handshake_begin_ms": _inference_relative("inference_child_handshake_begin_at_ms"),
                "inference_child_handshake_end_ms": _inference_relative("inference_child_handshake_end_at_ms"),
                "inference_runner_construct_begin_ms": _inference_relative("inference_runner_construct_begin_at_ms"),
                "inference_runner_construct_end_ms": _inference_relative("inference_runner_construct_end_at_ms"),
                "inference_provider_import_begin_ms": _inference_relative("inference_provider_import_begin_at_ms"),
                "inference_provider_import_end_ms": _inference_relative("inference_provider_import_end_at_ms"),
                "inference_import_onnxruntime_begin_ms": _inference_relative("inference_import_onnxruntime_begin_at_ms"),
                "inference_import_onnxruntime_end_ms": _inference_relative("inference_import_onnxruntime_end_at_ms"),
                "inference_import_transformers_begin_ms": _inference_relative("inference_import_transformers_begin_at_ms"),
                "inference_import_transformers_end_ms": _inference_relative("inference_import_transformers_end_at_ms"),
                "inference_model_registry_load_begin_ms": _inference_relative("inference_model_registry_load_begin_at_ms"),
                "inference_model_registry_load_end_ms": _inference_relative("inference_model_registry_load_end_at_ms"),
                "inference_network_credential_probe_begin_ms": _inference_relative("inference_network_credential_probe_begin_at_ms"),
                "inference_network_credential_probe_end_ms": _inference_relative("inference_network_credential_probe_end_at_ms"),
                "inference_capability_probe_begin_ms": _inference_relative("inference_capability_probe_begin_at_ms"),
                "inference_capability_probe_end_ms": _inference_relative("inference_capability_probe_end_at_ms"),
                "inference_hf_cache_lookup_begin_ms": _inference_relative("inference_hf_cache_lookup_begin_at_ms"),
                "inference_hf_cache_lookup_end_ms": _inference_relative("inference_hf_cache_lookup_end_at_ms"),
                "inference_onnx_session_begin_ms": _inference_relative("inference_onnx_session_begin_at_ms"),
                "inference_onnx_session_end_ms": _inference_relative("inference_onnx_session_end_at_ms"),
                "inference_tokenizer_load_begin_ms": _inference_relative("inference_tokenizer_load_begin_at_ms"),
                "inference_tokenizer_load_end_ms": _inference_relative("inference_tokenizer_load_end_at_ms"),
                "inference_runner_initialize_end_ms": _inference_relative("inference_runner_initialize_end_at_ms"),
                "inference_child_ready_ms": _inference_relative("inference_child_ready_at_ms"),
                "inference_runner_registration_ms": _duration(
                    "inference_runner_registration_begin_at_ms",
                    "inference_runner_registration_end_at_ms",
                ),
                "inference_proc_spawn_ms": _duration("inference_proc_spawn_begin_at_ms", "inference_proc_spawn_end_at_ms"),
                "inference_child_handshake_ms": _duration(
                    "inference_child_handshake_begin_at_ms",
                    "inference_child_handshake_end_at_ms",
                ),
                "inference_runner_construct_ms": _duration(
                    "inference_runner_construct_begin_at_ms",
                    "inference_runner_construct_end_at_ms",
                ),
                "inference_provider_import_ms": _duration(
                    "inference_provider_import_begin_at_ms",
                    "inference_provider_import_end_at_ms",
                ),
                "inference_import_onnxruntime_ms": _duration(
                    "inference_import_onnxruntime_begin_at_ms",
                    "inference_import_onnxruntime_end_at_ms",
                ),
                "inference_import_transformers_ms": _duration(
                    "inference_import_transformers_begin_at_ms",
                    "inference_import_transformers_end_at_ms",
                ),
                "inference_model_registry_load_ms": _duration(
                    "inference_model_registry_load_begin_at_ms",
                    "inference_model_registry_load_end_at_ms",
                ),
                "inference_network_credential_probe_ms": _duration(
                    "inference_network_credential_probe_begin_at_ms",
                    "inference_network_credential_probe_end_at_ms",
                ),
                "inference_capability_probe_ms": _duration(
                    "inference_capability_probe_begin_at_ms",
                    "inference_capability_probe_end_at_ms",
                ),
                "inference_hf_cache_lookup_ms": _duration(
                    "inference_hf_cache_lookup_begin_at_ms",
                    "inference_hf_cache_lookup_end_at_ms",
                ),
                "inference_onnx_session_ms": _duration(
                    "inference_onnx_session_begin_at_ms",
                    "inference_onnx_session_end_at_ms",
                ),
                "inference_tokenizer_load_ms": _duration(
                    "inference_tokenizer_load_begin_at_ms",
                    "inference_tokenizer_load_end_at_ms",
                ),
            }
            inference_total_ms = _duration("inference_proc_spawn_begin_at_ms", "inference_child_ready_at_ms")
            duration_candidates = {
                key: inference_stage_timing.get(key)
                for key in (
                    "inference_runner_registration_ms",
                    "inference_proc_spawn_ms",
                    "inference_child_handshake_ms",
                    "inference_provider_import_ms",
                    "inference_runner_construct_ms",
                    "inference_import_onnxruntime_ms",
                    "inference_import_transformers_ms",
                    "inference_model_registry_load_ms",
                    "inference_network_credential_probe_ms",
                    "inference_capability_probe_ms",
                    "inference_hf_cache_lookup_ms",
                    "inference_onnx_session_ms",
                    "inference_tokenizer_load_ms",
                )
                if inference_stage_timing.get(key) is not None
            }
            inference_slowest_stage = ""
            if duration_candidates:
                inference_slowest_stage = max(duration_candidates.items(), key=lambda item: int(item[1] or 0))[0].removesuffix("_ms")
            median_upgrade_ms = None
            if self.turn_detection_upgrade_durations_ms:
                median_upgrade_ms = int(
                    statistics.median(float(value) for value in self.turn_detection_upgrade_durations_ms)
                )
            latest_room_state: dict[str, Any] = {}
            if self.last_room_joined_at_ms is not None:
                matching_states = [
                    room_state
                    for room_state in self._room_stage_by_room.values()
                    if room_state.get("room_joined_at_ms") == self.last_room_joined_at_ms
                ]
                if matching_states:
                    latest_room_state = dict(matching_states[-1])
            if not latest_room_state and self._room_stage_by_room:
                latest_room_state = dict(next(reversed(self._room_stage_by_room.values())))
            room_timing = self._room_state_timing_summary(latest_room_state)
            return {
                "ready": core_ready,
                "tier": "SESSION_CAPABLE" if core_ready else state,
                "state": state,
                "ready_predicates": ready_predicates,
                "ready_unmet_checks": [name for name, ok in ready_predicates.items() if not ok],
                "worker_alive": worker_heartbeat_fresh,
                "last_probe_ok": claim_probe_valid,
                "last_probe_age_ms": claim_probe_age_ms,
                "claim_probe_ttl_ms": self._claim_probe_ttl_ms(),
                "capability_ready": capability_ready,
                "checks": checks,
                "tiers": {
                    "core": {
                        "ready": core_ready,
                        "infra_ready": infra_ready,
                    },
                    "capability": {
                        "ready": capability_ready,
                        "initializing": self.capability_init_started and not self.capability_ready,
                        "failure_reason": self.capability_failure_reason,
                    },
                },
                "current_tier": (
                    "CAPABILITY"
                    if capability_ready and core_ready
                    else ("SESSION_CAPABLE" if core_ready else ("INFRA" if infra_ready else "BOOTING"))
                ),
                "timing": {
                    "boot_elapsed_ms": max(0, now_ms - self.boot_started_at_ms),
                    "last_worker_heartbeat_age_ms": heartbeat_age_ms,
                    "worker_connect_started_ms": (
                        max(0, self.worker_connect_started_at_ms - self.boot_started_at_ms)
                        if self.worker_connect_started_at_ms is not None
                        else None
                    ),
                    "worker_conn_task_started_ms": (
                        max(0, self.worker_conn_task_started_at_ms - self.boot_started_at_ms)
                        if self.worker_conn_task_started_at_ms is not None
                        else None
                    ),
                    "infra_ready_ms": (
                        max(0, self.infra_ready_at_ms - self.boot_started_at_ms)
                        if self.infra_ready_at_ms is not None
                        else None
                    ),
                    "core_ready_ms": (
                        max(0, self.core_ready_at_ms - self.boot_started_at_ms)
                        if self.core_ready_at_ms is not None
                        else None
                    ),
                    "worker_registered_ms": (
                        max(0, self.worker_registered_at_ms - self.boot_started_at_ms)
                        if self.worker_registered_at_ms is not None
                        else None
                    ),
                    "worker_connect_error_ms": (
                        max(0, self.worker_connect_error_at_ms - self.boot_started_at_ms)
                        if self.worker_connect_error_at_ms is not None
                        else None
                    ),
                    "claimable_ready_ms": (
                        max(0, self.claimable_ready_at_ms - self.boot_started_at_ms)
                        if self.claimable_ready_at_ms is not None
                        else None
                    ),
                    "capability_ready_ms": (
                        max(0, self.capability_ready_at_ms - self.boot_started_at_ms)
                        if self.capability_ready_at_ms is not None
                        else None
                    ),
                    "claim_probe_ms": (
                        max(0, self.last_claim_probe_at_ms - self.claim_probe_started_at_ms)
                        if self.last_claim_probe_at_ms is not None and self.claim_probe_started_at_ms is not None
                        else None
                    ),
                    "first_session_ready_ms": (
                        max(0, self.last_session_ready_at_ms - self.boot_started_at_ms)
                        if self.last_session_ready_at_ms is not None
                        else None
                    ),
                    "worker_job_claimed_ms": (
                        max(0, self.last_worker_claim_at_ms - self.boot_started_at_ms)
                        if self.last_worker_claim_at_ms is not None
                        else None
                    ),
                    "room_joined_ms": (
                        max(0, self.last_room_joined_at_ms - self.boot_started_at_ms)
                        if self.last_room_joined_at_ms is not None
                        else None
                    ),
                    "session_started_ms": (
                        max(0, self.last_session_started_at_ms - self.boot_started_at_ms)
                        if self.last_session_started_at_ms is not None
                        else None
                    ),
                    "session_ready_ms": (
                        max(0, self.last_session_ready_at_ms - self.boot_started_at_ms)
                        if self.last_session_ready_at_ms is not None
                        else None
                    ),
                    "phase1_runtime_build_ms": room_timing.get("phase1_runtime_build_ms"),
                    "phase1_runtime_llm_ms": room_timing.get("phase1_runtime_llm_ms"),
                    "phase1_runtime_stt_ms": room_timing.get("phase1_runtime_stt_ms"),
                    "phase1_runtime_tts_ms": room_timing.get("phase1_runtime_tts_ms"),
                    "phase1_runtime_vad_ms": room_timing.get("phase1_runtime_vad_ms"),
                    "voice_agent_create_ms": room_timing.get("voice_agent_create_ms"),
                    "session_object_create_ms": room_timing.get("session_object_create_ms"),
                    "pre_session_start_gap_ms": room_timing.get("pre_session_start_gap_ms"),
                    "session_start_transport_attach_ms": room_timing.get("session_start_transport_attach_ms"),
                    "listener_attach_ts_ms": latest_room_state.get("listener_attach_ts_ms"),
                    "track_subscribed_emit_ts_ms": latest_room_state.get("track_subscribed_emit_ts_ms"),
                    "track_subscribed_consume_ts_ms": latest_room_state.get("track_subscribed_consume_ts_ms"),
                    "startup_gate_classification": latest_room_state.get("startup_gate_classification", ""),
                    "teardown_begin_ts_ms": latest_room_state.get("teardown_begin_ts_ms"),
                    "teardown_ipc_closed_ts_ms": latest_room_state.get("teardown_ipc_closed_ts_ms"),
                    "teardown_to_ipc_close_ms": room_timing.get("teardown_to_ipc_close_ms"),
                    "teardown_to_callback_gap_ms": room_timing.get("teardown_to_callback_gap_ms"),
                    "session_start_room_media_bind_ms": room_timing.get("session_start_room_media_bind_ms"),
                    "participant_wait_ms": room_timing.get("participant_wait_ms"),
                    "publish_wait_ms": room_timing.get("publish_wait_ms"),
                    "local_track_subscribed_wait_ms": room_timing.get("local_track_subscribed_wait_ms"),
                    "subscribe_wait_ms": room_timing.get("subscribe_wait_ms"),
                    "audio_output_start_ms": room_timing.get("audio_output_start_ms"),
                    "first_audio_packet_ms": room_timing.get("first_audio_packet_ms"),
                    "synced_audio_frame_wait_ms": room_timing.get("synced_audio_frame_wait_ms"),
                    "participant_audio_frame_wait_ms": room_timing.get("participant_audio_frame_wait_ms"),
                    "transport_frame_ingress_ms": room_timing.get("transport_frame_ingress_ms"),
                    "transport_frame_processed_ms": room_timing.get("transport_frame_processed_ms"),
                    "first_pcm_frame_ms": room_timing.get("first_pcm_frame_ms"),
                    "total_media_bind_ms": room_timing.get("total_media_bind_ms"),
                    "media_bind_probe_registration_state": latest_room_state.get("media_bind_probe_registration_state", ""),
                    "media_bind_probe_source_path": latest_room_state.get("media_bind_probe_source_path", ""),
                    "media_bind_probe_room_io_id": latest_room_state.get("media_bind_probe_room_io_id", ""),
                    "media_bind_probe_audio_output_id": latest_room_state.get("media_bind_probe_audio_output_id", ""),
                    "active_room_io_id": latest_room_state.get("active_room_io_id", ""),
                    "active_audio_output_id": latest_room_state.get("active_audio_output_id", ""),
                    "attached_callback_target_id": latest_room_state.get("attached_callback_target_id", ""),
                    "callback_fired_source_id": latest_room_state.get("callback_fired_source_id", ""),
                    "callback_processed_source_id": latest_room_state.get("callback_processed_source_id", ""),
                    "callback_emitted_source_id": latest_room_state.get("callback_emitted_source_id", ""),
                    "callback_discard_reason": latest_room_state.get("callback_discard_reason", ""),
                    "lineage_switch_count": int(latest_room_state.get("lineage_switch_count") or 0),
                    "lineage_path_state": latest_room_state.get("lineage_path_state", ""),
                    "lineage_instance_mismatch": bool(latest_room_state.get("lineage_instance_mismatch")),
                    "active_audio_output_chain_ids": list(latest_room_state.get("active_audio_output_chain_ids", [])),
                    "active_audio_output_chain_classes": list(latest_room_state.get("active_audio_output_chain_classes", [])),
                    "attached_callback_target_chain_ids": list(latest_room_state.get("attached_callback_target_chain_ids", [])),
                    "attached_callback_target_chain_classes": list(latest_room_state.get("attached_callback_target_chain_classes", [])),
                    "callback_fired_source_chain_ids": list(latest_room_state.get("callback_fired_source_chain_ids", [])),
                    "callback_fired_source_chain_classes": list(latest_room_state.get("callback_fired_source_chain_classes", [])),
                    "callback_processed_source_chain_ids": list(latest_room_state.get("callback_processed_source_chain_ids", [])),
                    "callback_processed_source_chain_classes": list(latest_room_state.get("callback_processed_source_chain_classes", [])),
                    "callback_emitted_source_chain_ids": list(latest_room_state.get("callback_emitted_source_chain_ids", [])),
                    "callback_emitted_source_chain_classes": list(latest_room_state.get("callback_emitted_source_chain_classes", [])),
                    "active_audio_output_seen_at_ms": latest_room_state.get("active_audio_output_seen_at_ms"),
                    "attached_callback_target_seen_at_ms": latest_room_state.get("attached_callback_target_seen_at_ms"),
                    "callback_fired_source_seen_at_ms": latest_room_state.get("callback_fired_source_seen_at_ms"),
                    "callback_processed_source_seen_at_ms": latest_room_state.get("callback_processed_source_seen_at_ms"),
                    "callback_emitted_source_seen_at_ms": latest_room_state.get("callback_emitted_source_seen_at_ms"),
                    "callback_discarded_at_ms": latest_room_state.get("callback_discarded_at_ms"),
                    "lineage_active_to_attached_link": latest_room_state.get("lineage_active_to_attached_link", ""),
                    "lineage_attached_to_fired_link": latest_room_state.get("lineage_attached_to_fired_link", ""),
                    "interactive_start_probe_seen": bool(latest_room_state.get("interactive_start_probe_seen")),
                    "last_media_bind_probe_stage": latest_room_state.get("last_media_bind_probe_stage", ""),
                    "media_bind_timeout_class": latest_room_state.get("media_bind_timeout_class", ""),
                    "active_to_attached_ms": room_timing.get("active_to_attached_ms"),
                    "attached_to_fired_ms": room_timing.get("attached_to_fired_ms"),
                    "session_start_agent_graph_ms": room_timing.get("session_start_agent_graph_ms"),
                    "session_start_audio_pipeline_ms": room_timing.get("session_start_audio_pipeline_ms"),
                    "session_start_client_events_ms": room_timing.get("session_start_client_events_ms"),
                    "session_start_first_stream_ready_ms": room_timing.get("session_start_first_stream_ready_ms"),
                },
                "worker_connect_stage": self.worker_connect_stage,
                "worker_connect_attempt": self.worker_connect_attempt,
                "active_worker_attempt": self.active_worker_attempt,
                "last_invalidated_worker_attempt": self.last_invalidated_worker_attempt,
                "worker_connect_error_type": self.worker_connect_error_type or "",
                "worker_connect_error_message": self.worker_connect_error_message or "",
                "worker_connect_timeout_reason": self.worker_connect_timeout_reason or "",
                "worker_connect_retry_reason": self.worker_connect_retry_reason or "",
                "worker_connect_error_stage": self.worker_connect_error_stage or "",
                "stale_worker_started_count": self.stale_worker_started_count,
                "stale_worker_registered_count": self.stale_worker_registered_count,
                "stale_worker_claim_count": self.stale_worker_claim_count,
                "late_active_worker_registered_count": self.late_active_worker_registered_count,
                "last_stale_callback_ms": self.last_stale_callback_ms,
                "last_late_active_callback_ms": self.last_late_active_callback_ms,
                "active_attempt_timing": {
                    "attempt_started_ms": 0 if attempt_started_at_ms is not None else None,
                    "attempt_elapsed_ms": (
                        max(0, now_ms - int(attempt_started_at_ms))
                        if attempt_started_at_ms is not None and self.active_worker_attempt
                        else None
                    ),
                    "credentials_begin_ms": _attempt_relative("credentials_begin_at_ms"),
                    "credentials_end_ms": _attempt_relative("credentials_end_at_ms"),
                    "server_created_ms": _attempt_relative("server_created_at_ms"),
                    "server_run_enter_ms": _attempt_relative("server_run_enter_at_ms"),
                    "worker_started_ms": _attempt_relative("worker_started_at_ms"),
                    "worker_registered_ms": _attempt_relative("worker_registered_at_ms"),
                    "claim_probe_sent_ms": _attempt_relative("claim_probe_sent_at_ms"),
                    "claim_probe_claimed_ms": _attempt_relative("claim_probe_claimed_at_ms"),
                    "claim_probe_passed_ms": _attempt_relative("claim_probe_passed_at_ms"),
                    "runtime_ready_ms": _attempt_relative("runtime_ready_at_ms"),
                    "registration_ms": registration_ms,
                    "registered_to_ready_ms": registered_to_ready_ms,
                },
                "active_attempt_boot_timing": {
                    "attempt_started_ms": 0 if attempt_started_at_ms is not None else None,
                    "attempt_elapsed_ms": (
                        max(0, now_ms - int(attempt_started_at_ms))
                        if attempt_started_at_ms is not None and self.active_worker_attempt
                        else None
                    ),
                    "credentials_begin_ms": _attempt_relative("credentials_begin_at_ms"),
                    "credentials_end_ms": _attempt_relative("credentials_end_at_ms"),
                    "server_created_ms": _attempt_relative("server_created_at_ms"),
                    "worker_run_enter_ms": _attempt_relative("worker_run_enter_at_ms"),
                    "worker_network_connect_begin_ms": _attempt_relative("worker_network_connect_begin_at_ms"),
                    "worker_auth_begin_ms": _attempt_relative("worker_auth_begin_at_ms"),
                    "worker_registration_begin_ms": _attempt_relative("worker_registration_begin_at_ms"),
                    "plugin_preload_begin_ms": _attempt_relative("plugin_preload_begin_at_ms"),
                    "plugin_preload_end_ms": _attempt_relative("plugin_preload_end_at_ms"),
                    "inference_executor_start_begin_ms": _attempt_relative("inference_executor_start_begin_at_ms"),
                    "inference_executor_start_end_ms": _attempt_relative("inference_executor_start_end_at_ms"),
                    "inference_executor_initialize_begin_ms": _attempt_relative("inference_executor_initialize_begin_at_ms"),
                    "inference_executor_initialize_end_ms": _attempt_relative("inference_executor_initialize_end_at_ms"),
                    "http_server_start_begin_ms": _attempt_relative("http_server_start_begin_at_ms"),
                    "http_server_start_end_ms": _attempt_relative("http_server_start_end_at_ms"),
                    "proc_pool_start_begin_ms": _attempt_relative("proc_pool_start_begin_at_ms"),
                    "proc_pool_start_end_ms": _attempt_relative("proc_pool_start_end_at_ms"),
                    "proc_pool_process_created_ms": _attempt_relative("proc_pool_process_created_at_ms"),
                    "proc_pool_process_started_ms": _attempt_relative("proc_pool_process_started_at_ms"),
                    "proc_pool_process_ready_ms": _attempt_relative("proc_pool_process_ready_at_ms"),
                    "worker_conn_task_scheduled_ms": _attempt_relative("worker_conn_task_scheduled_at_ms"),
                    "worker_started_event_ms": _attempt_relative("worker_started_event_at_ms"),
                    "worker_registered_event_ms": _attempt_relative("worker_registered_event_at_ms"),
                    "worker_heartbeat_first_seen_ms": _attempt_relative("worker_heartbeat_first_seen_at_ms"),
                },
                "boot_blocker_stage": boot_blocker_stage,
                "boot_stage_sequence": boot_stage_sequence,
                "global_init_stage_timing": global_init_stage_timing,
                "global_init_total_ms": global_init_total_ms,
                "global_init_slowest_stage": global_init_slowest_stage,
                "global_init_stage_sequence": global_init_stage_sequence,
                "global_init_dependency_map": global_init_dependency_map,
                "llm_init_stage_timing": llm_init_stage_timing,
                "llm_init_total_ms": llm_init_total_ms,
                "llm_init_slowest_stage": llm_init_slowest_stage,
                "semantic_memory_ready": self.semantic_memory_ready,
                "vector_store_warming": self.semantic_memory_warming,
                "semantic_memory_boot_mode": self.semantic_memory_boot_mode,
                "semantic_memory_error": self.semantic_memory_error,
                "semantic_memory_ready_ms": (
                    max(0, self.semantic_memory_ready_at_ms - self.boot_started_at_ms)
                    if self.semantic_memory_ready_at_ms is not None
                    else None
                ),
                "semantic_memory_query_degraded_count": self.semantic_memory_query_degraded_count,
                "semantic_memory_add_deferred_count": self.semantic_memory_add_deferred_count,
                "llm_fallback_ready": self.llm_fallback_ready,
                "llm_fallback_warming": self.llm_fallback_warming,
                "llm_fallback_boot_mode": self.llm_fallback_boot_mode,
                "llm_fallback_error": self.llm_fallback_error,
                "llm_fallback_ready_ms": (
                    max(0, self.llm_fallback_ready_at_ms - self.boot_started_at_ms)
                    if self.llm_fallback_ready_at_ms is not None
                    else None
                ),
                "inference_stage_timing": inference_stage_timing,
                "inference_total_ms": inference_total_ms,
                "inference_slowest_stage": inference_slowest_stage,
                "inference_runner_names": list(self.inference_runner_names),
                "inference_stage_sequence": inference_stage_sequence,
                "enhanced_turn_detection_ready": self.enhanced_turn_detection_ready,
                "enhanced_turn_detection_mode": self.enhanced_turn_detection_mode,
                "eou_registration_state": self.eou_registration_state,
                "eou_registration_error": self.eou_registration_error,
                "eou_init_thread_handoff_count": self.eou_init_thread_handoff_count,
                "eou_init_main_thread_success": self.eou_init_main_thread_success,
                "eou_init_main_thread_fail": self.eou_init_main_thread_fail,
                "eou_upgrade_success": self.eou_upgrade_success,
                "onnx_init_state": self.onnx_init_state,
                "onnx_init_error": self.onnx_init_error,
                "onnx_background_ready_ms": (
                    max(0, self.onnx_background_ready_at_ms - self.boot_started_at_ms)
                    if self.onnx_background_ready_at_ms is not None
                    else None
                ),
                "onnx_first_use_wait_ms": self.onnx_first_use_wait_ms,
                "sessions_started_on_stt": self.sessions_started_on_stt,
                "sessions_upgraded_to_eou": self.sessions_upgraded_to_eou,
                "sessions_completed_without_eou": self.sessions_completed_without_eou,
                "upgrade_failures": self.upgrade_failures,
                "median_upgrade_ms": median_upgrade_ms,
                "inference_runner_timing": {
                    runner_name: {
                        field_name.removesuffix("_at_ms") + "_ms": (
                            max(0, int(field_value) - int(attempt_started_at_ms))
                            if field_value is not None and attempt_started_at_ms is not None
                            else None
                        )
                        for field_name, field_value in runner_timing.items()
                    }
                    for runner_name, runner_timing in self.inference_runner_timing_ms.items()
                },
                "probe": {
                    "room": self.claim_probe_room_name,
                    "stage": self.claim_probe_stage,
                    "status": self.claim_probe_status,
                    "elapsed_ms": (
                        max(0, now_ms - self.claim_probe_started_at_ms)
                        if self.claim_probe_started_at_ms is not None and self.claimable_ready_at_ms is None
                        else (
                            max(0, self.last_claim_probe_at_ms - self.claim_probe_started_at_ms)
                            if self.last_claim_probe_at_ms is not None and self.claim_probe_started_at_ms is not None
                            else None
                        )
                    ),
                    "timeout_budget_ms": self.claim_probe_timeout_budget_ms,
                    "failure_reason": self.claim_probe_failure_reason or "",
                    "last_claim_probe_at_ms": self.last_claim_probe_at_ms,
                    "last_claim_probe_error": self.last_claim_probe_error,
                },
                "session": {
                    "active_session_count": self.active_session_count,
                    "last_worker_claim_at_ms": self.last_worker_claim_at_ms,
                    "last_room_joined_at_ms": self.last_room_joined_at_ms,
                    "last_session_started_at_ms": self.last_session_started_at_ms,
                    "last_session_ready_at_ms": self.last_session_ready_at_ms,
                    "last_session_failure_at_ms": self.last_session_failure_at_ms,
                    "last_session_failure_reason": self.last_session_failure_reason or "",
                    "last_session_failure_taxonomy": latest_room_state.get("session_failure_taxonomy", ""),
                    "last_session_failure_timeout_class": latest_room_state.get("session_failure_timeout_class", ""),
                    "last_worker_disconnect_at_ms": self.last_worker_disconnect_at_ms,
                },
                "build": {
                    "version": self.version,
                    "mode": self.mode,
                },
                "error": {
                    "worker_connect_error_type": self.worker_connect_error_type or "",
                    "worker_connect_error_message": self.worker_connect_error_message or "",
                },
                "cycle_id": self.cycle_id,
            }


_READINESS_TRACKER: RuntimeReadinessTracker | None = None


def get_runtime_readiness_tracker() -> RuntimeReadinessTracker:
    global _READINESS_TRACKER
    if _READINESS_TRACKER is None:
        _READINESS_TRACKER = RuntimeReadinessTracker()
    return _READINESS_TRACKER
