import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

class IdeActionEnvelope {
  IdeActionEnvelope({
    required this.target,
    required this.operation,
    this.arguments = const <String, dynamic>{},
    this.confidence = 1.0,
    this.reason = 'user request',
  });

  final String target;
  final String operation;
  final Map<String, dynamic> arguments;
  final double confidence;
  final String reason;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'type': 'ide_action',
      'target': target,
      'operation': operation,
      'arguments': arguments,
      'confidence': confidence,
      'reason': reason,
    };
  }
}

class IdeActionResult {
  IdeActionResult({
    required this.actionId,
    required this.status,
    this.result = const <String, dynamic>{},
    this.risk,
    this.policyReason,
    this.requiresApproval,
  });

  factory IdeActionResult.fromJson(Map<String, dynamic> json) {
    return IdeActionResult(
      actionId: (json['action_id'] ?? '').toString(),
      status: (json['status'] ?? '').toString(),
      result: json['result'] is Map<String, dynamic>
          ? json['result'] as Map<String, dynamic>
          : Map<String, dynamic>.from(json['result'] as Map? ?? const <String, dynamic>{}),
      risk: json['risk']?.toString(),
      policyReason: json['policy_reason']?.toString(),
      requiresApproval: json['requires_approval'] is bool ? json['requires_approval'] as bool : null,
    );
  }

  final String actionId;
  final String status;
  final Map<String, dynamic> result;
  final String? risk;
  final String? policyReason;
  final bool? requiresApproval;
}

class IdePendingAction {
  IdePendingAction({
    required this.actionId,
    required this.actionType,
    required this.targetId,
    required this.risk,
    required this.policyReason,
    required this.userId,
    required this.sessionId,
    required this.requestedAt,
    required this.expiresAt,
    this.traceId,
    this.taskId,
    this.payload = const <String, dynamic>{},
  });

  factory IdePendingAction.fromJson(Map<String, dynamic> json) {
    return IdePendingAction(
      actionId: (json['action_id'] ?? '').toString(),
      actionType: (json['action_type'] ?? '').toString(),
      targetId: (json['target_id'] ?? '').toString(),
      risk: (json['risk'] ?? '').toString(),
      policyReason: (json['policy_reason'] ?? '').toString(),
      userId: (json['user_id'] ?? '').toString(),
      sessionId: (json['session_id'] ?? '').toString(),
      requestedAt: _asDouble(json['requested_at']),
      expiresAt: _asDouble(json['expires_at']),
      traceId: json['trace_id']?.toString(),
      taskId: json['task_id']?.toString(),
      payload: json['payload'] is Map<String, dynamic>
          ? json['payload'] as Map<String, dynamic>
          : Map<String, dynamic>.from(json['payload'] as Map? ?? const <String, dynamic>{}),
    );
  }

  final String actionId;
  final String actionType;
  final String targetId;
  final String risk;
  final String policyReason;
  final String userId;
  final String sessionId;
  final double requestedAt;
  final double expiresAt;
  final String? traceId;
  final String? taskId;
  final Map<String, dynamic> payload;
}

class IdeActionAuditEvent {
  IdeActionAuditEvent({
    required this.actionId,
    required this.eventType,
    required this.timestamp,
    required this.userId,
    required this.sessionId,
    required this.actionType,
    required this.risk,
    this.idempotencyKey,
    this.decidedBy,
    this.decidedAt,
    this.executionResult = const <String, dynamic>{},
    this.error,
    this.traceId,
    this.taskId,
  });

  factory IdeActionAuditEvent.fromJson(Map<String, dynamic> json) {
    return IdeActionAuditEvent(
      actionId: (json['action_id'] ?? '').toString(),
      eventType: (json['event_type'] ?? '').toString(),
      timestamp: _asDouble(json['timestamp']),
      userId: (json['user_id'] ?? '').toString(),
      sessionId: (json['session_id'] ?? '').toString(),
      actionType: (json['action_type'] ?? '').toString(),
      risk: (json['risk'] ?? '').toString(),
      idempotencyKey: json['idempotency_key']?.toString(),
      decidedBy: json['decided_by']?.toString(),
      decidedAt: json['decided_at'] == null ? null : _asDouble(json['decided_at']),
      executionResult: json['execution_result'] is Map<String, dynamic>
          ? json['execution_result'] as Map<String, dynamic>
          : Map<String, dynamic>.from(json['execution_result'] as Map? ?? const <String, dynamic>{}),
      error: json['error']?.toString(),
      traceId: json['trace_id']?.toString(),
      taskId: json['task_id']?.toString(),
    );
  }

