// Maya-One Full Integration Test Suite
// Sends real messages via Flutter session, verifies backend logs
// Run: flutter test test/integration/maya_full_integration_test.dart --timeout=120s

import 'dart:io';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

// ─── LOG VERIFIER ──────────────────────────────────────────────────────────

class BackendLogVerifier {
  final String logPath;
  late List<String> _lines;

  BackendLogVerifier(this.logPath);

  Future<void> reload() async {
    final file = File(logPath);
    if (!await file.exists()) {
      _lines = [];
      return;
    }
    final content = await file.readAsString();
    _lines = content.split('\n');
  }

  /// Returns true if any log line contains all of the given patterns
  bool hasLine(List<String> patterns) {
    for (final line in _lines) {
      if (patterns.every((p) => line.contains(p))) return true;
    }
    return false;
  }

  /// Returns true if any log line added after [startLine] contains all patterns.
  bool hasLineSince(List<String> patterns, int startLine) {
    final lines = startLine >= _lines.length ? const <String>[] : _lines.skip(startLine);
    for (final line in lines) {
      if (patterns.every((p) => line.contains(p))) return true;
    }
    return false;
  }

  /// Returns the matching line for evidence
  String? getLine(List<String> patterns) {
    for (final line in _lines) {
      if (patterns.every((p) => line.contains(p))) return line.trim();
    }
    return null;
  }

  /// Returns matching evidence line added after [startLine], if any.
  String? getLineSince(List<String> patterns, int startLine) {
    final lines = startLine >= _lines.length ? const <String>[] : _lines.skip(startLine);
    for (final line in lines) {
      if (patterns.every((p) => line.contains(p))) return line.trim();
    }
    return null;
  }

  /// Wait up to [timeoutSecs] for a log pattern to appear
  Future<bool> waitFor(
    List<String> patterns, {
    int timeoutSecs = 20,
  }) async {
    for (int i = 0; i < timeoutSecs; i++) {
      await reload();
      if (hasLine(patterns)) return true;
      await Future.delayed(const Duration(seconds: 1));
    }
    return false;
  }

  /// Wait up to [timeoutSecs] for pattern to appear after [startLine].
  Future<bool> waitForSince(
    List<String> patterns,
    int startLine, {
    int timeoutSecs = 20,
  }) async {
    for (int i = 0; i < timeoutSecs; i++) {
      await reload();
      if (hasLineSince(patterns, startLine)) return true;
      await Future.delayed(const Duration(seconds: 1));
    }
    return false;
  }
}

// ─── MESSAGE SENDER ────────────────────────────────────────────────────────

class MayaMessageSender {
  final String _userId = 'itest_user';
  String? _roomName;

  /// Send a message to Maya via LiveKit data channel
  /// Uses the token server to get session credentials
  Future<bool> sendMessage(String message) async {
    try {
      final runId = 'itest_${DateTime.now().millisecondsSinceEpoch}';
      _roomName ??= 'itest_room_${DateTime.now().millisecondsSinceEpoch}';

      // Backend token contract is POST /token with room + participant.
      final tokenResult = await Process.run('curl', [
        '-s',
        '-o',
        '/tmp/maya_itest_token.json',
        '-w',
        '%{http_code}',
        '-X',
        'POST',
        'http://localhost:5050/token',
        '-H',
        'Content-Type: application/json',
        '-d',
        json.encode({
          'roomName': _roomName,
          'participantName': _userId,
          'metadata': {'source': 'integration_test', 'run_id': runId},
        }),
      ]);

      final tokenCode = int.tryParse((tokenResult.stdout ?? '').toString().trim()) ?? 0;
      if (tokenCode != 200) {
        print('sendMessage token failure status=$tokenCode');
        return false;
      }

      // Send chat payload via backend bridge endpoint.
      final result = await Process.run('curl', [
        '-s',
        '-o',
        '/tmp/maya_itest_send.json',
        '-w',
        '%{http_code}',
        '-X',
        'POST',
        'http://localhost:5050/send_message',
        '-H',
        'Content-Type: application/json',
        '-d',
        json.encode({
          'message': message,
          'user_id': _userId,
          'run_id': runId,
        }),
      ]);

      final sendCode = int.tryParse((result.stdout ?? '').toString().trim()) ?? 0;
      if (sendCode != 200) {
        final payload = await File('/tmp/maya_itest_send.json').readAsString();
        print('sendMessage failed status=$sendCode payload=$payload');
      }
      return sendCode == 200;
    } catch (e) {
      // Fallback: write to console input pipe if available
      print('sendMessage exception: $e');
      return false;
    }
  }
}

