import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/state/models/conversation_models.dart';
import 'package:voice_assistant/state/controllers/workspace_controller.dart';
import 'package:voice_assistant/state/providers/conversation_history_provider.dart';
import 'package:voice_assistant/widgets/layout/shell_sidebar.dart';

class _StubConversationHistoryProvider extends ChangeNotifier
    implements ConversationHistoryProvider {
  final List<ConversationRecord> _records;
  final List<ProjectRecord> _projects;
  String _activeConversationId;

  _StubConversationHistoryProvider({
    required List<ConversationRecord> conversations,
    required String activeConversationId,
    List<ProjectRecord> projects = const <ProjectRecord>[],
  })  : _records = List<ConversationRecord>.from(conversations),
        _projects = List<ProjectRecord>.from(projects),
        _activeConversationId = activeConversationId;

  @override
  List<ConversationRecord> get conversations => List.unmodifiable(
        _records.where((conversation) => !conversation.archived).toList()
          ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt)),
      );

  @override
  List<ProjectRecord> get projects => List.unmodifiable(_projects);

  @override
  String get activeConversationId => _activeConversationId;

  @override
  bool get hasRunningTask => false;

  @override
  bool get isSwitchingConversation => false;

  @override
  String get switchStatus => '';

  @override
  Future<bool> createConversation({bool allowTaskInterruption = false}) async {
    final now = DateTime.now();
    final conversation = ConversationRecord(
      id: 'conv_${_records.length + 1}',
      title: 'New chat',
      preview: '',
      createdAt: now,
      updatedAt: now,
      archived: false,
      messages: const <ConversationMessageSnapshot>[],
      resumeContext: ConversationResumeContext(updatedAt: now),
    );
    _records.insert(0, conversation);
    _activeConversationId = conversation.id;
    notifyListeners();
    return true;
  }

  @override
  Future<bool> activateConversation(
    String conversationId, {
    bool allowTaskInterruption = false,
  }) async {
    if (_records.where((record) => record.id == conversationId).isEmpty) {
      return false;
    }
    _activeConversationId = conversationId;
    notifyListeners();
    return true;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) {
    return super.noSuchMethod(invocation);
  }
}

ConversationRecord _conversation({
  required String id,
  required String title,
  required DateTime timestamp,
}) {
  return ConversationRecord(
    id: id,
    title: title,
    preview: 'preview',
    createdAt: timestamp,
    updatedAt: timestamp,
    archived: false,
    messages: const <ConversationMessageSnapshot>[],
    resumeContext: ConversationResumeContext(updatedAt: timestamp),
  );
}

Future<void> _pumpSidebar(
  WidgetTester tester, {
  required ConversationHistoryProvider history,
  required WorkspaceController workspace,
}) async {
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationHistoryProvider>.value(value: history),
        ChangeNotifierProvider<WorkspaceController>.value(value: workspace),
      ],
      child: MaterialApp(
        home: Scaffold(
          body: ShellSidebar(
            activePage: 'home',
            onNavigate: (page) => workspace.setCurrentPage(page),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 250));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> setViewport(
    WidgetTester tester, {
    required double width,
    required double height,
  }) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = Size(width, height);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    await tester.pump();
  }

  group('ShellSidebar', () {
    testWidgets('renders provider-backed conversation rows', (tester) async {
      await setViewport(tester, width: 1440, height: 1900);
      final now = DateTime.now();
      final history = _StubConversationHistoryProvider(
        conversations: <ConversationRecord>[
          _conversation(id: 'conv_1', title: 'Thread One', timestamp: now),
          _conversation(id: 'conv_2', title: 'Thread Two', timestamp: now.add(const Duration(seconds: 1))),
        ],
        activeConversationId: 'conv_2',
      );
      final workspace = WorkspaceController();
      addTearDown(history.dispose);
      addTearDown(workspace.dispose);

      await _pumpSidebar(tester, history: history, workspace: workspace);

      expect(find.text('Thread One'), findsOneWidget);
      expect(find.text('Thread Two'), findsOneWidget);
      expect(find.byKey(const Key('sidebar_new_chat_button')), findsOneWidget);
    });

    testWidgets('new chat button creates and activates a blank thread', (tester) async {
      await setViewport(tester, width: 1440, height: 1900);
      final now = DateTime.now();
      final history = _StubConversationHistoryProvider(
        conversations: <ConversationRecord>[
          _conversation(id: 'conv_1', title: 'Thread One', timestamp: now),
        ],
        activeConversationId: 'conv_1',
      );
      final workspace = WorkspaceController();
      addTearDown(history.dispose);
      addTearDown(workspace.dispose);

      await _pumpSidebar(tester, history: history, workspace: workspace);
      final beforeCount = history.conversations.length;

      await tester.tap(find.byKey(const Key('sidebar_new_chat_button')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(history.conversations.length, beforeCount + 1);
      expect(history.activeConversationId, 'conv_2');
      expect(workspace.currentPage, 'home');
    });

    testWidgets('overflow menu exposes thread actions', (tester) async {
      await setViewport(tester, width: 1440, height: 1900);
      final now = DateTime.now();
      final history = _StubConversationHistoryProvider(
        conversations: <ConversationRecord>[
          _conversation(id: 'conv_1', title: 'Action Thread', timestamp: now),
        ],
        activeConversationId: 'conv_1',
      );
      final workspace = WorkspaceController();
      addTearDown(history.dispose);
      addTearDown(workspace.dispose);

      await _pumpSidebar(tester, history: history, workspace: workspace);

      await tester.tap(find.byKey(const Key('sidebar_chat_menu_conv_1')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));

      expect(find.text('Rename'), findsOneWidget);
      expect(find.text('Export chat'), findsOneWidget);
      expect(find.text('Move to project'), findsOneWidget);
      expect(find.text('Archive'), findsOneWidget);
      expect(find.text('Delete'), findsOneWidget);
    });
  });
}
