class GatekeeperEventLoggerImpl {
  final bool enabled;
  final String logPath;

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
    // No-op on non-IO platforms (web).
  }
}
