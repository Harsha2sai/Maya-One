import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

/// Live terminal bridge for IDE tab.
///
/// Flow:
/// 1) Open IDE session via POST /ide/session/open
/// 2) Open terminal via POST /ide/terminal/open
/// 3) Connect WebSocket /ws/terminal?session_id=...&token=...
/// 4) Stream output chunks + forward user input to PTY
class IdeTerminalService {
  IdeTerminalService({
    http.Client? client,
    this.maxOutputChars = 200000,
  }) : _client = client ?? http.Client();

  final http.Client _client;
  final int maxOutputChars;

  static const List<String> _httpBases = <String>[
    'http://127.0.0.1:5050',
    'http://localhost:5050',
  ];

  final StreamController<String> _outputController =
      StreamController<String>.broadcast(sync: true);
  final StreamController<IdeTerminalStatus> _statusController =
      StreamController<IdeTerminalStatus>.broadcast(sync: true);

  WebSocket? _socket;
  Timer? _pingTimer;
  Timer? _reconnectTimer;

  String? _baseHttp;
  String? _ideSessionId;
  String? _terminalSessionId;
  String? _token;
  String? _wsUrl;
  String? _lastError;

  String _userId = 'guest-local';
  String _workspacePath = '.';
  String _cwd = '~';
  int _reconnectAttempt = 0;
  bool _started = false;
  bool _manualClose = false;

  IdeTerminalStatus _status = IdeTerminalStatus.idle;

  Stream<String> get outputStream => _outputController.stream;
  Stream<IdeTerminalStatus> get statusStream => _statusController.stream;

  IdeTerminalStatus get status => _status;
  String? get ideSessionId => _ideSessionId;
  String? get terminalSessionId => _terminalSessionId;
  String? get lastError => _lastError;

  Future<void> start({
    required String userId,
    required String workspacePath,
    String cwd = '~',
  }) async {
    _manualClose = false;
    _started = true;
    _userId = userId.trim().isEmpty ? 'guest-local' : userId;
    _workspacePath = workspacePath.trim().isEmpty ? '.' : workspacePath;
    _cwd = cwd;

    _setStatus(IdeTerminalStatus.opening);
    await _ensureIdeSession();
    await _openTerminalSession();
    await _connectWebSocket();
  }

  Future<void> stop() async {
    _manualClose = true;
    _started = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _pingTimer?.cancel();
    _pingTimer = null;

    try {
      await _socket?.close();
    } catch (_) {}
    _socket = null;

    await _safeCloseTerminalSession();
    await _safeCloseIdeSession();

    _setStatus(IdeTerminalStatus.closed);
  }

  Future<void> sendInput(String input) async {
    if (_socket == null) return;
    final payload = jsonEncode(<String, dynamic>{
      'type': 'input',
      'text': input,
    });

    try {
      _socket!.add(payload);
    } catch (e) {
      _lastError = e.toString();
      _setStatus(IdeTerminalStatus.error);
      _scheduleReconnect();
    }
  }

  Future<void> sendResize({required int rows, required int cols}) async {
    if (_socket == null) return;
    final payload = jsonEncode(<String, dynamic>{
      'type': 'resize',
      'rows': rows,
      'cols': cols,
    });

    try {
      _socket!.add(payload);
    } catch (_) {}
  }

  Future<void> dispose() async {
    await stop();
    await _outputController.close();
    await _statusController.close();
    _client.close();
  }

  Future<void> _ensureIdeSession() async {
    if (_ideSessionId != null && _ideSessionId!.isNotEmpty) {
      return;
    }

    final body = jsonEncode(<String, dynamic>{
      'workspace_path': _workspacePath,
      'user_id': _userId,
    });

    final result = await _postJson('/ide/session/open', body);
    _ideSessionId = (result['session_id'] ?? '').toString();
    if (_ideSessionId == null || _ideSessionId!.isEmpty) {
      throw StateError('Missing ide session id from /ide/session/open');
    }
  }

  Future<void> _openTerminalSession({bool refresh = false}) async {
    if (_ideSessionId == null || _ideSessionId!.isEmpty) {
      throw StateError('IDE session is not available');
    }

    if (refresh && _terminalSessionId != null) {
      await _safeCloseTerminalSession();
    }

    final body = jsonEncode(<String, dynamic>{
      'ide_session_id': _ideSessionId,
      'user_id': _userId,
      'cwd': _cwd,
    });

    final result = await _postJson('/ide/terminal/open', body);
    _terminalSessionId = (result['session_id'] ?? '').toString();
    _token = (result['token'] ?? '').toString();
    _wsUrl = (result['ws_url'] ?? '').toString();

    if ((_terminalSessionId ?? '').isEmpty || (_token ?? '').isEmpty || (_wsUrl ?? '').isEmpty) {
      throw StateError('Missing terminal websocket fields from /ide/terminal/open');
    }
  }

