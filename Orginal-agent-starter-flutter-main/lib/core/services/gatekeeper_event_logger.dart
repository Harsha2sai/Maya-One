import 'gatekeeper_event_logger_stub.dart' if (dart.library.io) 'gatekeeper_event_logger_io.dart' as impl;

class GatekeeperEventLogger {
  static const bool _enabled = bool.fromEnvironment('FLUTTER_GATEKEEPER_MODE', defaultValue: false);
  static const String _logPath = String.fromEnvironment(
    'FLUTTER_GATEKEEPER_LOG_PATH',
    defaultValue: '/tmp/maya_flutter_gatekeeper.jsonl',
  );

  static final GatekeeperEventLogger instance = GatekeeperEventLogger._();

  final impl.GatekeeperEventLoggerImpl _impl = impl.GatekeeperEventLoggerImpl(
    enabled: _enabled,
    logPath: _logPath,
  );

  GatekeeperEventLogger._();

  bool get enabled => _enabled;
  String get logPath => _logPath;

  static String preview(String? text, {int maxChars = 180}) {
    final raw = (text ?? '').replaceAll(RegExp(r'\s+'), ' ').trim();
    if (raw.length <= maxChars) return raw;
    return '${raw.substring(0, maxChars)}...';
  }

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
    if (!_enabled) return;
    _impl.logEvent(
      eventType,
      turnId: turnId,
      traceId: traceId,
      sessionId: sessionId,
      content: content,
      toolName: toolName,
      status: status,
      latencyMs: latencyMs,
      source: source,
      extra: extra,
    );
  }
}