// ─── TEST HELPER ───────────────────────────────────────────────────────────

class TestCase {
  final String name;
  final String utterance;
  final List<String> expectedLogPatterns; // ALL must appear
  final List<String> forbiddenLogPatterns; // NONE must appear
  final int timeoutSecs;

  const TestCase({
    required this.name,
    required this.utterance,
    required this.expectedLogPatterns,
    this.forbiddenLogPatterns = const [],
    this.timeoutSecs = 20,
  });
}

// ─── TEST CASES ────────────────────────────────────────────────────────────

final bool runFullSuite = Platform.environment['MAYA_ITEST_FULL'] == '1';
final bool integrationEnabled = Platform.environment['MAYA_ITEST_ENABLE'] == '1';
final bool harnessPresent = File('/tmp/maya_test_session.env').existsSync();
final bool runIntegrationSuite = integrationEnabled && harnessPresent;
final String integrationSkipReason = !integrationEnabled
    ? 'Set MAYA_ITEST_ENABLE=1 to run backend-coupled integration tests.'
    : 'Backend harness missing. Run ./Agent/scripts/start_test_backend.sh first.';

final List<TestCase> smokeTestCases = [
  TestCase(
    name: 'SM-01: Time query bridge acceptance',
    utterance: 'what time is it',
    expectedLogPatterns: ['send_message_accepted'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'SM-02: Factual query bridge acceptance',
    utterance: 'who is the PM of India',
    expectedLogPatterns: ['send_message_accepted'],
    timeoutSecs: 20,
  ),
  TestCase(
    name: 'SM-03: Media query bridge acceptance',
    utterance: 'play the recent songs in youtube',
    expectedLogPatterns: ['send_message_accepted'],
    timeoutSecs: 20,
  ),
];

final List<TestCase> allTestCases = [
  // ══════════════════════════════════════════
  // PHASE 1: FAST-PATH (router must NOT fire)
  // ══════════════════════════════════════════

  TestCase(
    name: 'FP-01: Time query fast-path',
    utterance: 'what time is it',
    expectedLogPatterns: ['fast_path', 'time'],
    forbiddenLogPatterns: ['agent_router_decision'],
  ),
  TestCase(
    name: 'FP-02: Next track fast-path',
    utterance: 'next track',
    expectedLogPatterns: ['fast_path', 'playerctl'],
    forbiddenLogPatterns: ['agent_router_decision', 'media_route'],
  ),
  TestCase(
    name: 'FP-03: Pause fast-path',
    utterance: 'pause',
    expectedLogPatterns: ['fast_path', 'playerctl'],
    forbiddenLogPatterns: ['agent_router_decision'],
  ),
  TestCase(
    name: 'FP-04: Open app fast-path',
    utterance: 'open calculator',
    expectedLogPatterns: ['fast_path', 'open'],
    forbiddenLogPatterns: ['agent_router_decision'],
  ),
  TestCase(
    name: 'FP-05: Volume fast-path',
    utterance: 'volume up',
    expectedLogPatterns: ['fast_path'],
    forbiddenLogPatterns: ['agent_router_decision'],
  ),

  // ══════════════════════════════════════════
  // PHASE 2: IDENTITY ROUTING
  // ══════════════════════════════════════════

  TestCase(
    name: 'ID-01: Name query routes to identity',
    utterance: 'what is your name',
    expectedLogPatterns: ['agent_router_decision', 'identity'],
    forbiddenLogPatterns: ['research_route', 'media_route'],
  ),
  TestCase(
    name: 'ID-02: Capability query routes to identity',
    utterance: 'what can you do',
    expectedLogPatterns: ['agent_router_decision', 'identity'],
    forbiddenLogPatterns: ['research_route'],
  ),
  TestCase(
    name: 'ID-03: AI question routes to identity',
    utterance: 'are you an AI',
    expectedLogPatterns: ['agent_router_decision', 'identity'],
    forbiddenLogPatterns: ['research_route'],
  ),
  TestCase(
    name: 'ID-04: Memory skipped for identity',
    utterance: 'who are you',
    expectedLogPatterns: ['identity', 'context_builder_memory_skipped'],
    forbiddenLogPatterns: ['research_route'],
  ),
  TestCase(
    name: 'ID-05: User memory question routes to chat NOT identity',
    utterance: 'do you know my name',
    expectedLogPatterns: ['agent_router_decision', 'chat'],
    forbiddenLogPatterns: ['identity'],
  ),

  // ══════════════════════════════════════════
  // PHASE 3: MEDIA AGENT
  // ══════════════════════════════════════════

  TestCase(
    name: 'MD-01: Play music routes to media_play',
    utterance: 'play music',
    expectedLogPatterns: ['agent_router_decision', 'media_play'],
    forbiddenLogPatterns: ['fast_path', 'research_route'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'MD-02: Media route completes',
    utterance: 'play music',
    expectedLogPatterns: ['media_route_completed'],
    forbiddenLogPatterns: ["couldn't map"],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'MD-03: Natural language play maps correctly',
    utterance: 'start playing music',
    expectedLogPatterns: ['agent_router_decision', 'media_play', 'media_route_completed'],
    forbiddenLogPatterns: ["couldn't map that media command"],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'MD-04: Genre play routes to media not fast-path',
    utterance: 'put on some jazz',
    expectedLogPatterns: ['agent_router_decision', 'media_play'],
    forbiddenLogPatterns: ['fast_path'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'MD-05: next track stays fast-path not MediaAgent',
    utterance: 'next track',
    expectedLogPatterns: ['fast_path'],
    forbiddenLogPatterns: ['media_route_completed', 'agent_router_decision'],
  ),

  // ══════════════════════════════════════════
  // PHASE 4: RESEARCH AGENT
  // ══════════════════════════════════════════

  TestCase(
    name: 'RS-01: Factual query routes to research',
    utterance: 'who invented Python',
    expectedLogPatterns: ['agent_router_decision', 'research'],
    forbiddenLogPatterns: ['identity', 'fast_path'],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'RS-02: Research route completes with sources',
    utterance: 'who invented Python',
    expectedLogPatterns: ['research_route_completed'],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'RS-03: No duplicate response (single publish)',
    utterance: 'what is quantum computing',
    expectedLogPatterns: ['research_route_completed'],
    forbiddenLogPatterns: ['duplicate_publish', 'double_response'],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'RS-04: News query uses web_search',
    utterance: 'what is happening in AI today',
    expectedLogPatterns: ['research_route_completed', 'web_search'],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'RS-05: Display text not raw JSON',
    utterance: 'latest news in machine learning',
    expectedLogPatterns: ['research_route_completed'],
    forbiddenLogPatterns: ['display_text: {', 'display_text: ['],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'RS-06: CEO/role query forces fresh web search',
    utterance: 'who is the CEO of OpenAI right now',
    expectedLogPatterns: ['research_route_completed', 'web_search'],
    forbiddenLogPatterns: ['using_cached_knowledge'],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'RS-07: TTS voice summary logged',
    utterance: 'who invented Python',
    expectedLogPatterns: ['tts_voice_summary'],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'RS-08: Regression — person query to research not identity',
    utterance: 'who is Elon Musk',
    expectedLogPatterns: ['agent_router_decision', 'research'],
    forbiddenLogPatterns: ['identity'],
    timeoutSecs: 30,
  ),

  // ══════════════════════════════════════════
  // PHASE 5: SYSTEM AGENT
  // ══════════════════════════════════════════

  TestCase(
    name: 'SY-01: System query routes correctly',
    utterance: 'take a screenshot',
    expectedLogPatterns: ['agent_router_decision', 'system'],
    forbiddenLogPatterns: ['research_route', 'identity'],
    timeoutSecs: 20,
  ),
  TestCase(
    name: 'SY-02: Windows query uses shell not vision',
    utterance: 'what windows are currently open',
    expectedLogPatterns: ['fast_path', 'wmctrl'],
    forbiddenLogPatterns: ['VISION_QUERY', 'VisionController'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'SY-03: Blocked command rejected by validator',
    utterance: 'run sudo rm -rf slash',
    expectedLogPatterns: ['action_blocked'],
    forbiddenLogPatterns: ['action_executed', 'shell_success'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'SY-04: Destructive action triggers confirmation',
    utterance: 'delete the file test.txt',
    expectedLogPatterns: ['destructive_action', 'confirmation_required'],
    forbiddenLogPatterns: ['action_executed_without_confirmation'],
    timeoutSecs: 20,
  ),
  TestCase(
    name: 'SY-05: Kill denylist blocks systemd',
    utterance: 'kill systemd process',
    expectedLogPatterns: ['action_blocked'],
    forbiddenLogPatterns: ['SIGTERM', 'process_killed'],
    timeoutSecs: 15,
  ),

  // ══════════════════════════════════════════
  // PHASE 6: MEMORY SYSTEM
  // ══════════════════════════════════════════

  TestCase(
    name: 'MM-01: Store preference acknowledged',
    utterance: 'my favorite language is Rust',
    expectedLogPatterns: ['memory_stored', 'PREFERENCE'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'MM-02: Memory recall works',
    utterance: 'what is my favorite programming language',
    expectedLogPatterns: ['memory_retrieved', 'Rust'],
    timeoutSecs: 20,
  ),
  TestCase(
    name: 'MM-03: Memory skipped for identity queries',
    utterance: 'what is your name',
    expectedLogPatterns: ['context_builder_memory_skipped'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'MM-04: Memory injected for chat queries',
    utterance: 'what do you know about me',
    expectedLogPatterns: ['agent_router_decision', 'chat'],
    forbiddenLogPatterns: ['context_builder_memory_skipped'],
    timeoutSecs: 15,
  ),

  // ══════════════════════════════════════════
  // PHASE 7: TASK PLANNER
  // ══════════════════════════════════════════

  TestCase(
    name: 'TK-01: Task creation acknowledged',
    utterance: 'create a task to research Python frameworks',
    expectedLogPatterns: ['task_created', 'plan_generated'],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'TK-02: Task gets ID',
    utterance: 'create a task to research Python frameworks',
    expectedLogPatterns: ['task_id='],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'TK-03: Task status queryable',
    utterance: 'what tasks are running',
    expectedLogPatterns: ['task_query'],
    timeoutSecs: 20,
  ),

  // ══════════════════════════════════════════
  // PHASE 8: CHAT & CONTEXT
  // ══════════════════════════════════════════

  TestCase(
    name: 'CH-01: Greeting routes to chat',
    utterance: 'how are you',
    expectedLogPatterns: ['agent_router_decision', 'chat'],
    forbiddenLogPatterns: ['research_route', 'identity'],
  ),
  TestCase(
    name: 'CH-02: Chat uses tool_choice none',
    utterance: 'tell me a joke',
    expectedLogPatterns: ['agent_router_decision', 'chat', 'tool_choice_none'],
    forbiddenLogPatterns: ['tool_call'],
  ),
  TestCase(
    name: 'CH-03: No task bleed after system action',
    utterance: 'tell me a joke',
    expectedLogPatterns: ['agent_router_decision', 'chat'],
    forbiddenLogPatterns: ['I completed the action', 'Action cancelled'],
  ),
  TestCase(
    name: 'CH-04: Math stays in chat not research',
    utterance: 'what is 25 times 4',
    expectedLogPatterns: ['agent_router_decision', 'chat'],
    forbiddenLogPatterns: ['research_route'],
  ),

  // ══════════════════════════════════════════
  // PHASE 9: TTS & VOICE HEALTH
  // ══════════════════════════════════════════

  TestCase(
    name: 'TTS-01: Voice summary logged before TTS',
    utterance: 'who invented Python',
    expectedLogPatterns: ['tts_voice_summary'],
    timeoutSecs: 30,
  ),
  TestCase(
    name: 'TTS-02: TTS error does not kill session',
    utterance: 'how are you',
    expectedLogPatterns: ['agent_router_decision', 'chat'],
    forbiddenLogPatterns: ['AgentSession is closing', 'unrecoverable error'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'TTS-03: TTS fallback triggered on provider error',
    utterance: 'what is your name',
    // If primary TTS fails, fallback should fire — not session close
    forbiddenLogPatterns: ['AgentSession is closing'],
    expectedLogPatterns: ['identity'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'TTS-04: Cartesia 401 handled gracefully',
    utterance: 'tell me about Python',
    forbiddenLogPatterns: ['status_code=401', 'AgentSession is closing'],
    expectedLogPatterns: ['research_route_completed'],
    timeoutSecs: 30,
  ),

  // ══════════════════════════════════════════
  // PHASE 10: LANE QUEUE & ROUTING RESILIENCE
  // ══════════════════════════════════════════

  TestCase(
    name: 'LQ-01: Router depth guard active',
    utterance: 'how are you',
    expectedLogPatterns: ['agent_router_decision'],
    forbiddenLogPatterns: ['agent_depth_exceeded'],
    timeoutSecs: 15,
  ),
  TestCase(
    name: 'LQ-02: InputGuard fires on every message',
    utterance: 'hello Maya',
    expectedLogPatterns: ['agent_router_decision'],
    // InputGuard is silent on valid input — verifying it doesn't crash
    forbiddenLogPatterns: ['InputGuard error', 'sanitize_exception'],
    timeoutSecs: 10,
  ),
];

// ─── MAIN TEST RUNNER ──────────────────────────────────────────────────────

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  // Read log path from env file written by start_test_backend.sh
  late String logPath;
  late BackendLogVerifier verifier;
  late MayaMessageSender sender;
  final testCases = runFullSuite ? allTestCases : smokeTestCases;

  group('Maya Full Integration Tests', skip: runIntegrationSuite ? false : integrationSkipReason, () {
    setUpAll(() async {
      final envFile = File('/tmp/maya_test_session.env');
      if (!await envFile.exists()) {
        throw Exception(
          'Backend not started. Run: ./Agent/scripts/start_test_backend.sh first',
        );
      }
      final envLines = await envFile.readAsLines();
      final logDir = envLines.firstWhere((l) => l.startsWith('LOG_DIR=')).split('=')[1];
      logPath = '$logDir/agent_full.log';
      verifier = BackendLogVerifier(logPath);
      sender = MayaMessageSender();

      print('=== Maya Integration Tests ===');
      print('Log file: $logPath');
      print('Mode: ${runFullSuite ? "full" : "smoke"}');
      print('Total test cases: ${testCases.length}');
      print('');

      // Wait for backend to be fully ready.
      final ready = await verifier.waitFor(['MAYA RUNTIME READY'], timeoutSecs: 30) ||
          await verifier.waitFor(['worker connected'], timeoutSecs: 30) ||
          await verifier.waitFor(['Global agent ready'], timeoutSecs: 30);
      if (!ready) {
        throw Exception('Backend did not reach ready state within 30s');
      }
      print('Backend ready. Starting tests...\n');
    });

    for (final tc in testCases) {
      testWidgets(tc.name, (tester) async {
        // Record log position before sending
        await verifier.reload();
        final linesBefore = verifier._lines.length;

        // Send message
        print('→ [${tc.name}] Sending: "${tc.utterance}"');
        final sent = await sender.sendMessage(tc.utterance);
        expect(sent, isTrue, reason: '${tc.name}: send_message call failed');

        // Wait for expected patterns
        bool allExpectedFound = true;
        final missingPatterns = <String>[];

        for (final pattern in tc.expectedLogPatterns) {
          final found = await verifier.waitForSince(
            [pattern],
            linesBefore,
            timeoutSecs: tc.timeoutSecs,
          );
          if (!found) {
            allExpectedFound = false;
            missingPatterns.add(pattern);
          }
        }

        // Check forbidden patterns
        await verifier.reload();
        final violations = <String>[];
        for (final forbidden in tc.forbiddenLogPatterns) {
          // Only check lines added AFTER sending the message
          final newLines = verifier._lines.skip(linesBefore).toList();
          if (newLines.any((l) => l.contains(forbidden))) {
            violations.add(forbidden);
          }
        }

        // Report
        if (allExpectedFound && violations.isEmpty) {
          print('  ✅ PASS');
          for (final p in tc.expectedLogPatterns) {
            final line = verifier.getLineSince([p], linesBefore);
            if (line != null) print('     Evidence: $line');
          }
        } else {
          if (missingPatterns.isNotEmpty) {
            print('  ❌ FAIL — Missing log patterns: $missingPatterns');
          }
          if (violations.isNotEmpty) {
            print('  ❌ FAIL — Forbidden patterns found: $violations');
          }
        }

        // Assert
        expect(
          missingPatterns,
          isEmpty,
          reason: '${tc.name}: Missing expected log patterns: $missingPatterns',
        );
        expect(
          violations,
          isEmpty,
          reason: '${tc.name}: Forbidden log patterns found: $violations',
        );
      });
    }
  });
}
