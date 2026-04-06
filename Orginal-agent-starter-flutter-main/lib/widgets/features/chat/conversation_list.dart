import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:chat_bubbles/chat_bubbles.dart';
import 'dart:async';

import '../../../state/providers/chat_provider.dart';
import '../../../ui/theme/app_theme.dart';
import 'agent_thinking_bubble.dart';
import 'assistant_message_panel.dart';
import 'jump_to_latest_chip.dart';
import 'research_result_bubble.dart';
import 'media_result_bubble.dart';
import 'system_action_bubble.dart';

class ConversationList extends StatefulWidget {
  const ConversationList({super.key});

  @override
  State<ConversationList> createState() => _ConversationListState();
}

class _ConversationListState extends State<ConversationList> with SingleTickerProviderStateMixin {
  final ScrollController _scrollController = ScrollController();
  int _previousRenderItemCount = 0;
  bool _autoScrollEnabled = true;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  bool _isNearBottom({double threshold = 120}) {
    if (!_scrollController.hasClients) return true;
    final position = _scrollController.position;
    return (position.maxScrollExtent - position.pixels) <= threshold;
  }

  void _onScroll() {
    final nextValue = _isNearBottom();
    if (_autoScrollEnabled != nextValue && mounted) {
      setState(() {
        _autoScrollEnabled = nextValue;
      });
    }
  }

  void _scrollToNewest() {
    if (_scrollController.hasClients) {
      unawaited(_scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      ));
    }
  }

  bool _isLongAssistantMessage(String content) {
    return content.length >= 280 ||
        content.contains('|') ||
        content.contains('```') ||
        content.contains('\n- ') ||
        content.contains('\n* ');
  }

  Widget _buildMessageBubble(ChatMessage msg) {
    if (msg.isUser) {
      return BubbleSpecialThree(
        text: msg.content,
        color: ZoyaTheme.accent.withValues(alpha: 0.2),
        tail: true,
        isSender: true,
        textStyle: ZoyaTheme.fontBody.copyWith(
          color: Colors.white,
          fontSize: 15,
          height: 1.4,
        ),
      );
    }

    if (msg.eventType == 'research_result') {
      return ResearchResultBubble(
        summary: msg.content,
        sources: msg.sources,
        traceId: (msg.payload['traceId'] ?? msg.turnId ?? msg.id).toString(),
      );
    }

    if (msg.eventType == 'media_result') {
      return MediaResultBubble(
        trackName: (msg.payload['trackName'] ?? '').toString(),
        provider: (msg.payload['provider'] ?? '').toString(),
        statusText: msg.content,
        artist: (msg.payload['artist'] ?? '').toString(),
        albumArtUrl: (msg.payload['albumArtUrl'] ?? '').toString(),
        autoDismiss: false,
      );
    }

    if (msg.eventType == 'system_result') {
      return SystemActionBubble(
        actionType: (msg.payload['actionType'] ?? 'SYSTEM').toString(),
        message: msg.content,
        detail: (msg.payload['detail'] ?? '').toString(),
        success: msg.payload['success'] == true,
        rollbackAvailable: msg.payload['rollbackAvailable'] == true,
        autoDismiss: false,
      );
    }

    if (msg.eventType == 'confirmation_required') {
      final actionType = (msg.payload['actionType'] ?? 'Action').toString();
      final destructive = msg.payload['destructive'] == true;
      return Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
        decoration: BoxDecoration(
          color: (destructive ? ZoyaTheme.danger : ZoyaTheme.accent).withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: (destructive ? ZoyaTheme.danger : ZoyaTheme.accent).withValues(alpha: 0.35),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  destructive ? Icons.warning_amber_rounded : Icons.help_outline_rounded,
                  size: 15,
                  color: destructive ? ZoyaTheme.danger : ZoyaTheme.accent,
                ),
                const SizedBox(width: 6),
                Text(
                  actionType,
                  style: ZoyaTheme.fontBody.copyWith(
                    color: destructive ? ZoyaTheme.danger : ZoyaTheme.accent,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              msg.content,
              style: ZoyaTheme.fontBody.copyWith(
                color: ZoyaTheme.textMuted,
                fontSize: 13,
              ),
            ),
          ],
        ),
      );
    }

    final isLong = _isLongAssistantMessage(msg.content) || msg.sources.isNotEmpty;
    if (isLong) {
      return AssistantMessagePanel(
        content: msg.content,
        isLive: msg.isLive,
        canExpand: true,
        sources: msg.sources,
      );
    }

    return BubbleSpecialThree(
      text: msg.content,
      color: const Color(0xFF1E1E2E),
      tail: true,
      isSender: false,
      textStyle: ZoyaTheme.fontBody.copyWith(
        color: Colors.white,
        fontSize: 15,
        height: 1.4,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final chat = context.watch<ChatProvider>();
    final showThinkingBubble = chat.isAgentThinking && 
        chat.agentState != AgentState.listening && 
        !chat.hasAnyLiveAssistantMessage;
    final messages = chat.messages;
    
    final renderItemCount = messages.length + (showThinkingBubble ? 1 : 0);

    if (renderItemCount > _previousRenderItemCount) {
      if (_autoScrollEnabled || _isNearBottom()) {
        WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToNewest());
      }
      _previousRenderItemCount = renderItemCount;
    } else if (renderItemCount < _previousRenderItemCount) {
      _previousRenderItemCount = renderItemCount;
    }

    return Expanded(
      child: Stack(
        children: [
          Positioned.fill(
            child: SelectionArea(
              child: ListView.builder(
                key: const Key('conversation_list'),
                reverse: false,
                controller: _scrollController,
                padding: const EdgeInsets.fromLTRB(24, 100, 24, 140),
                itemCount: renderItemCount,
                itemBuilder: (context, index) {
                  if (showThinkingBubble && index == renderItemCount - 1) {
                    return _AnimatedConversationMessage(
                      key: const ValueKey('thinking_bubble'),
                      child: AgentThinkingBubble(
                        state: chat.agentState,
                        tool: chat.currentTool,
                      ),
                    );
                  }

                  final msg = messages[index];
                  return _AnimatedConversationMessage(
                    key: ValueKey(msg.id),
                    child: Align(
                      alignment: msg.isUser ? Alignment.centerRight : Alignment.centerLeft,
                      child: Container(
                        constraints: const BoxConstraints(maxWidth: 600),
                        margin: const EdgeInsets.only(bottom: 16),
                        child: _buildMessageBubble(msg),
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
          if (!_autoScrollEnabled && messages.isNotEmpty)
            Positioned(
              bottom: 8,
              left: 0,
              right: 0,
              child: Center(
                child: JumpToLatestChip(onTap: _scrollToNewest),
              ),
            ),
        ],
      ),
    );
  }
}

class _AnimatedConversationMessage extends StatefulWidget {
  final Widget child;

  const _AnimatedConversationMessage({
    super.key,
    required this.child,
  });

  @override
  State<_AnimatedConversationMessage> createState() => _AnimatedConversationMessageState();
}

class _AnimatedConversationMessageState extends State<_AnimatedConversationMessage>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 300));
    _scale = CurvedAnimation(parent: _controller, curve: Curves.easeOutBack);
    unawaited(_controller.forward());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: _scale,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: widget.child,
      ),
    );
  }
}
