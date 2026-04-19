import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/services/ide_files_service.dart';
import 'package:voice_assistant/widgets/features/workbench/ide_tab.dart';

import '../../../helpers/fake_ide_services.dart';

void main() {
  group('IDE Files Pane', () {
    late FakeIdeFilesService filesService;
    late FakeIdeTerminalService terminalService;

    Future<void> pumpPane(WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: IDETab(
              filesService: filesService,
              terminalService: terminalService,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    setUp(() {
      filesService = FakeIdeFilesService();
      terminalService = FakeIdeTerminalService();
    });

    testWidgets('directory click updates breadcrumb and list', (tester) async {
      await pumpPane(tester);

      await tester.tap(find.byKey(const Key('ide-entry-src')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-files-breadcrumb-src')), findsOneWidget);
      expect(find.byKey(const Key('ide-entry-src/main.dart')), findsOneWidget);
    });

    testWidgets('file click loads content into editor', (tester) async {
      await pumpPane(tester);

      await tester.tap(find.byKey(const Key('ide-entry-README.md')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-files-editor')), findsOneWidget);
      expect(find.textContaining('# Maya-One'), findsOneWidget);
    });

    testWidgets('editing sets dirty and save clears dirty', (tester) async {
      await pumpPane(tester);

      await tester.tap(find.byKey(const Key('ide-entry-README.md')));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(const Key('ide-files-editor')), '# Changed\n');
      await tester.pumpAndSettle();
      expect(find.text('Unsaved'), findsOneWidget);

      await tester.tap(find.byKey(const Key('ide-files-save')));
      await tester.pumpAndSettle();

      expect(find.text('Saved'), findsOneWidget);
      expect(filesService.readCachedFile('README.md'), '# Changed\n');
    });

    testWidgets('unsaved navigation prompts Save/Discard/Cancel', (tester) async {
      await pumpPane(tester);

      await tester.tap(find.byKey(const Key('ide-entry-README.md')));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(const Key('ide-files-editor')), '# Unsaved\n');
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('ide-entry-src')));
      await tester.pumpAndSettle();

      final dialog = find.byType(AlertDialog);
      expect(dialog, findsOneWidget);
      expect(find.descendant(of: dialog, matching: find.text('Unsaved changes')), findsOneWidget);
      expect(find.descendant(of: dialog, matching: find.text('Save')), findsOneWidget);
      expect(find.descendant(of: dialog, matching: find.text('Discard')), findsOneWidget);
      expect(find.descendant(of: dialog, matching: find.text('Cancel')), findsOneWidget);

      await tester.tap(find.descendant(of: dialog, matching: find.text('Cancel')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-files-breadcrumb-src')), findsNothing);
      expect(find.byKey(const Key('ide-files-editor')), findsOneWidget);
      expect(find.text('Unsaved'), findsOneWidget);
    });

    testWidgets('403 write denial renders policy banner', (tester) async {
      filesService.writeFailure = IdeFilesError(
        statusCode: 403,
        message: 'action not permitted',
        risk: 'high',
        policyReason: 'write blocked by policy',
      );

      await pumpPane(tester);

      await tester.tap(find.byKey(const Key('ide-entry-README.md')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('ide-files-editor')), '# Denied\n');
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('ide-files-save')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-files-error-banner')), findsOneWidget);
      expect(find.textContaining('Blocked by policy'), findsOneWidget);
      expect(find.textContaining('write blocked by policy'), findsOneWidget);
    });

    testWidgets('409 write denial renders approval banner', (tester) async {
      filesService.writeFailure = IdeFilesError(
        statusCode: 409,
        message: 'action not permitted',
        risk: 'high',
        policyReason: 'approval required for write',
        requiresApproval: true,
      );

      await pumpPane(tester);

      await tester.tap(find.byKey(const Key('ide-entry-README.md')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('ide-files-editor')), '# Needs approval\n');
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('ide-files-save')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('ide-files-error-banner')), findsOneWidget);
      expect(find.textContaining('Approval required'), findsOneWidget);
      expect(find.textContaining('approval required for write'), findsOneWidget);
    });
  });
}
