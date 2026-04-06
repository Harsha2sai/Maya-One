import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:voice_assistant/core/services/livekit_service.dart';
import 'package:voice_assistant/state/controllers/agent_activity_controller.dart';
import 'package:voice_assistant/state/controllers/overlay_controller.dart';
import 'package:voice_assistant/state/controllers/workspace_controller.dart';
import 'package:voice_assistant/state/models/overlay_models.dart';
import 'package:voice_assistant/state/models/workspace_models.dart';
import 'package:voice_assistant/state/providers/session_provider.dart';
import 'package:voice_assistant/widgets/features/chat/confirmation_card.dart';
import 'package:voice_assistant/widgets/features/chat/media_result_bubble.dart';
import 'package:voice_assistant/widgets/features/chat/system_action_bubble.dart';
import 'package:voice_assistant/widgets/overlays/global_overlay_host.dart';

class _FakeSessionProvider extends SessionProvider {
  _FakeSessionProvider() : super(LiveKitService());

  @override
  Future<bool> reconnectWithMetadata({
    String? userId,
    Map<String, dynamic>? clientConfig,
  }) async {
    updateConnectionStateForTesting(SessionConnectionState.reconnecting);
    return true;
  }
}

Future<void> _pumpHost(
  WidgetTester tester, {
  required OverlayController overlay,
  required SessionProvider session,
  required WorkspaceController workspace,
}) async {
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<OverlayController>.value(value: overlay),
        ChangeNotifierProvider<SessionProvider>.value(value: session),
        ChangeNotifierProvider<WorkspaceController>.value(value: workspace),
        ChangeNotifierProvider<AgentActivityController>(
          create: (_) => AgentActivityController(),
        ),
      ],
      child: MaterialApp(
        home: GlobalOverlayHost(
          child: const Scaffold(
            body: SizedBox.expand(
              child: ColoredBox(
                color: Colors.black,
                child: Center(
                  child: Text('child'),
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('GlobalOverlayHost', () {
    testWidgets('renders no overlay widgets when controller is idle', (tester) async {
      final overlay = OverlayController();
      final session = _FakeSessionProvider();
      final workspace = WorkspaceController();
      addTearDown(overlay.dispose);
      addTearDown(session.dispose);
      addTearDown(workspace.dispose);

      await _pumpHost(
        tester,
        overlay: overlay,
        session: session,
        workspace: workspace,
      );

      expect(find.byType(SystemActionBubble), findsNothing);
      expect(find.byType(MediaResultBubble), findsNothing);
      expect(find.byType(ConfirmationCard), findsNothing);
      expect(find.textContaining('Disconnected from Maya session'), findsNothing);
      expect(find.byKey(const Key('global_overlay_compact_workbench_sheet')), findsNothing);
    });

    testWidgets('renders system and confirmation overlays from controller state', (tester) async {
      final overlay = OverlayController();
      final session = _FakeSessionProvider();
      final workspace = WorkspaceController();
      addTearDown(overlay.dispose);
      addTearDown(session.dispose);
      addTearDown(workspace.dispose);

      overlay.showSystemActionToast(
        const SystemActionToastData(
          actionType: 'SYSTEM',
          message: 'Saved screenshot.',
          detail: '/tmp/screen.png',
          success: true,
          rollbackAvailable: false,
          traceId: 'trace-1',
        ),
      );
      overlay.showConfirmationPrompt(
        const ConfirmationPromptData(
          actionType: 'Delete',
          description: 'Delete the current file?',
          destructive: true,
          timeoutSeconds: 120,
          traceId: 'trace-confirm',
        ),
      );

      await _pumpHost(
        tester,
        overlay: overlay,
        session: session,
        workspace: workspace,
      );

      expect(find.byType(SystemActionBubble), findsOneWidget);
      expect(find.byType(ConfirmationCard), findsOneWidget);
      expect(find.textContaining('Delete the current file'), findsOneWidget);
    });

    testWidgets('renders media banner from controller state', (tester) async {
      final overlay = OverlayController();
      final session = _FakeSessionProvider();
      final workspace = WorkspaceController();
      addTearDown(overlay.dispose);
      addTearDown(session.dispose);
      addTearDown(workspace.dispose);

      overlay.showMediaResultToast(
        const MediaResultToastData(
          trackName: 'Numb',
          artist: 'Linkin Park',
          provider: 'spotify',
          statusText: 'Playing on Spotify',
          albumArtUrl: '',
          eventId: 'evt-media-host',
        ),
      );

      await _pumpHost(
        tester,
        overlay: overlay,
        session: session,
        workspace: workspace,
      );

      expect(find.byType(MediaResultBubble), findsOneWidget);
      expect(find.textContaining('Playing on Spotify'), findsOneWidget);

      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();
      expect(overlay.mediaResultToast, isNull);
    });

    testWidgets('renders compact workbench sheet from OverlayController', (tester) async {
      final overlay = OverlayController();
      final session = _FakeSessionProvider();
      final workspace = WorkspaceController()
        ..setLayoutMode(WorkspaceLayoutMode.compact)
        ..setWorkbenchVisible(false);
      addTearDown(overlay.dispose);
      addTearDown(session.dispose);
      addTearDown(workspace.dispose);

      overlay.setCompactWorkbenchSheetOpen(true);

      await _pumpHost(
        tester,
        overlay: overlay,
        session: session,
        workspace: workspace,
      );

      expect(find.byKey(const Key('global_overlay_compact_workbench_sheet')), findsOneWidget);
    });

    testWidgets('does not render workbench overlay for medium/wide layouts', (tester) async {
      final overlay = OverlayController();
      final session = _FakeSessionProvider();
      final workspace = WorkspaceController()..setLayoutMode(WorkspaceLayoutMode.wide);
      addTearDown(overlay.dispose);
      addTearDown(session.dispose);
      addTearDown(workspace.dispose);

      overlay.setCompactWorkbenchSheetOpen(true);

      await _pumpHost(
        tester,
        overlay: overlay,
        session: session,
        workspace: workspace,
      );

      expect(find.byKey(const Key('global_overlay_workbench_panel')), findsNothing);
    });

    testWidgets('renders reconnect prompt when reconnect visibility is enabled', (tester) async {
      final overlay = OverlayController();
      final session = _FakeSessionProvider();
      final workspace = WorkspaceController();
      addTearDown(overlay.dispose);
      addTearDown(session.dispose);
      addTearDown(workspace.dispose);

      overlay.setReconnectPromptVisible(true);

      await _pumpHost(
        tester,
        overlay: overlay,
        session: session,
        workspace: workspace,
      );

      expect(find.textContaining('Disconnected from Maya session'), findsOneWidget);
      expect(find.text('Reconnect'), findsOneWidget);
    });
  });
}