  final String actionId;
  final String eventType;
  final double timestamp;
  final String userId;
  final String sessionId;
  final String actionType;
  final String risk;
  final String? idempotencyKey;
  final String? decidedBy;
  final double? decidedAt;
  final Map<String, dynamic> executionResult;
  final String? error;
  final String? traceId;
  final String? taskId;
}

class IdeMcpInventory {
  IdeMcpInventory({
    this.mcpServers = const <String, dynamic>{},
    this.plugins = const <String, dynamic>{},
    this.connectors = const <String, dynamic>{},
  });

  factory IdeMcpInventory.fromJson(Map<String, dynamic> json) {
    return IdeMcpInventory(
      mcpServers: json['mcp_servers'] is Map<String, dynamic>
          ? json['mcp_servers'] as Map<String, dynamic>
          : Map<String, dynamic>.from(json['mcp_servers'] as Map? ?? const <String, dynamic>{}),
      plugins: json['plugins'] is Map<String, dynamic>
          ? json['plugins'] as Map<String, dynamic>
          : Map<String, dynamic>.from(json['plugins'] as Map? ?? const <String, dynamic>{}),
      connectors: json['connectors'] is Map<String, dynamic>
          ? json['connectors'] as Map<String, dynamic>
          : Map<String, dynamic>.from(json['connectors'] as Map? ?? const <String, dynamic>{}),
    );
  }

  final Map<String, dynamic> mcpServers;
  final Map<String, dynamic> plugins;
  final Map<String, dynamic> connectors;
}

class IdeActionError implements Exception {
  IdeActionError({
    required this.statusCode,
    required this.message,
    this.payload = const <String, dynamic>{},
  });

  final int statusCode;
  final String message;
  final Map<String, dynamic> payload;

  @override
  String toString() => 'IdeActionError(status=$statusCode, message=$message)';
}

class IdeActionsService {
  IdeActionsService({http.Client? client}) : _client = client ?? http.Client();

  static const List<String> _bases = <String>[
    'http://127.0.0.1:5050',
    'http://localhost:5050',
  ];

  final http.Client _client;
  String? _activeBase;

  Future<IdeActionResult> requestAction({
    required String userId,
    required String sessionId,
    required IdeActionEnvelope action,
    String? idempotencyKey,
    String? traceId,
    String? taskId,
  }) async {
    final payload = await _post(
      '/ide/action/request',
      <String, dynamic>{
        'user_id': userId,
        'session_id': sessionId,
        'idempotency_key': idempotencyKey ?? _idempotencyKey(userId, sessionId, action),
        'trace_id': traceId,
        'task_id': taskId,
        'action': action.toJson(),
      },
    );
    return IdeActionResult.fromJson(payload);
  }

