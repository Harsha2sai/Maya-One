import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

class IdeFilesService {
  IdeFilesService({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  static const List<String> _bases = <String>[
    'http://127.0.0.1:5050',
    'http://localhost:5050',
  ];

  String? _activeBase;
  String? _lastUserId;
  String? _lastWorkspacePath;

  Future<String> openIdeSession({
    required String userId,
    required String workspacePath,
  }) async {
    final response = await _post(
      '/ide/session/open',
      <String, dynamic>{
        'user_id': userId,
        'workspace_path': workspacePath,
      },
    );

    final sessionId = (response['session_id'] ?? '').toString();
    if (sessionId.isEmpty) {
      throw IdeFilesError(statusCode: 500, message: 'Missing session_id in open session response');
    }

    _lastUserId = userId;
    _lastWorkspacePath = workspacePath;
    return sessionId;
  }

  Future<void> closeIdeSession({required String sessionId}) async {
    await _post(
      '/ide/session/close',
      <String, dynamic>{'session_id': sessionId},
    );
  }

  Future<IdeDirectorySnapshot> listDirectory({
    required String sessionId,
    required String relativePath,
  }) async {
    return _withSessionRetry(
      sessionId: sessionId,
      operation: (effectiveSessionId) async {
        final response = await _get(
          '/ide/files/tree',
          <String, String>{
            'session_id': effectiveSessionId,
            'relative_path': relativePath,
          },
        );

        final entriesJson = (response['entries'] as List<dynamic>? ?? <dynamic>[])
            .whereType<Map<String, dynamic>>()
            .toList(growable: false);

        final entries = entriesJson.map(IdeFilesEntry.fromJson).toList(growable: false);

        return IdeDirectorySnapshot(
          sessionId: (response['session_id'] ?? effectiveSessionId).toString(),
          path: (response['path'] ?? relativePath).toString(),
          entries: entries,
        );
      },
    );
  }

  Future<IdeFileDocument> readFile({
    required String sessionId,
    required String relativePath,
  }) async {
    return _withSessionRetry(
      sessionId: sessionId,
      operation: (effectiveSessionId) async {
        final response = await _get(
          '/ide/file/read',
          <String, String>{
            'session_id': effectiveSessionId,
            'relative_path': relativePath,
          },
        );

        final content = (response['content'] ?? '').toString();
        final path = (response['path'] ?? relativePath).toString();

        return IdeFileDocument(
          sessionId: (response['session_id'] ?? effectiveSessionId).toString(),
          path: path,
          originalContent: content,
          draftContent: content,
          lastSavedAt: null,
        );
      },
    );
  }

  Future<IdeWriteResult> writeFile({
    required String sessionId,
    required String relativePath,
    required String content,
  }) async {
    return _withSessionRetry(
      sessionId: sessionId,
      operation: (effectiveSessionId) async {
        final response = await _post(
          '/ide/file/write',
          <String, dynamic>{
            'session_id': effectiveSessionId,
            'relative_path': relativePath,
            'content': content,
          },
        );

        return IdeWriteResult(
          sessionId: (response['session_id'] ?? effectiveSessionId).toString(),
          path: (response['path'] ?? relativePath).toString(),
          lastSavedAt: DateTime.now().toUtc(),
        );
      },
    );
  }

  Future<void> dispose() async {
    _client.close();
  }

  Future<T> _withSessionRetry<T>({
    required String sessionId,
    required Future<T> Function(String effectiveSessionId) operation,
  }) async {
    try {
      return await operation(sessionId);
    } on IdeFilesError catch (error) {
      final canRetry = error.statusCode == 404 && _lastUserId != null && _lastWorkspacePath != null;
      if (!canRetry) {
        rethrow;
      }

      final newSessionId = await openIdeSession(
        userId: _lastUserId!,
        workspacePath: _lastWorkspacePath!,
      );
      return operation(newSessionId);
    }
  }

  Future<Map<String, dynamic>> _get(
    String path,
    Map<String, String> query,
  ) async {
    final response = await _request(
      method: 'GET',
      path: path,
      query: query,
    );
    return _decodeJsonResponse(response);
  }

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    final response = await _request(
      method: 'POST',
      path: path,
      body: jsonEncode(body),
      headers: const <String, String>{'Content-Type': 'application/json'},
    );
    return _decodeJsonResponse(response);
  }

  Future<http.Response> _request({
    required String method,
    required String path,
    Map<String, String>? query,
    String? body,
    Map<String, String>? headers,
  }) async {
    final bases = <String>{
      if (_activeBase != null) _activeBase!,
      ..._bases,
    }.toList(growable: false);

    Object? lastConnectionError;

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

        throw _decodeErrorResponse(response);
      } on SocketException catch (e) {
        lastConnectionError = e;
      } on HttpException catch (e) {
        lastConnectionError = e;
      } on http.ClientException catch (e) {
        lastConnectionError = e;
      }
    }

