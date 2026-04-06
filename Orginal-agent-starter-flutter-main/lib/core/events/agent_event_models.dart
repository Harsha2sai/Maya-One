enum AgentEventValidationStatus {
  valid,
  schemaVersionMismatch,
  unknownType,
  invalid,
}

class AgentUiEvent {
  final String eventType;
  final String schemaVersion;
  final String? traceId;
  final String? taskId;
  final String? conversationId;
  final String? originSessionId;
  final int timestamp;
  final Map<String, dynamic> payload;

  const AgentUiEvent({
    required this.eventType,
    required this.schemaVersion,
    required this.timestamp,
    required this.payload,
    this.traceId,
    this.taskId,
    this.conversationId,
    this.originSessionId,
  });

  factory AgentUiEvent.fromNormalizedMap(Map<String, dynamic> normalized) {
    final payload = Map<String, dynamic>.from(normalized)
      ..remove('type')
      ..remove('schema_version')
      ..remove('trace_id')
      ..remove('task_id')
      ..remove('conversation_id')
      ..remove('origin_session_id')
      ..remove('timestamp');

    return AgentUiEvent(
      eventType: (normalized['type'] ?? '').toString(),
      schemaVersion: (normalized['schema_version'] ?? '').toString(),
      traceId: normalized['trace_id']?.toString(),
      taskId: normalized['task_id']?.toString(),
      conversationId: normalized['conversation_id']?.toString(),
      originSessionId: normalized['origin_session_id']?.toString(),
      timestamp: normalized['timestamp'] is int
          ? normalized['timestamp'] as int
          : int.tryParse((normalized['timestamp'] ?? '').toString()) ?? 0,
      payload: payload,
    );
  }

  AgentUiEvent copyWith({
    String? eventType,
    String? schemaVersion,
    String? traceId,
    String? taskId,
    String? conversationId,
    String? originSessionId,
    int? timestamp,
    Map<String, dynamic>? payload,
  }) {
    return AgentUiEvent(
      eventType: eventType ?? this.eventType,
      schemaVersion: schemaVersion ?? this.schemaVersion,
      traceId: traceId ?? this.traceId,
      taskId: taskId ?? this.taskId,
      conversationId: conversationId ?? this.conversationId,
      originSessionId: originSessionId ?? this.originSessionId,
      timestamp: timestamp ?? this.timestamp,
      payload: payload ?? this.payload,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'type': eventType,
      'schema_version': schemaVersion,
      ...payload,
      'timestamp': timestamp,
      if (traceId != null) 'trace_id': traceId,
      if (taskId != null) 'task_id': taskId,
      if (conversationId != null) 'conversation_id': conversationId,
      if (originSessionId != null) 'origin_session_id': originSessionId,
    };
  }
}

class AgentEventValidationResult {
  final AgentEventValidationStatus status;
  final AgentUiEvent? validatedEvent;
  final String? reason;
  final String? receivedSchemaVersion;

  const AgentEventValidationResult({
    required this.status,
    this.validatedEvent,
    this.reason,
    this.receivedSchemaVersion,
  });

  Map<String, dynamic>? get normalizedEvent => validatedEvent?.toMap();

  bool get canRoute =>
      (status == AgentEventValidationStatus.valid || status == AgentEventValidationStatus.schemaVersionMismatch) &&
      validatedEvent != null;
}