  Future<List<IdePendingAction>> listPending({String? userId}) async {
    final payload = await _get(
      '/ide/action/pending',
      <String, String>{
        if ((userId ?? '').trim().isNotEmpty) 'user_id': userId!.trim(),
      },
    );
    final actions = (payload['actions'] as List<dynamic>? ?? const <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(IdePendingAction.fromJson)
        .toList(growable: false);
    return actions;
  }

  Future<List<IdeActionAuditEvent>> listAudit({
    String? userId,
    String? sessionId,
    int limit = 200,
  }) async {
    final payload = await _get(
      '/ide/action/audit',
      <String, String>{
        if ((userId ?? '').trim().isNotEmpty) 'user_id': userId!.trim(),
        if ((sessionId ?? '').trim().isNotEmpty) 'session_id': sessionId!.trim(),
        'limit': '$limit',
      },
    );
    final events = (payload['events'] as List<dynamic>? ?? const <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(IdeActionAuditEvent.fromJson)
        .toList(growable: false);
    return events;
  }

  Future<IdeActionResult> approveAction({
    required String actionId,
    required String decidedBy,
    String reason = '',
  }) async {
    final payload = await _post(
      '/ide/action/approve',
      <String, dynamic>{
        'action_id': actionId,
        'decided_by': decidedBy,
        'reason': reason,
      },
    );
    return IdeActionResult.fromJson(payload);
  }

  Future<void> denyAction({
    required String actionId,
    required String decidedBy,
    required String reason,
  }) async {
    await _post(
      '/ide/action/deny',
      <String, dynamic>{
        'action_id': actionId,
        'decided_by': decidedBy,
        'reason': reason,
      },
    );
  }

  Future<void> cancelAction({
    required String actionId,
    required String userId,
  }) async {
    await _post(
      '/ide/action/cancel',
      <String, dynamic>{
        'action_id': actionId,
        'user_id': userId,
      },
    );
  }

  Future<IdeMcpInventory> getMcpInventory() async {
    final payload = await _get('/ide/mcp/inventory', const <String, String>{});
    return IdeMcpInventory.fromJson(payload);
  }

  Future<IdeActionResult> mutateMcp({
    required String userId,
    required String sessionId,
    required IdeActionEnvelope action,
    String? idempotencyKey,
  }) async {
    final payload = await _post(
      '/ide/mcp/mutate',
      <String, dynamic>{
        'user_id': userId,
        'session_id': sessionId,
        'idempotency_key': idempotencyKey ?? _idempotencyKey(userId, sessionId, action),
        'action': action.toJson(),
      },
    );
    return IdeActionResult.fromJson(payload);
  }

  Future<void> dispose() async {
    _client.close();
  }

  Future<Map<String, dynamic>> _get(String path, Map<String, String> query) async {
    final response = await _request(method: 'GET', path: path, query: query);
    return _decodeJson(response);
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final response = await _request(
      method: 'POST',
      path: path,
      headers: const <String, String>{'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    return _decodeJson(response);
  }

  Future<http.Response> _request({
    required String method,
    required String path,
    Map<String, String>? query,
    Map<String, String>? headers,
    String? body,
  }) async {
    final bases = <String>{
      if (_activeBase != null) _activeBase!,
      ..._bases,
    }.toList(growable: false);

    Object? lastError;
    for (final base in bases) {
      final uri = Uri.parse('$base$path').replace(queryParameters: query);
      try {
        late http.Response response;
        if (method == 'GET') {
          response = await _client.get(uri, headers: headers).timeout(const Duration(seconds: 8));
        } else {
          response = await _client.post(uri, headers: headers, body: body).timeout(const Duration(seconds: 8));
        }
        _activeBase = base;
        if (response.statusCode >= 200 && response.statusCode < 300) {
          return response;
        }
        throw _decodeError(response);
      } on SocketException catch (e) {
        lastError = e;
      } on HttpException catch (e) {
        lastError = e;
      } on http.ClientException catch (e) {
        lastError = e;
      }
    }

    throw IdeActionError(
      statusCode: 0,
      message: 'Unable to connect to action backend: $lastError',
    );
  }

  Map<String, dynamic> _decodeJson(http.Response response) {
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      return <String, dynamic>{};
    } catch (_) {
      return <String, dynamic>{};
    }
  }

  IdeActionError _decodeError(http.Response response) {
    final payload = _decodeJson(response);
    return IdeActionError(
      statusCode: response.statusCode,
      message: (payload['error'] ?? 'request failed').toString(),
      payload: payload,
    );
  }

  String _idempotencyKey(String userId, String sessionId, IdeActionEnvelope action) {
    final stamp = DateTime.now().microsecondsSinceEpoch;
    return '$userId:$sessionId:${action.target}:${action.operation}:$stamp';
  }
}

double _asDouble(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse('${value ?? 0}') ?? 0;
}
