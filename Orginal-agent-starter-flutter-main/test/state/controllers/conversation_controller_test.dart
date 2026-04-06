import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:voice_assistant/core/services/livekit_service.dart';
import 'package:voice_assistant/core/services/storage_service.dart';
import 'package:voice_assistant/state/controllers/conversation_controller.dart';
import 'package:voice_assistant/state/providers/chat_provider.dart';
import 'package:voice_assistant/state/providers/conversation_history_provider.dart';
import 'package:voice_assistant/state/providers/session_provider.dart';

class _FakeSessionProvider extends SessionProvider {
  _FakeSessionProvider() : super(LiveKitService());

  String _sessionId = 'fake-session-1';

  @override
  bool get isConnected => true;

  @override
  String? get currentSessionId => _sessionId;

  @override
  String? get currentUserId => 'test-user';

  @override
  Future<bool> reconnectWithMetadata({
    String? userId,
    Map<String, dynamic>? clientConfig,
  }) async {
    _sessionId = 'fake-session-${DateTime.now().microsecondsSinceEpoch}';
    notifyListeners();
    return true;
  }

  @override
  Future<bool> sendBootstrapContext({
    required Map<String, dynamic> payload,
    required String conversationId,
    required int bootstrapVersion,
    bool waitForAck = true,
  }) async {
    return true;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<({ChatProvider chat, ConversationHistoryProvider history, ConversationController controller})>
      buildHarness() async {
    final storage = StorageService();
    final chat = ChatProvider();
    final session = _FakeSessionProvider();
    final history = ConversationHistoryProvider(storage, chat, session);

    final deadline = DateTime.now().add(const Duration(seconds: 2));
    while (!history.initialized && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }

    final controller = ConversationController()..bind(chat, history);
    return (chat: chat, history: history, controller: controller);
  }

  group('ConversationController', () {
    test('proxies active conversation state and message list', () async {
      SharedPreferences.setMockInitialValues({});
      final harness = await buildHarness();

      harness.chat.addMessage(
        ChatMessage(
          id: 'm1',
          content: 'hello maya',
          timestamp: DateTime.now(),
          isUser: true,
          isAgent: false,
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 250));

      expect(harness.controller.activeConversationTitle, 'New chat');
      expect(harness.controller.hasMessages, isTrue);
      expect(harness.controller.messages.last.content, 'hello maya');

      harness.controller.dispose();
      harness.history.dispose();
      harness.chat.dispose();
    });

    test('derives research artifacts from active conversation snapshots', () async {
      SharedPreferences.setMockInitialValues({});
      final harness = await buildHarness();

      harness.chat.handleChatEvent({
        'type': 'research_result',
        'turn_id': 'turn-research',
        'summary': 'Python was created by Guido van Rossum.',
        'query': 'who created python',
        'sources': const [
          {
            'title': 'Python history',
            'url': 'https://example.com/python',
            'domain': 'example.com',
            'snippet': 'Created by Guido',
            'provider': 'tavily',
          },
        ],
        'timestamp': DateTime.now().millisecondsSinceEpoch,
        'trace_id': 'trace-research',
        'task_id': 'task-research',
      });
      await Future<void>.delayed(const Duration(milliseconds: 250));
      await harness.history.renameConversation(harness.history.activeConversationId, 'Research thread');

      final artifacts = harness.controller.researchArtifacts;
      expect(artifacts, hasLength(1));
      expect(artifacts.single.query, 'who created python');
      expect(artifacts.single.taskId, 'task-research');

      harness.controller.dispose();
      harness.history.dispose();
      harness.chat.dispose();
    });

    test('filters task-related messages from the active conversation', () async {
      SharedPreferences.setMockInitialValues({});
      final harness = await buildHarness();

      harness.chat.handleChatEvent({
        'type': 'system_result',
        'turn_id': 'turn-system',
        'action_type': 'SCREENSHOT',
        'success': true,
        'message': 'Saved screenshot.',
        'detail': '/tmp/maya.png',
        'rollback_available': false,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
        'task_id': 'task-system',
        'trace_id': 'trace-system',
      });
      harness.chat.handleChatEvent({
        'type': 'system_result',
        'turn_id': 'turn-system-2',
        'action_type': 'OPEN_URL',
        'success': true,
        'message': 'Opened url.',
        'detail': 'https://example.com',
        'rollback_available': false,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
        'task_id': 'task-other',
        'trace_id': 'trace-system-2',
      });
      await Future<void>.delayed(const Duration(milliseconds: 250));

      final relatedMessages = harness.controller.taskRelatedMessages('task-system');
      expect(relatedMessages, hasLength(1));
      expect(relatedMessages.single.content, 'Saved screenshot.');

      harness.controller.dispose();
      harness.history.dispose();
      harness.chat.dispose();
    });
  });
}
