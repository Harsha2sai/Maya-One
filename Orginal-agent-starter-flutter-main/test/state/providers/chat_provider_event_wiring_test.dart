import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/services/search_cue_service.dart';
import 'package:voice_assistant/state/controllers/overlay_controller.dart';
import 'package:voice_assistant/state/providers/chat_provider.dart';

class _FakeSearchCueService extends SearchCueService {
  _FakeSearchCueService() : super(playOverride: (_) async {});

  final List<String> playedCueKeys = <String>[];
  int playAttempts = 0;

  @override
  Future<bool> playCue(String turnId, {required bool soundEnabled}) async {
    playAttempts += 1;
    final played = await super.playCue(turnId, soundEnabled: soundEnabled);
    if (played) {
      playedCueKeys.add('$turnId::${CueState.searching.name}');
    }
    return played;
  }

  @override
  Future<bool> playStateCue(
    String turnId, {
    required CueState state,
    required bool soundEnabled,
  }) async {
    playAttempts += 1;
    final played = await super.playStateCue(
      turnId,
      state: state,
      soundEnabled: soundEnabled,
    );
    if (played) {
      playedCueKeys.add('$turnId::${state.name}');
    }
    return played;
  }
}

void main() {
  group('ChatProvider event wiring', () {
    late ChatProvider provider;
    late OverlayController overlayController;

    setUp(() {
      provider = ChatProvider();
      overlayController = OverlayController();
      provider.bindOverlayController(overlayController);
    });

    test('agent_thinking shows indicator state', () {
      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 't1',
        'state': 'thinking',
        'timestamp': 1,
      });

      expect(provider.agentState, AgentState.thinking);
      expect(provider.isAgentThinking, isTrue);
    });

    test('tool_execution started maps to callingTools and tool label', () {
      provider.handleChatEvent({
        'type': 'tool_execution',
        'schema_version': '1.0',
        'turn_id': 't2',
        'tool_name': 'web_search',
        'status': 'started',
        'timestamp': 2,
      });

      expect(provider.agentState, AgentState.callingTools);
      expect(provider.currentTool, 'web_search');
    });

    test('turn_complete clears thinking state', () {
      provider.updateAgentState(AgentState.callingTools, tool: 'web_search');
      provider.handleChatEvent({
        'type': 'turn_complete',
        'schema_version': '1.0',
        'turn_id': 't3',
        'status': 'success',
        'timestamp': 3,
      });

      expect(provider.agentState, AgentState.idle);
      expect(provider.isAgentThinking, isFalse);
    });

    test('error event adds safe error text, not raw payload', () {
      provider.handleChatEvent({
        'type': 'error',
        'schema_version': '1.0',
        'turn_id': 't4',
        'message': 'Traceback: internal details',
        'timestamp': 4,
      });

      expect(provider.messages, isNotEmpty);
      expect(
        provider.messages.last.content,
        'I ran into an issue while processing that. Please try again.',
      );
      expect(provider.agentState, AgentState.idle);
    });

    test('research_result updates assistant message with sources', () {
      provider.handleChatEvent({
        'type': 'assistant_final',
        'schema_version': '1.0',
        'turn_id': 't5',
        'content': 'summary text',
        'timestamp': 5,
      });
      provider.handleChatEvent({
        'type': 'research_result',
        'schema_version': '1.0',
        'turn_id': 't5',
        'query': 'latest ai news',
        'summary': 'research summary',
        'sources': const [
          {
            'title': 'Source 1',
            'url': 'https://example.com',
            'domain': 'example.com',
            'snippet': 'snippet',
            'provider': 'tavily',
          }
        ],
        'timestamp': 6,
      });

      expect(provider.messages, isNotEmpty);
      final last = provider.messages.last;
      expect(last.content, 'research summary');
      expect(last.sources.length, 1);
      expect(last.eventType, 'research_result');
    });

    test('media_result forwards toast to OverlayController and adds persistent history card', () {
      provider.handleChatEvent({
        'type': 'media_result',
        'schema_version': '1.0',
        'turn_id': 'm1',
        'action': 'play',
        'provider': 'spotify',
        'track_name': 'Song A',
        'artist': 'Artist A',
        'track_url': 'https://open.spotify.com/track/abc',
        'task_id': 'task-media-1',
        'conversation_id': 'conversation-1',
        'timestamp': 7,
      });

      // Toast now lives on OverlayController, not ChatProvider
      expect(overlayController.mediaResultToast, isNotNull);
      expect(overlayController.mediaResultToast?.trackName, 'Song A');
      expect(overlayController.mediaResultToast?.provider, 'spotify');
      final messages = provider.messages.where((m) => m.eventType == 'media_result').toList();
      expect(messages, hasLength(1));
      expect(messages.single.payload['taskId'], 'task-media-1');
      expect(messages.single.payload['conversationId'], 'conversation-1');
    });

    test('spotify status update mutates provider state', () {
      provider.updateSpotifyStatus(connected: true, displayName: 'Harsha');
      expect(provider.spotifyConnected, isTrue);
      expect(provider.spotifyDisplayName, 'Harsha');
    });

    test('system_result forwards toast to OverlayController and adds persistent history card', () {
      provider.handleChatEvent({
        'type': 'system_result',
        'schema_version': '1.0',
        'turn_id': 's1',
        'action_type': 'SCREENSHOT',
        'success': true,
        'message': 'Saved screenshot.',
        'detail': '/tmp/maya_screen.png',
        'rollback_available': false,
        'task_id': 'task-system-1',
        'conversation_id': 'conversation-2',
        'timestamp': 8,
        'trace_id': 'trace-system',
      });

      // Toast now lives on OverlayController, not ChatProvider
      expect(overlayController.systemActionToast, isNotNull);
      expect(overlayController.systemActionToast?.actionType, 'SCREENSHOT');
      final messages = provider.messages.where((m) => m.eventType == 'system_result').toList();
      expect(messages, hasLength(1));
      expect(messages.single.payload['taskId'], 'task-system-1');
      expect(messages.single.payload['conversationId'], 'conversation-2');
    });

    test('confirmation_required forwards prompt to OverlayController and inserts history card', () {
      provider.handleChatEvent({
        'type': 'confirmation_required',
        'schema_version': '1.0',
        'action_type': 'FILE_DELETE',
        'description': 'Delete test.txt',
        'destructive': true,
        'timeout_seconds': 30,
        'timestamp': 9,
        'trace_id': 'trace-confirm',
      });

      // Confirmation state now lives on OverlayController, not ChatProvider
      expect(overlayController.pendingConfirmation, isNotNull);
      expect(overlayController.pendingConfirmation?.traceId, 'trace-confirm');
      expect(provider.messages.last.eventType, 'confirmation_required');
    });

    test('confirmation_response clears OverlayController confirmation via resolveConfirmationLocally', () {
      provider.handleChatEvent({
        'type': 'confirmation_required',
        'schema_version': '1.0',
        'action_type': 'FILE_DELETE',
        'description': 'Delete test.txt',
        'destructive': true,
        'timeout_seconds': 30,
        'timestamp': 10,
        'trace_id': 'trace-confirm',
      });

      provider.handleChatEvent({
        'type': 'confirmation_response',
        'schema_version': '1.0',
        'confirmed': false,
        'trace_id': 'trace-confirm',
        'timestamp': 11,
      });

      expect(overlayController.pendingConfirmation, isNull);
      expect(provider.messages.where((m) => m.id == 'confirmation_trace-confirm'), isEmpty);
    });

    test('assistant_final is suppressed for same turn during structured suppression window', () {
      provider.handleChatEvent({
        'type': 'research_result',
        'schema_version': '1.0',
        'turn_id': 'turn-structured',
        'query': 'latest ai news',
        'summary': 'Structured summary',
        'timestamp': 12,
      });

      provider.handleChatEvent({
        'type': 'assistant_final',
        'schema_version': '1.0',
        'turn_id': 'turn-structured',
        'content': 'Structured summary',
        'timestamp': 13,
      });

      final turnMessages = provider.messages.where((m) => m.turnId == 'turn-structured').toList();
      expect(turnMessages, hasLength(1));
      expect(turnMessages.single.eventType, 'research_result');
    });

    test('structured suppression does not chain across turns and expires after 8 seconds', () {
      var now = DateTime(2026, 3, 14, 10, 0, 0);
      provider.setNowProviderForTesting(() => now);

      provider.handleChatEvent({
        'type': 'research_result',
        'schema_version': '1.0',
        'turn_id': 'turn-a',
        'summary': 'Turn A summary',
        'timestamp': 14,
      });

      provider.handleChatEvent({
        'type': 'assistant_final',
        'schema_version': '1.0',
        'turn_id': 'turn-a',
        'content': 'Turn A plain duplicate',
        'timestamp': 15,
      });

      // New turn should not be suppressed by previous turn's structured card.
      provider.handleChatEvent({
        'type': 'assistant_final',
        'schema_version': '1.0',
        'turn_id': 'turn-b',
        'content': 'Turn B final',
        'timestamp': 16,
      });
      expect(provider.messages.where((m) => m.turnId == 'turn-b' && m.eventType == 'assistant_final'), hasLength(1));

      // Same turn is allowed after suppression expiry.
      now = now.add(const Duration(seconds: 9));
      provider.handleChatEvent({
        'type': 'assistant_final',
        'schema_version': '1.0',
        'turn_id': 'turn-a',
        'content': 'Turn A after window',
        'timestamp': 17,
      });
      expect(
        provider.messages.where((m) => m.turnId == 'turn-a' && m.eventType == 'assistant_final'),
        hasLength(1),
      );
    });

    test('search cue plays exactly once per turn for agent_thinking:searching', () async {
      final cueService = _FakeSearchCueService();
      provider = ChatProvider(
        searchCueService: cueService,
        soundEffectsEnabled: true,
      );
      provider.bindOverlayController(overlayController);

      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 'search-turn',
        'state': 'searching',
        'timestamp': 18,
      });
      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 'search-turn',
        'state': 'searching',
        'timestamp': 19,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(
        cueService.playedCueKeys.where((key) => key == 'search-turn::searching'),
        hasLength(1),
      );
    });

    test('search cue does not play for non-searching thinking states', () async {
      final cueService = _FakeSearchCueService();
      provider = ChatProvider(
        searchCueService: cueService,
        soundEffectsEnabled: true,
      );
      provider.bindOverlayController(overlayController);

      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 'think-turn',
        'state': 'thinking',
        'timestamp': 20,
      });
      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 'write-turn',
        'state': 'writing',
        'timestamp': 21,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(cueService.playedCueKeys, isEmpty);
    });

    test('search cue is skipped when sound effects are disabled', () async {
      final cueService = _FakeSearchCueService();
      provider = ChatProvider(
        searchCueService: cueService,
        soundEffectsEnabled: false,
      );
      provider.bindOverlayController(overlayController);

      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 'sound-off-turn',
        'state': 'searching',
        'timestamp': 22,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(cueService.playedCueKeys, isEmpty);
    });

    test('tool_execution started triggers tool-calling cue once per turn burst', () async {
      final cueService = _FakeSearchCueService();
      provider = ChatProvider(
        searchCueService: cueService,
        soundEffectsEnabled: true,
      );
      provider.bindOverlayController(overlayController);

      provider.handleChatEvent({
        'type': 'tool_execution',
        'schema_version': '1.0',
        'turn_id': 'tool-turn',
        'tool_name': 'web_search',
        'status': 'started',
        'timestamp': 22,
      });
      provider.handleChatEvent({
        'type': 'tool_execution',
        'schema_version': '1.0',
        'turn_id': 'tool-turn',
        'tool_name': 'web_search',
        'status': 'started',
        'timestamp': 23,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(
        cueService.playedCueKeys.where((key) => key == 'tool-turn::toolCalling'),
        hasLength(1),
      );
    });

    test('turn_complete triggers completion cue and allows replay on later turn', () async {
      final cueService = _FakeSearchCueService();
      provider = ChatProvider(
        searchCueService: cueService,
        soundEffectsEnabled: true,
      );
      provider.bindOverlayController(overlayController);

      provider.handleChatEvent({
        'type': 'turn_complete',
        'schema_version': '1.0',
        'turn_id': 'complete-turn',
        'timestamp': 24,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));

      provider.handleChatEvent({
        'type': 'turn_complete',
        'schema_version': '1.0',
        'turn_id': 'complete-turn',
        'timestamp': 25,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(
        cueService.playedCueKeys.where((key) => key == 'complete-turn::completed'),
        hasLength(2),
      );
    });

    test('turn_complete clears cue state so same turn can play again', () async {
      final cueService = _FakeSearchCueService();
      provider = ChatProvider(
        searchCueService: cueService,
        soundEffectsEnabled: true,
      );
      provider.bindOverlayController(overlayController);

      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 'repeat-turn',
        'state': 'searching',
        'timestamp': 23,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));
      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 'repeat-turn',
        'state': 'searching',
        'timestamp': 24,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));
      provider.handleChatEvent({
        'type': 'turn_complete',
        'schema_version': '1.0',
        'turn_id': 'repeat-turn',
        'timestamp': 25,
      });
      provider.handleChatEvent({
        'type': 'agent_thinking',
        'schema_version': '1.0',
        'turn_id': 'repeat-turn',
        'state': 'searching',
        'timestamp': 26,
      });
      await Future<void>.delayed(const Duration(milliseconds: 10));

      expect(
        cueService.playedCueKeys.where((key) => key == 'repeat-turn::searching'),
        hasLength(2),
      );
    });
  });
}
