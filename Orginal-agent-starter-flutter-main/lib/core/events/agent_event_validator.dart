import 'agent_event_models.dart';

class AgentEventValidator {
  static const String expectedSchemaVersion = '1.0';
  static const Set<String> _knownTypes = <String>{
    'user_message',
    'assistant_delta',
    'assistant_final',
    'research_result',
    'media_result',
    'system_result',
    'confirmation_required',
    'confirmation_response',
    'agent_thinking',
    'tool_execution',
    'agent_speaking',
    'turn_complete',
    'error',
  };

  static AgentEventValidationResult validateChatEvent(Map<String, dynamic> raw) {
    final type = (raw['type'] ?? '').toString().trim();
    if (type.isEmpty) {
      return const AgentEventValidationResult(
        status: AgentEventValidationStatus.invalid,
        reason: 'missing_type',
      );
    }
    if (!_knownTypes.contains(type)) {
      return AgentEventValidationResult(
        status: AgentEventValidationStatus.unknownType,
        reason: 'unknown_type',
      );
    }

    final receivedSchemaVersion = raw['schema_version']?.toString();
    final mismatch = receivedSchemaVersion != expectedSchemaVersion;
    final normalized = _normalize(type, raw);
    if (normalized == null) {
      return AgentEventValidationResult(
        status: mismatch ? AgentEventValidationStatus.schemaVersionMismatch : AgentEventValidationStatus.invalid,
        reason: mismatch ? 'schema_mismatch_unparseable' : 'invalid_payload',
        receivedSchemaVersion: receivedSchemaVersion,
      );
    }

    final validatedEvent = AgentUiEvent.fromNormalizedMap(normalized);

    return AgentEventValidationResult(
      status: mismatch ? AgentEventValidationStatus.schemaVersionMismatch : AgentEventValidationStatus.valid,
      validatedEvent: validatedEvent,
      receivedSchemaVersion: receivedSchemaVersion,
      reason: mismatch ? 'schema_mismatch_best_effort' : null,
    );
  }

  static int _timestamp(dynamic raw) {
    if (raw is int) return raw;
    if (raw is String) {
      final parsed = int.tryParse(raw.trim());
      if (parsed != null) return parsed;
    }
    return DateTime.now().millisecondsSinceEpoch;
  }

  static String? _requiredString(Map<String, dynamic> raw, String key) {
    final val = raw[key];
    if (val == null) return null;
    final s = val.toString().trim();
    return s.isEmpty ? null : s;
  }

