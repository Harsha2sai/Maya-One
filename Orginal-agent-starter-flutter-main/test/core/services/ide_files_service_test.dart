import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:voice_assistant/core/services/ide_files_service.dart';

void main() {
  group('IdeFilesService', () {
    test('openIdeSession returns session_id', () async {
      final service = IdeFilesService(
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/ide/session/open');
          return http.Response(jsonEncode(<String, dynamic>{'session_id': 'sess-1'}), 200);
        }),
      );

      final sessionId = await service.openIdeSession(userId: 'u1', workspacePath: '/tmp/ws');
      expect(sessionId, 'sess-1');
    });

    test('listDirectory parses entries', () async {
      final service = IdeFilesService(
        client: MockClient((request) async {
          expect(request.method, 'GET');
          expect(request.url.path, '/ide/files/tree');
          return http.Response(
            jsonEncode(<String, dynamic>{
              'session_id': 'sess-1',
              'path': '',
              'entries': <Map<String, dynamic>>[
                <String, dynamic>{'name': 'src', 'path': 'src', 'is_dir': true, 'size': 0},
                <String, dynamic>{'name': 'README.md', 'path': 'README.md', 'is_dir': false, 'size': 42},
              ],
            }),
            200,
          );
        }),
      );

      final snapshot = await service.listDirectory(sessionId: 'sess-1', relativePath: '');
      expect(snapshot.path, '');
      expect(snapshot.entries.length, 2);
      expect(snapshot.entries.first.isDir, isTrue);
      expect(snapshot.entries.last.name, 'README.md');
    });

    test('readFile returns document content', () async {
      final service = IdeFilesService(
        client: MockClient((request) async {
          expect(request.url.path, '/ide/file/read');
          return http.Response(
            jsonEncode(<String, dynamic>{
              'session_id': 'sess-1',
              'path': 'README.md',
              'content': '# hello\n',
            }),
            200,
          );
        }),
      );

      final document = await service.readFile(sessionId: 'sess-1', relativePath: 'README.md');
      expect(document.path, 'README.md');
      expect(document.originalContent, '# hello\n');
      expect(document.isDirty, isFalse);
    });

    test('writeFile returns save result', () async {
      final service = IdeFilesService(
        client: MockClient((request) async {
          expect(request.url.path, '/ide/file/write');
          return http.Response(
            jsonEncode(<String, dynamic>{
              'status': 'ok',
              'session_id': 'sess-1',
              'path': 'README.md',
            }),
            200,
          );
        }),
      );

      final result = await service.writeFile(
        sessionId: 'sess-1',
        relativePath: 'README.md',
        content: 'updated',
      );
      expect(result.sessionId, 'sess-1');
      expect(result.path, 'README.md');
    });

    test('parses nested decision payload for 403/409 errors', () async {
      for (final status in <int>[403, 409]) {
        final service = IdeFilesService(
          client: MockClient((request) async {
            return http.Response(
              jsonEncode(<String, dynamic>{
                'error': 'action not permitted',
                'decision': <String, dynamic>{
                  'risk': 'high',
                  'allowed': false,
                  'requires_approval': status == 409,
                  'policy_reason': 'blocked by policy',
                },
              }),
              status,
            );
          }),
        );

        expect(
          () => service.writeFile(
            sessionId: 'sess-1',
            relativePath: 'README.md',
            content: 'x',
          ),
          throwsA(
            isA<IdeFilesError>()
                .having((e) => e.statusCode, 'statusCode', status)
                .having((e) => e.risk, 'risk', 'high')
                .having((e) => e.policyReason, 'policyReason', 'blocked by policy')
                .having((e) => e.requiresApproval, 'requiresApproval', status == 409),
          ),
        );
      }
    });

    test('reopens session once on 404 and retries operation', () async {
      var step = 0;
      final service = IdeFilesService(
        client: MockClient((request) async {
          step += 1;

          if (step == 1) {
            expect(request.url.path, '/ide/session/open');
            return http.Response(jsonEncode(<String, dynamic>{'session_id': 'sess-old'}), 200);
          }
          if (step == 2) {
            expect(request.url.path, '/ide/files/tree');
            expect(request.url.queryParameters['session_id'], 'sess-old');
            return http.Response(jsonEncode(<String, dynamic>{'error': 'session not found'}), 404);
          }
          if (step == 3) {
            expect(request.url.path, '/ide/session/open');
            return http.Response(jsonEncode(<String, dynamic>{'session_id': 'sess-new'}), 200);
          }

          expect(request.url.path, '/ide/files/tree');
          expect(request.url.queryParameters['session_id'], 'sess-new');
          return http.Response(
            jsonEncode(<String, dynamic>{
              'session_id': 'sess-new',
              'path': '',
              'entries': <Map<String, dynamic>>[],
            }),
            200,
          );
        }),
      );

      final opened = await service.openIdeSession(userId: 'u1', workspacePath: '/tmp/ws');
      expect(opened, 'sess-old');

      final snapshot = await service.listDirectory(sessionId: opened, relativePath: '');
      expect(snapshot.sessionId, 'sess-new');
      expect(step, 4);
    });
  });
}
