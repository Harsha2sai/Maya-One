import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:voice_assistant/core/services/livekit_service.dart';
import 'package:voice_assistant/core/services/storage_service.dart';
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

  Future<ConversationHistoryProvider> buildProvider() async {
    final storage = StorageService();
    final chat = ChatProvider();
    final session = _FakeSessionProvider();
    final provider = ConversationHistoryProvider(storage, chat, session);

    final deadline = DateTime.now().add(const Duration(seconds: 2));
    while (!provider.initialized && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }

    return provider;
  }

  group('ConversationHistoryProvider', () {
    test('migrates legacy conversation titles into the structured store once', () async {
      SharedPreferences.setMockInitialValues({
        'conversation_history': <String>['Voice planning thread', 'Research follow-up'],
      });

      final provider = await buildProvider();
      final storage = StorageService();

      expect(provider.initialized, isTrue);
      expect(
        provider.conversations.map((conversation) => conversation.title),
        containsAll(<String>['Voice planning thread', 'Research follow-up']),
      );
      expect(await storage.isConversationMigrationComplete(), isTrue);
      expect(await storage.loadConversationStore(), isNotNull);

      provider.dispose();
    });

    test('falls back to a blank chat when legacy history is malformed', () async {
      SharedPreferences.setMockInitialValues({
        'conversation_history': 'invalid_legacy_payload',
      });

      final provider = await buildProvider();
      final storage = StorageService();

      expect(provider.initialized, isTrue);
      expect(provider.conversations, hasLength(1));
      expect(provider.conversations.single.title, 'New chat');
      expect(await storage.isConversationMigrationComplete(), isTrue);

      provider.dispose();
    });

    test('createConversation adds a blank thread and activates it', () async {
      SharedPreferences.setMockInitialValues({});

      final provider = await buildProvider();

      expect(provider.conversations, hasLength(1));
      final originalConversationId = provider.activeConversationId;

      final created = await provider.createConversation();

      expect(created, isTrue);
      expect(provider.conversations, hasLength(2));
      expect(provider.activeConversationId, isNot(originalConversationId));
      expect(provider.activeConversation?.title, 'New chat');

      provider.dispose();
    });

    test('archive and restore move conversations between active and archived lists', () async {
      SharedPreferences.setMockInitialValues({});

      final provider = await buildProvider();
      await provider.renameConversation(provider.activeConversationId, 'Primary thread');
      await provider.createConversation();
      await provider.renameConversation(provider.activeConversationId, 'Archived thread');

      final archivedConversationId = provider.activeConversationId;
      await provider.archiveConversation(archivedConversationId);

      expect(
        provider.archivedConversations.map((conversation) => conversation.title),
        contains('Archived thread'),
      );
      expect(
        provider.conversations.map((conversation) => conversation.title),
        isNot(contains('Archived thread')),
      );

      await provider.restoreConversation(archivedConversationId);

      expect(
        provider.conversations.map((conversation) => conversation.title),
        contains('Archived thread'),
      );
      expect(provider.archivedConversations, isEmpty);

      provider.dispose();
    });
  });
}
