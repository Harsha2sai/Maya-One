import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/events/agent_event_models.dart';
import 'orb_controller.dart';

enum VoiceUiState {
  idle,
  listening,
  thinking,
  toolRunning,
  speaking,
  greeting,
  interrupted,
  bootstrapping,
  offline,
  reconnecting,
}

class AgentTask {
  final String id;
  final String name;
  String status;
  final DateTime startTime;
  DateTime? endTime;
  String? result;

  AgentTask({
    required this.id,
    required this.name,
    required this.status,
    required this.startTime,
    this.endTime,
    this.result,
  });
}

class AgentLog {
  final DateTime timestamp;
  final String message;
  final String level;

  AgentLog({
    required this.timestamp,
    required this.message,
    this.level = 'info',
  });
}

class AgentActivityController extends ChangeNotifier {
  StreamSubscription<AgentUiEvent>? _subscription;
  Stream<AgentUiEvent>? _boundAgentEvents;
  OrbController? _orbController;
  VoiceUiState _voiceUiState = VoiceUiState.idle;
  String? _activeToolName;
  String? _activeTaskId;

  final List<AgentTask> _tasks = [];
  final List<AgentLog> _logs = [];

  AgentActivityController({Stream<AgentUiEvent>? agentEvents, OrbController? orbController}) {
    _orbController = orbController;
    if (agentEvents != null) {
      bind(agentEvents);
    }
  }

  VoiceUiState get voiceUiState => _voiceUiState;
  String? get activeToolName => _activeToolName;
  String? get activeTaskId => _activeTaskId;
  List<AgentTask> get tasks => List.unmodifiable(_tasks);
  List<AgentLog> get logs => List.unmodifiable(_logs);

  void bind(Stream<AgentUiEvent> agentEvents) {
    if (identical(_boundAgentEvents, agentEvents)) {
      return;
    }
    _boundAgentEvents = agentEvents;
    unawaited(_subscription?.cancel());
    _subscription = agentEvents.listen(_handleEvent);
  }

  void bindOrb(OrbController orbController) {
    if (identical(_orbController, orbController)) {
      return;
    }
    _orbController = orbController;
  }

  @visibleForTesting
  void ingestForTesting(AgentUiEvent event) {
    _handleEvent(event);
  }

  void _addLog(String message, {String level = 'info'}) {
    _logs.add(AgentLog(timestamp: DateTime.now(), message: message, level: level));
    if (_logs.length > 1000) _logs.removeAt(0);
  }

  void _handleEvent(AgentUiEvent event) {
    final eventTime = DateTime.fromMillisecondsSinceEpoch(event.timestamp);

    switch (event.eventType) {
      case 'session_connected':
        _setVoiceState(VoiceUiState.idle);
        _addLog('Session connected');
        break;
      case 'session_disconnected':
        _setVoiceState(VoiceUiState.offline);
        _addLog('Session disconnected', level: 'warning');
        break;
      case 'session_reconnecting':
        _setVoiceState(VoiceUiState.reconnecting);
        _addLog('Session reconnecting', level: 'warning');
        break;
      case 'track_subscribed':
        _setVoiceState(VoiceUiState.greeting);
        _addLog('Audio track subscribed');
        break;
      case 'bootstrap_started':
        _setVoiceState(VoiceUiState.bootstrapping);
        _addLog('Bootstrap started');
        break;
      case 'bootstrap_acknowledged':
      case 'bootstrap_timeout':
        _setVoiceState(VoiceUiState.idle);
        _addLog('Bootstrap completed');
        break;
      case 'user_speaking':
        _setVoiceState(VoiceUiState.listening);
        _addLog('User speaking');
        break;
      case 'user_silence':
        if (_voiceUiState == VoiceUiState.listening) {
          _setVoiceState(VoiceUiState.idle);
          _addLog('User silence');
        }
        break;
      case 'agent_speaking':
        final status = event.payload['status']?.toString();
        _setVoiceState(status == 'idle' ? VoiceUiState.idle : VoiceUiState.speaking);
        if (status != 'idle') _addLog('Agent speaking');
        break;
      case 'agent_interrupted':
        _setVoiceState(VoiceUiState.interrupted);
        _addLog('Agent interrupted', level: 'warning');
        break;
      case 'agent_idle':
        _setVoiceState(VoiceUiState.idle);
        break;
      case 'agent_thinking':
        _setVoiceState(VoiceUiState.thinking);
        _addLog('Agent thinking');
        break;
      case 'tool_execution':
        final toolName = (event.payload['tool_name'] ?? event.payload['tool'])?.toString() ?? 'unknown_tool';
        _activeToolName = toolName;
        final taskId = event.taskId ?? 'unknown_task';
        _activeTaskId = taskId;
        final status = event.payload['status']?.toString().toLowerCase() ?? '';

        // Update tasks list
        final existingTaskIndex = _tasks.indexWhere((t) => t.id == taskId);
        if (existingTaskIndex >= 0) {
          _tasks[existingTaskIndex].status = status;
          if (status == 'finished' || status == 'failed' || status == 'completed') {
            _tasks[existingTaskIndex].endTime = eventTime;
            _tasks[existingTaskIndex].result = event.payload['result']?.toString();
          }
        } else {
          _tasks.add(AgentTask(
            id: taskId,
            name: toolName,
            status: status.isEmpty ? 'started' : status,
            startTime: eventTime,
          ));
        }

        _addLog('Tool $toolName: $status');

        if (status == 'running' || status == 'started' || status == 'in_progress') {
          _setVoiceState(VoiceUiState.toolRunning, notify: false);
        } else if (_voiceUiState == VoiceUiState.toolRunning) {
          _setVoiceState(VoiceUiState.thinking, notify: false);
        }
        notifyListeners();
        break;
      default:
        break;
    }
  }

  void _setVoiceState(VoiceUiState nextState, {bool notify = true}) {
    if (_voiceUiState == nextState) {
      return;
    }
    _voiceUiState = nextState;
    if (notify) {
      notifyListeners();
    }
  }

  @override
  void dispose() {
    unawaited(_subscription?.cancel());
    super.dispose();
  }
}
