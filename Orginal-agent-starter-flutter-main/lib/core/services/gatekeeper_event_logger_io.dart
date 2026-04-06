import 'dart:async';
import 'dart:convert';
import 'dart:io';

class GatekeeperEventLoggerImpl {
  final bool enabled;
  final String logPath;
  Future<void> _writeQueue = Future<void>.value();

  GatekeeperEventLoggerImpl({
    required this.enabled,
    required this.logPath,
  });

  void logEvent(
    String eventType, {
    String? turnId,
    String? traceId,
    String? sessionId,
    String? content,
    String? toolName,
    String? status,
    double? latencyMs,
    String? source,
    Map<String, dynamic>? extra,
  }) {
    if (!enabled) return;

    final now = DateTime.now();
    final record = <String, dynamic>{
      'ts': now.toUtc().toIso8601String(),
      'ts_ms': now.millisecondsSinceEpoch,
      'event_type': eventType,
      'turn_id': turnId,
      'trace_id': traceId,
      'session_id': sessionId,
      'content': content,
      'content_preview': _preview(content),
      'tool_name': toolName,
      'status': status,
      'latency_ms': latencyMs,
      'source': source,
      if (extra != null) ...extra,
    };

    _writeQueue = _writeQueue.then((_) async {
      try {
        final file = File(logPath);
        await file.parent.create(recursive: true);
        await file.writeAsString('${jsonEncode(record)}\n', mode: FileMode.append, flush: true);
      } catch (_) {
        // Logging must never break app behavior.
      }
    });
  }

  String _preview(String? text, {int maxChars = 180}) {
    final raw = (text ?? '').replaceAll(RegExp(r'\s+'), ' ').trim();
    if (raw.length <= maxChars) return raw;
    return '${raw.substring(0, maxChars)}...';
  }
}
