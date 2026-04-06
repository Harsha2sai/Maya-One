import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/state/controllers/overlay_controller.dart';
import 'package:voice_assistant/state/models/overlay_models.dart';

void main() {
  group('OverlayController Tests', () {
    late OverlayController controller;

    setUp(() {
      controller = OverlayController();
    });

    test('Initial state should be empty/hidden for all overlays', () {
      expect(controller.systemActionToast, isNull);
      expect(controller.mediaResultToast, isNull);
      expect(controller.pendingConfirmation, isNull);
      expect(controller.compactWorkbenchSheetOpen, false);
      expect(controller.isReconnectPromptVisible, false);
    });

    test('showSystemActionToast triggers listeners and sets state', () {
      int notifyCount = 0;
      controller.addListener(() {
        notifyCount++;
      });

      final action = SystemActionToastData(
        message: 'Test Label',
        actionType: 'test',
        detail: 'detail',
        success: true,
        rollbackAvailable: false,
        traceId: '123',
      );
      controller.showSystemActionToast(action);

      expect(controller.systemActionToast, action);
      expect(notifyCount, 1);

      controller.clearSystemActionToast();
      expect(controller.systemActionToast, isNull);
      expect(notifyCount, 2);
    });

    test('showConfirmationPrompt sets and clearConfirmationPrompt clears state', () {
      const confirmation = ConfirmationPromptData(
        actionType: 'Delete file',
        description: 'Delete README.md?',
        destructive: true,
        timeoutSeconds: 60,
        traceId: 'trace-confirm',
      );

      controller.showConfirmationPrompt(confirmation);
      expect(controller.pendingConfirmation, confirmation);

      controller.clearConfirmationPrompt();
      expect(controller.pendingConfirmation, isNull);
    });

    test('showMediaResultToast sets field and auto-clears after timeout', () async {
      const media = MediaResultToastData(
        trackName: 'Song',
        provider: 'spotify',
        statusText: 'Playing now',
        artist: 'Artist',
        albumArtUrl: '',
        eventId: 'evt-media-1',
      );

      controller.showMediaResultToast(media);
      expect(controller.mediaResultToast, media);

      await Future<void>.delayed(const Duration(milliseconds: 3200));
      expect(controller.mediaResultToast, isNull);
    });

    test('setCompactWorkbenchSheetOpen toggles state', () {
      controller.setCompactWorkbenchSheetOpen(true);
      expect(controller.compactWorkbenchSheetOpen, true);

      controller.setCompactWorkbenchSheetOpen(false);
      expect(controller.compactWorkbenchSheetOpen, false);
    });

    test('setReconnectPromptVisible toggles state', () {
      controller.setReconnectPromptVisible(true);
      expect(controller.isReconnectPromptVisible, true);

      controller.setReconnectPromptVisible(false);
      expect(controller.isReconnectPromptVisible, false);
    });

    test('reset clears all overlay state', () {
      controller.showSystemActionToast(
        const SystemActionToastData(
          message: 'Saved',
          actionType: 'system',
          detail: 'done',
          success: true,
          rollbackAvailable: false,
          traceId: 'trace-reset',
        ),
      );
      controller.showMediaResultToast(
        const MediaResultToastData(
          trackName: 'Song',
          provider: 'spotify',
          statusText: 'Playing',
          artist: 'Artist',
          albumArtUrl: '',
          eventId: 'evt-media-2',
        ),
      );
      controller.showConfirmationPrompt(
        const ConfirmationPromptData(
          actionType: 'Confirm',
          description: 'Proceed?',
          destructive: false,
          timeoutSeconds: 10,
          traceId: 'trace-reset-confirm',
        ),
      );
      controller.setReconnectPromptVisible(true);
      controller.setCompactWorkbenchSheetOpen(true);

      controller.reset();

      expect(controller.systemActionToast, isNull);
      expect(controller.mediaResultToast, isNull);
      expect(controller.pendingConfirmation, isNull);
      expect(controller.isReconnectPromptVisible, false);
      expect(controller.compactWorkbenchSheetOpen, false);
    });
  });
}
