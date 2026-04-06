import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'dart:async';

import '../../../state/controllers/composer_controller.dart';
import '../../../state/providers/chat_provider.dart';
import '../../../state/providers/conversation_history_provider.dart';
import '../../../state/providers/session_provider.dart';
import '../../../../core/services/file_service.dart';
import 'message_bar.dart' as widgets;

class ComposerBar extends StatefulWidget {
  const ComposerBar({super.key});

  @override
  State<ComposerBar> createState() => _ComposerBarState();
}

class _ComposerBarState extends State<ComposerBar> {
  final FileService _fileService = FileService();

  Future<void> _handleSend() async {
    if (!mounted) return;

    if (context.read<ConversationHistoryProvider>().isSwitchingConversation) {
      return;
    }

    final composer = context.read<ComposerController>();
    final text = composer.textController.text.trim();
    if (text.isEmpty && composer.attachments.isEmpty) return;

    composer
      ..setSending(true)
      ..setUploading(true);

    try {
      final List<String> attachmentUrls = [];

      // Upload files first if any
      if (composer.attachments.isNotEmpty) {
        for (final file in composer.attachments) {
          final url = await _fileService.uploadFile(file);
          if (url != null) {
            attachmentUrls.add(url);
          }
        }
      }

      String messageContent = text;
      if (attachmentUrls.isNotEmpty) {
        messageContent += "\n\nAttachments:\n${attachmentUrls.join('\n')}";
      }

      debugPrint('Sending message: $messageContent');

      // Add to local chat immediately for UI responsiveness
      if (!mounted) return;
      context.read<ChatProvider>().addMessage(ChatMessage(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            content: messageContent,
            timestamp: DateTime.now(),
            isUser: true,
            isAgent: false,
            attachmentUrls: attachmentUrls,
          ));
      composer
        ..clearDraft()
        ..clearAttachments();

      // Send to LiveKit session (for agent to hear)
      if (!mounted) return;
      await context.read<SessionProvider>().sendUserMessage(messageContent);
      debugPrint('✅ Message sent to backend confirmed');
    } catch (e) {
      debugPrint('❌ Failed to send message: $e');
    } finally {
      if (mounted) {
        composer
          ..setUploading(false)
          ..setSending(false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final composer = context.watch<ComposerController>();
    final history = context.watch<ConversationHistoryProvider>();

    final bool isSendEnabled = !history.isSwitchingConversation && !composer.isUploading && !composer.isSending;

    return Align(
      alignment: Alignment.bottomCenter,
      child: Padding(
        padding: const EdgeInsets.only(left: 20, right: 20, bottom: 20),
        child: Container(
          key: const Key('conversation_composer_bar'),
          constraints: const BoxConstraints(maxWidth: 800),
          decoration: BoxDecoration(
            color: const Color(0xFF222222).withValues(alpha: 0.9),
            borderRadius: BorderRadius.circular(30),
            border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.5),
                blurRadius: 20,
                offset: const Offset(0, 5),
              ),
            ],
          ),
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: widgets.MessageBar(
            controller: composer.textController,
            focusNode: composer.focusNode,
            onSendTap: _handleSend,
            isSendEnabled: isSendEnabled,
            attachments: composer.attachments,
            onAttachmentAdded: (file) => context.read<ComposerController>().addAttachment(file),
            onAttachmentRemoved: (file) => context.read<ComposerController>().removeAttachment(file),
            isUploading: composer.isUploading,
          ),
        ),
      ),
    );
  }
}