    throw IdeFilesError(
      statusCode: 0,
      message: 'Unable to connect to IDE backend: $lastConnectionError',
    );
  }

  Map<String, dynamic> _decodeJsonResponse(http.Response response) {
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

  IdeFilesError _decodeErrorResponse(http.Response response) {
    final payload = _decodeJsonResponse(response);
    final message = (payload['error'] ?? 'Request failed').toString();

    final decision = payload['decision'];
    String? risk;
    String? policyReason;
    bool? requiresApproval;

    if (decision is Map<String, dynamic>) {
      risk = decision['risk']?.toString();
      policyReason = decision['policy_reason']?.toString();
      requiresApproval = decision['requires_approval'] is bool ? decision['requires_approval'] as bool : null;
    }

    return IdeFilesError(
      statusCode: response.statusCode,
      message: message,
      risk: risk,
      policyReason: policyReason,
      requiresApproval: requiresApproval,
    );
  }
}

class IdeFilesEntry {
  IdeFilesEntry({
    required this.name,
    required this.path,
    required this.isDir,
    required this.size,
  });

  factory IdeFilesEntry.fromJson(Map<String, dynamic> json) {
    return IdeFilesEntry(
      name: (json['name'] ?? '').toString(),
      path: (json['path'] ?? '').toString(),
      isDir: json['is_dir'] == true,
      size: (json['size'] is int) ? json['size'] as int : int.tryParse((json['size'] ?? '0').toString()) ?? 0,
    );
  }

  final String name;
  final String path;
  final bool isDir;
  final int size;
}

class IdeDirectorySnapshot {
  IdeDirectorySnapshot({
    required this.sessionId,
    required this.path,
    required this.entries,
  });

  final String sessionId;
  final String path;
  final List<IdeFilesEntry> entries;
}

class IdeFileDocument {
  IdeFileDocument({
    required this.sessionId,
    required this.path,
    required this.originalContent,
    required this.draftContent,
    this.lastSavedAt,
  });

  final String sessionId;
  final String path;
  final String originalContent;
  final String draftContent;
  final DateTime? lastSavedAt;

  bool get isDirty => originalContent != draftContent;
}

class IdeWriteResult {
  IdeWriteResult({
    required this.sessionId,
    required this.path,
    required this.lastSavedAt,
  });

  final String sessionId;
  final String path;
  final DateTime lastSavedAt;
}

class IdeFilesError implements Exception {
  IdeFilesError({
    required this.statusCode,
    required this.message,
    this.risk,
    this.policyReason,
    this.requiresApproval,
  });

  final int statusCode;
  final String message;
  final String? risk;
  final String? policyReason;
  final bool? requiresApproval;

  @override
  String toString() {
    return 'IdeFilesError(status=$statusCode, message=$message, risk=$risk, policyReason=$policyReason, requiresApproval=$requiresApproval)';
  }
}
