import 'dart:async';
import 'dart:convert';
import 'dart:io';

enum IdeAgenticConnectionState {
  idle,
  connecting,
  connected,
  reconnecting,
  error,
  closed,
}

class IdeAgenticEvent {
  const IdeAgenticEvent({
    required this.seq,
    required this.eventType,
    required this.timestamp,
    required this.payload,
    this.sessionId,
    this.traceId,
    this.taskId,
    this.agentId,
    this.status,
  });

  final int seq;
  final String eventType;
  final double timestamp;
  final String? sessionId;
  final String? traceId;
  final String? taskId;
  final String? agentId;
  final String? status;
  final Map<String, dynamic> payload;

  factory IdeAgenticEvent.fromJson(Map<String, dynamic> json) {
    return IdeAgenticEvent(
      seq: json['seq'] is int ? json['seq'] as int : int.tryParse('${json['seq']}') ?? 0,
      eventType: (json['event_type'] ?? '').toString(),
      timestamp: json['timestamp'] is num
          ? (json['timestamp'] as num).toDouble()
          : double.tryParse('${json['timestamp']}') ?? 0.0,
      sessionId: json['session_id']?.toString(),
      traceId: json['trace_id']?.toString(),
      taskId: json['task_id']?.toString(),
      agentId: json['agent_id']?.toString(),
      status: json['status']?.toString(),
      payload: json['payload'] is Map<String, dynamic>
          ? json['payload'] as Map<String, dynamic>
          : Map<String, dynamic>.from(json['payload'] as Map? ?? const <String, dynamic>{}),
    );
  }
}

class IdeAgenticService {
  IdeAgenticService();

  static const List<String> _wsBases = <String>[
    'ws://127.0.0.1:5050',
    'ws://localhost:5050',
  ];

  final StreamController<IdeAgenticEvent> _eventsController =
      StreamController<IdeAgenticEvent>.broadcast(sync: true);
  final StreamController<IdeAgenticConnectionState> _stateController =
      StreamController<IdeAgenticConnectionState>.broadcast(sync: true);

  WebSocket? _socket;
  Timer? _reconnectTimer;

  String? _sessionId;
  bool _started = false;
  bool _manualClose = false;
  int _lastSeq = 0;
  int _reconnectAttempt = 0;
  IdeAgenticConnectionState _connectionState = IdeAgenticConnectionState.idle;
  String? _lastError;

  Stream<IdeAgenticEvent> get events => _eventsController.stream;
  Stream<IdeAgenticConnectionState> get stateStream => _stateController.stream;

  IdeAgenticConnectionState get connectionState => _connectionState;
  int get lastSeq => _lastSeq;
  String? get lastError => _lastError;

  Future<void> start({String? sessionId}) async {
    _started = true;
    _manualClose = false;
    _sessionId = sessionId?.trim().isEmpty ?? true ? null : sessionId!.trim();
    await _connect(isReconnect: false);
  }

  Future<void> stop() async {
    _manualClose = true;
    _started = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    try {
      await _socket?.close();
    } catch (_) {}
    _socket = null;
    _setState(IdeAgenticConnectionState.closed);
  }

  Future<void> dispose() async {
    await stop();
    await _eventsController.close();
    await _stateController.close();
  }

  Future<void> _connect({required bool isReconnect}) async {
    if (!_started) return;
    _setState(isReconnect ? IdeAgenticConnectionState.reconnecting : IdeAgenticConnectionState.connecting);

    Object? lastError;
    for (final base in _wsBases) {
      final query = <String, String>{
        'after_seq': '$_lastSeq',
        'limit': '500',
        if (_sessionId != null) 'session_id': _sessionId!,
      };
      final uri = Uri.parse('$base/ide/events/stream').replace(queryParameters: query);
      try {
        final socket = await WebSocket.connect(uri.toString());
        _socket = socket;
        _reconnectAttempt = 0;
        _lastError = null;
        _setState(IdeAgenticConnectionState.connected);

        socket.listen(
          _onSocketMessage,
          onError: (Object error) {
            _lastError = error.toString();
            _setState(IdeAgenticConnectionState.error);
            _scheduleReconnect();
          },
          onDone: () {
            if (_manualClose) {
              _setState(IdeAgenticConnectionState.closed);
              return;
            }
            _scheduleReconnect();
          },
          cancelOnError: false,
        );
        return;
      } catch (e) {
        lastError = e;
      }
    }

    _lastError = '$lastError';
    _setState(IdeAgenticConnectionState.error);
    _scheduleReconnect();
  }

  void _onSocketMessage(dynamic raw) {
    if (raw == null) return;
    try {
      final decoded = jsonDecode(raw as String);
      if (decoded is! Map<String, dynamic>) {
        return;
      }
      final event = IdeAgenticEvent.fromJson(decoded);
      if (event.seq > _lastSeq) {
        _lastSeq = event.seq;
      }
      _eventsController.add(event);
    } catch (_) {
      // Keep stream alive on malformed payloads.
    }
  }

  void _scheduleReconnect() {
    if (_manualClose || !_started) return;
    if (_reconnectTimer != null) return;

    _socket = null;
    _reconnectAttempt += 1;
    final delaySeconds = _backoffSeconds(_reconnectAttempt);
    _setState(IdeAgenticConnectionState.reconnecting);

    _reconnectTimer = Timer(Duration(seconds: delaySeconds), () async {
      _reconnectTimer = null;
      if (!_started || _manualClose) return;
      await _connect(isReconnect: true);
    });
  }

  int _backoffSeconds(int attempt) {
    if (attempt <= 1) return 1;
    if (attempt == 2) return 2;
    if (attempt == 3) return 4;
    if (attempt == 4) return 8;
    return 15;
  }

  void _setState(IdeAgenticConnectionState state) {
    if (_connectionState == state) return;
    _connectionState = state;
    _stateController.add(state);
  }
}
