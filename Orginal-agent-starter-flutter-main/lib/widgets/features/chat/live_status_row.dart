import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../state/providers/chat_provider.dart';
import '../../../state/providers/conversation_history_provider.dart';
import '../../../ui/theme/app_theme.dart';

class LiveStatusRow extends StatelessWidget {
  const LiveStatusRow({super.key});

  @override
  Widget build(BuildContext context) {
    final history = context.watch<ConversationHistoryProvider>();
    final chat = context.watch<ChatProvider>();

    String text = '';
    
    if (history.isSwitchingConversation) {
      text = history.switchStatus.isEmpty ? 'Switching conversation…' : history.switchStatus;
    } else if (chat.currentTool != null && chat.currentTool!.trim().isNotEmpty) {
      text = 'Maya is using ${chat.currentTool!}';
    } else if (chat.isAgentThinking && !chat.hasAnyLiveAssistantMessage) {
      text = 'Maya is thinking…';
    }

    if (text.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      key: const Key('conversation_live_status_row'),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              color: ZoyaTheme.accent,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              text,
              style: ZoyaTheme.fontBody.copyWith(
                fontSize: 12,
                color: Colors.white,
                fontWeight: FontWeight.w600,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