  static Map<String, dynamic>? _normalize(String type, Map<String, dynamic> raw) {
    switch (type) {
      case 'user_message':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final content = _requiredString(raw, 'content');
        if (turnId == null || content == null) return null;
        return {
          'type': 'user_message',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'content': content,
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'assistant_delta':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final content = _requiredString(raw, 'content');
        final seqRaw = raw['seq'];
        final seq = seqRaw is int ? seqRaw : int.tryParse((seqRaw ?? '').toString());
        if (turnId == null || content == null || seq == null) return null;
        return {
          'type': 'assistant_delta',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'content': content,
          'seq': seq,
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'assistant_final':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final content = _requiredString(raw, 'content');
        if (turnId == null || content == null) return null;
        return {
          'type': 'assistant_final',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'content': content,
          'voice_text': (raw['voice_text'] ?? '').toString(),
          'sources': raw['sources'] is List ? raw['sources'] : const [],
          'tool_invocations': raw['tool_invocations'] is List ? raw['tool_invocations'] : const [],
          'mode': (raw['mode'] ?? 'normal').toString(),
          'memory_updated': raw['memory_updated'] == true,
          'confidence': (raw['confidence'] is num)
              ? (raw['confidence'] as num).toDouble()
              : (double.tryParse((raw['confidence'] ?? '').toString()) ?? 0.0),
          'structured_data': raw['structured_data'] is Map ? raw['structured_data'] : const {},
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'research_result':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final summary = _requiredString(raw, 'summary');
        final query = _requiredString(raw, 'query');
        if (turnId == null || summary == null || query == null) return null;
        return {
          'type': 'research_result',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'summary': summary,
          'query': query,
          'sources': raw['sources'] is List ? raw['sources'] : const [],
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'task_id') != null) 'task_id': _requiredString(raw, 'task_id'),
          if (_requiredString(raw, 'conversation_id') != null)
            'conversation_id': _requiredString(raw, 'conversation_id'),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'media_result':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final action = _requiredString(raw, 'action');
        final provider = _requiredString(raw, 'provider');
        if (turnId == null || action == null || provider == null) return null;
        return {
          'type': 'media_result',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'action': action,
          'provider': provider,
          if (_requiredString(raw, 'track_name') != null) 'track_name': _requiredString(raw, 'track_name'),
          if (_requiredString(raw, 'artist') != null) 'artist': _requiredString(raw, 'artist'),
          if (_requiredString(raw, 'album_art_url') != null) 'album_art_url': _requiredString(raw, 'album_art_url'),
          if (_requiredString(raw, 'track_url') != null) 'track_url': _requiredString(raw, 'track_url'),
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'task_id') != null) 'task_id': _requiredString(raw, 'task_id'),
          if (_requiredString(raw, 'conversation_id') != null)
            'conversation_id': _requiredString(raw, 'conversation_id'),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'system_result':
        final actionType = _requiredString(raw, 'action_type');
        final message = _requiredString(raw, 'message');
        if (actionType == null || message == null) return null;
        return {
          'type': 'system_result',
          'schema_version': expectedSchemaVersion,
          if (_requiredString(raw, 'turn_id') != null) 'turn_id': _requiredString(raw, 'turn_id'),
          'action_type': actionType,
          'success': raw['success'] == true,
          'message': message,
          'detail': (raw['detail'] ?? '').toString(),
          'rollback_available': raw['rollback_available'] == true,
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'task_id') != null) 'task_id': _requiredString(raw, 'task_id'),
          if (_requiredString(raw, 'conversation_id') != null)
            'conversation_id': _requiredString(raw, 'conversation_id'),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'confirmation_required':
        final actionType = _requiredString(raw, 'action_type');
        final description = _requiredString(raw, 'description');
        final timeoutRaw = raw['timeout_seconds'];
        final timeout = timeoutRaw is int ? timeoutRaw : int.tryParse((timeoutRaw ?? '').toString());
        if (actionType == null || description == null || timeout == null) return null;
        return {
          'type': 'confirmation_required',
          'schema_version': expectedSchemaVersion,
          'action_type': actionType,
          'description': description,
          'destructive': raw['destructive'] == true,
          'timeout_seconds': timeout,
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'confirmation_response':
        final traceId = _requiredString(raw, 'trace_id');
        if (traceId == null) return null;
        return {
          'type': 'confirmation_response',
          'schema_version': expectedSchemaVersion,
          'trace_id': traceId,
          'confirmed': raw['confirmed'] == true,
          'timestamp': _timestamp(raw['timestamp']),
        };
      case 'agent_thinking':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final state = _requiredString(raw, 'state');
        if (turnId == null || state == null) return null;
        return {
          'type': 'agent_thinking',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'state': state,
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'tool_execution':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final status = _requiredString(raw, 'status');
        final toolName = _requiredString(raw, 'tool_name') ?? _requiredString(raw, 'tool');
        if (turnId == null || status == null || toolName == null) return null;
        return {
          'type': 'tool_execution',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'status': status,
          'tool_name': toolName,
          'tool': toolName,
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'message') != null) 'message': _requiredString(raw, 'message'),
          if (_requiredString(raw, 'task_id') != null) 'task_id': _requiredString(raw, 'task_id'),
          if (_requiredString(raw, 'conversation_id') != null)
            'conversation_id': _requiredString(raw, 'conversation_id'),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'agent_speaking':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final status = _requiredString(raw, 'status');
        if (turnId == null || status == null) return null;
        return {
          'type': 'agent_speaking',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'status': status,
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'turn_complete':
        final turnId = _requiredString(raw, 'turn_id') ?? _requiredString(raw, 'turnId');
        final status = _requiredString(raw, 'status');
        if (turnId == null || status == null) return null;
        return {
          'type': 'turn_complete',
          'schema_version': expectedSchemaVersion,
          'turn_id': turnId,
          'status': status,
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
      case 'error':
        final message = _requiredString(raw, 'message');
        if (message == null) return null;
        return {
          'type': 'error',
          'schema_version': expectedSchemaVersion,
          if (_requiredString(raw, 'turn_id') != null) 'turn_id': _requiredString(raw, 'turn_id'),
          'message': message,
          if (_requiredString(raw, 'code') != null) 'code': _requiredString(raw, 'code'),
          'timestamp': _timestamp(raw['timestamp']),
          if (_requiredString(raw, 'trace_id') != null) 'trace_id': _requiredString(raw, 'trace_id'),
        };
    }
    return null;
  }
}