  Future<void> _connectWebSocket() async {
    if (!_started) return;

    _setStatus(_reconnectAttempt == 0 ? IdeTerminalStatus.connecting : IdeTerminalStatus.reconnecting);

    final wsUrl = _resolveWsUrl();
    try {
      final socket = await WebSocket.connect(wsUrl);
      _socket = socket;
      _reconnectAttempt = 0;
      _lastError = null;

      _setStatus(IdeTerminalStatus.connected);
      _startPingLoop();

      socket.listen(
        _handleWsMessage,
        onError: (Object error) {
          _lastError = error.toString();
          _setStatus(IdeTerminalStatus.error);
          _scheduleReconnect();
        },
        onDone: () {
          if (_manualClose) {
            _setStatus(IdeTerminalStatus.closed);
            return;
          }
          _scheduleReconnect();
        },
        cancelOnError: false,
      );
    } catch (e) {
      _lastError = e.toString();
      _setStatus(IdeTerminalStatus.error);

      // Token/session could be stale after long disconnect; refresh and retry.
      if (_looksLikeAuthFailure(e.toString())) {
        try {
          await _openTerminalSession(refresh: true);
        } catch (_) {}
      }
      _scheduleReconnect();
    }
  }

  void _handleWsMessage(dynamic raw) {
    if (raw == null) return;

    try {
      final data = jsonDecode(raw as String) as Map<String, dynamic>;
      final type = (data['type'] ?? '').toString();

      if (type == 'output') {
        final text = (data['text'] ?? '').toString();
        if (text.isNotEmpty) {
          _outputController.add(text);
        }
      } else if (type == 'connected') {
        _setStatus(IdeTerminalStatus.connected);
      }
    } catch (_) {
      // Ignore malformed chunks to keep stream alive.
    }
  }

  bool _looksLikeAuthFailure(String message) {
    final normalized = message.toLowerCase();
    return normalized.contains('401') ||
        normalized.contains('invalid token') ||
        normalized.contains('not upgraded');
  }

  void _scheduleReconnect() {
    if (_manualClose || !_started) return;
    if (_reconnectTimer != null) return;

    _socket = null;
    _pingTimer?.cancel();
    _pingTimer = null;

    _reconnectAttempt += 1;
    final seconds = _backoffSeconds(_reconnectAttempt);
    _setStatus(IdeTerminalStatus.reconnecting);

    _reconnectTimer = Timer(Duration(seconds: seconds), () async {
      _reconnectTimer = null;
      if (!_started || _manualClose) return;

      // Refresh session/token periodically while reconnecting.
      if (_reconnectAttempt >= 3) {
        try {
          await _openTerminalSession(refresh: true);
        } catch (_) {}
      }

      await _connectWebSocket();
    });
  }

  int _backoffSeconds(int attempt) {
    if (attempt <= 1) return 1;
    if (attempt == 2) return 2;
    if (attempt == 3) return 4;
    if (attempt == 4) return 8;
    return 15;
  }

  void _startPingLoop() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      if (_socket == null) return;
      try {
        _socket!.add(jsonEncode(<String, dynamic>{
          'type': 'ping',
          'ts': DateTime.now().millisecondsSinceEpoch,
        }));
      } catch (_) {
        _scheduleReconnect();
      }
    });
  }

  Future<Map<String, dynamic>> _postJson(String path, String body) async {
    Object? lastError;
    int? lastStatus;

    for (final base in _httpBases) {
      final uri = Uri.parse('$base$path');
      try {
        final response = await _client
            .post(
              uri,
              headers: const <String, String>{'Content-Type': 'application/json'},
              body: body,
            )
            .timeout(const Duration(seconds: 8));

        if (response.statusCode >= 200 && response.statusCode < 300) {
          _baseHttp = base;
          return jsonDecode(response.body) as Map<String, dynamic>;
        }

        lastStatus = response.statusCode;
        lastError = response.body;
      } catch (e) {
        lastError = e;
      }
    }

    throw StateError('POST $path failed (status=$lastStatus): $lastError');
  }

  String _resolveWsUrl() {
    final wsPath = _wsUrl ?? '';
    if (wsPath.isEmpty) {
      throw StateError('WebSocket URL is not available');
    }

    if (wsPath.startsWith('ws://') || wsPath.startsWith('wss://')) {
      return wsPath;
    }

    final base = _baseHttp ?? _httpBases.first;
    final wsBase = base.replaceFirst('http://', 'ws://').replaceFirst('https://', 'wss://');
    return '$wsBase$wsPath';
  }

  Future<void> _safeCloseTerminalSession() async {
    final sessionId = _terminalSessionId;
    if (sessionId == null || sessionId.isEmpty) return;

    try {
      await _postJson(
        '/ide/terminal/close',
        jsonEncode(<String, dynamic>{'session_id': sessionId}),
      );
    } catch (_) {
      // Best effort.
    } finally {
      _terminalSessionId = null;
      _token = null;
      _wsUrl = null;
    }
  }

  Future<void> _safeCloseIdeSession() async {
    final sessionId = _ideSessionId;
    if (sessionId == null || sessionId.isEmpty) return;

    try {
      await _postJson(
        '/ide/session/close',
        jsonEncode(<String, dynamic>{'session_id': sessionId}),
      );
    } catch (_) {
      // Best effort.
    } finally {
      _ideSessionId = null;
    }
  }

  void _setStatus(IdeTerminalStatus next) {
    if (_status == next) return;
    _status = next;
    _statusController.add(next);
  }
}

enum IdeTerminalStatus {
  idle,
  opening,
  connecting,
  connected,
  reconnecting,
  closed,
  error,
}
