import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/events/agent_event_models.dart';
import 'package:voice_assistant/core/events/agent_event_validator.dart';

void main() {
  group('AgentEventValidator', () {
    test('accepts valid known event', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 't1',
        'state': 'thinking',
        'timestamp': 123,
      });

      expect(result.status, AgentEventValidationStatus.valid);
      expect(result.canRoute, isTrue);
      expect(result.validatedEvent, isNotNull);
      expect(result.validatedEvent?.eventType, 'agent_thinking');
      expect(result.normalizedEvent?['type'], 'agent_thinking');
    });

    test('returns schemaVersionMismatch for mismatched schema', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'user_message',
        'schema_version': '2.0',
        'turn_id': 't2',
        'content': 'hello',
        'timestamp': 456,
      });

      expect(result.status, AgentEventValidationStatus.schemaVersionMismatch);
      expect(result.canRoute, isTrue);
      expect(result.validatedEvent?.schemaVersion, AgentEventValidator.expectedSchemaVersion);
      expect(result.normalizedEvent?['schema_version'], AgentEventValidator.expectedSchemaVersion);
    });

    test('returns unknownType for unknown events', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'custom_event',
        'schema_version': '1.0',
        'timestamp': 1,
      });

      expect(result.status, AgentEventValidationStatus.unknownType);
      expect(result.canRoute, isFalse);
    });

    test('returns invalid when known event missing required fields', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'tool_execution',
        'schema_version': '1.0',
        'turn_id': 't3',
        'timestamp': 789,
      });

      expect(result.status, AgentEventValidationStatus.invalid);
      expect(result.canRoute, isFalse);
    });

    test('accepts research_result event', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'research_result',
        'schema_version': '1.0',
        'turn_id': 't4',
        'query': 'latest ai news',
        'summary': 'Top updates',
        'sources': const [
          {
            'title': 'Source',
            'url': 'https://example.com',
            'domain': 'example.com',
            'snippet': 'snippet',
            'provider': 'tavily',
          }
        ],
        'timestamp': 111,
      });

      expect(result.status, AgentEventValidationStatus.valid);
      expect(result.canRoute, isTrue);
      expect(result.validatedEvent?.payload['query'], 'latest ai news');
      expect(result.normalizedEvent?['type'], 'research_result');
      expect((result.normalizedEvent?['sources'] as List).length, 1);
    });

    test('accepts media_result event', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'media_result',
        'schema_version': '1.0',
        'turn_id': 'm1',
        'action': 'play',
        'provider': 'spotify',
        'track_name': 'Song A',
        'artist': 'Artist A',
        'track_url': 'https://open.spotify.com/track/abc',
        'timestamp': 112,
      });

      expect(result.status, AgentEventValidationStatus.valid);
      expect(result.canRoute, isTrue);
      expect(result.validatedEvent?.taskId, isNull);
      expect(result.normalizedEvent?['type'], 'media_result');
      expect(result.normalizedEvent?['provider'], 'spotify');
    });

    test('accepts system_result event', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'system_result',
        'schema_version': '1.0',
        'action_type': 'SCREENSHOT',
        'success': true,
        'message': 'Saved screenshot.',
        'detail': '/tmp/maya_screen.png',
        'rollback_available': false,
        'timestamp': 113,
        'trace_id': 'trace-system',
      });

      expect(result.status, AgentEventValidationStatus.valid);
      expect(result.canRoute, isTrue);
      expect(result.validatedEvent?.traceId, 'trace-system');
      expect(result.normalizedEvent?['type'], 'system_result');
      expect(result.normalizedEvent?['action_type'], 'SCREENSHOT');
    });

    test('accepts confirmation_required event', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'confirmation_required',
        'schema_version': '1.0',
        'action_type': 'FILE_DELETE',
        'description': 'Delete test.txt',
        'destructive': true,
        'timeout_seconds': 30,
        'timestamp': 114,
        'trace_id': 'trace-confirm',
      });

      expect(result.status, AgentEventValidationStatus.valid);
      expect(result.canRoute, isTrue);
      expect(result.normalizedEvent?['destructive'], true);
    });

    test('accepts confirmation_response event', () {
      final result = AgentEventValidator.validateChatEvent({
        'type': 'confirmation_response',
        'schema_version': '1.0',
        'confirmed': false,
        'trace_id': 'trace-confirm',
        'timestamp': 115,
      });

      expect(result.status, AgentEventValidationStatus.valid);
      expect(result.canRoute, isTrue);
      expect(result.normalizedEvent?['confirmed'], false);
    });
  });
}
