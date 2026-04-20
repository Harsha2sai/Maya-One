import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:voice_assistant/core/services/ide_actions_service.dart';

void main() {
  group('IdeActionsService', () {
    test('requestAction returns executed result', () async {
      final service = IdeActionsService(
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/ide/action/request');
          return http.Response(
            jsonEncode(
              <String, dynamic>{
                'action_id': 'act-1',
                'status': 'executed',
                'result': <String, dynamic>{'executed': true},
              },
            ),
            200,
          );
        }),
      );

      final result = await service.requestAction(
        userId: 'u1',
        sessionId: 'sess-1',
        action: IdeActionEnvelope(target: 'agent', operation: 'retry'),
      );
      expect(result.actionId, 'act-1');
      expect(result.status, 'executed');
    });

    test('listPending parses pending actions', () async {
      final service = IdeActionsService(
        client: MockClient((request) async {
          expect(request.url.path, '/ide/action/pending');
          return http.Response(
            jsonEncode(
              <String, dynamic>{
                'actions': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'action_id': 'act-p1',
                    'action_type': 'mcp:set_url',
                    'target_id': 'n8n',
                    'risk': 'high',
                    'policy_reason': 'approval required',
                    'user_id': 'u1',
                    'session_id': 'sess-1',
                    'requested_at': 1.0,
                    'expires_at': 10.0,
                    'payload': <String, dynamic>{},
                  },
                ],
              },
            ),
            200,
          );
        }),
      );

      final actions = await service.listPending(userId: 'u1');
      expect(actions.length, 1);
      expect(actions.first.actionId, 'act-p1');
      expect(actions.first.risk, 'high');
    });

    test('listAudit parses audit events', () async {
      final service = IdeActionsService(
        client: MockClient((request) async {
          expect(request.url.path, '/ide/action/audit');
          return http.Response(
            jsonEncode(
              <String, dynamic>{
                'events': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'action_id': 'act-1',
                    'event_type': 'executed',
                    'timestamp': 12.0,
                    'user_id': 'u1',
                    'session_id': 'sess-1',
                    'action_type': 'agent:retry',
                    'risk': 'medium',
                  },
                ],
              },
            ),
            200,
          );
        }),
      );

      final events = await service.listAudit(userId: 'u1', sessionId: 'sess-1', limit: 50);
      expect(events.length, 1);
      expect(events.first.eventType, 'executed');
    });

    test('mutateMcp posts mutate endpoint', () async {
      final service = IdeActionsService(
        client: MockClient((request) async {
          expect(request.url.path, '/ide/mcp/mutate');
          return http.Response(
            jsonEncode(
              <String, dynamic>{
                'action_id': 'act-2',
                'status': 'pending',
                'risk': 'high',
                'policy_reason': 'approval required',
                'requires_approval': true,
              },
            ),
            200,
          );
        }),
      );

      final result = await service.mutateMcp(
        userId: 'u1',
        sessionId: 'sess-1',
        action: IdeActionEnvelope(
          target: 'mcp',
          operation: 'set_url',
          arguments: const <String, dynamic>{'url': 'http://localhost:5678'},
        ),
      );
      expect(result.status, 'pending');
      expect(result.requiresApproval, isTrue);
    });

    test('throws IdeActionError for failing request', () async {
      final service = IdeActionsService(
        client: MockClient((request) async {
          return http.Response(
            jsonEncode(<String, dynamic>{'error': 'action not permitted'}),
            409,
          );
        }),
      );

      expect(
        () => service.requestAction(
          userId: 'u1',
          sessionId: 'sess-1',
          action: IdeActionEnvelope(target: 'mcp', operation: 'set_url'),
        ),
        throwsA(isA<IdeActionError>().having((e) => e.statusCode, 'statusCode', 409)),
      );
    });
  });
}
