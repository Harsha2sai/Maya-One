import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/state/controllers/composer_controller.dart';

void main() {
  group('ComposerController', () {
    test('tracks draft text and upload state', () {
      final controller = ComposerController();

      controller.setDraftText('hello maya');
      controller.setUploading(true);
      controller.setSending(true);

      expect(controller.draftText, 'hello maya');
      expect(controller.isUploading, isTrue);
      expect(controller.isSending, isTrue);
    });

    test('adds and removes attachments by path', () {
      final controller = ComposerController();
      final fileA = File('/tmp/a.txt');
      final fileB = File('/tmp/b.txt');

      controller.addAttachment(fileA);
      controller.addAttachment(fileA);
      controller.addAttachment(fileB);

      expect(controller.attachments.map((file) => file.path), <String>['/tmp/a.txt', '/tmp/b.txt']);

      controller.removeAttachment(fileA);
      expect(controller.attachments.map((file) => file.path), <String>['/tmp/b.txt']);
    });

    test('switches voice mode and clears draft/attachments', () {
      final controller = ComposerController();
      controller.setDraftText('draft');
      controller.addAttachment(File('/tmp/c.txt'));
      controller.setVoiceMode(VoiceInputMode.continuous);

      controller
        ..clearDraft()
        ..clearAttachments();

      expect(controller.voiceMode, VoiceInputMode.continuous);
      expect(controller.draftText, isEmpty);
      expect(controller.attachments, isEmpty);
    });
  });
}
