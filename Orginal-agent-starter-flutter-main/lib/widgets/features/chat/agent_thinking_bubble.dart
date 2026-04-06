import 'package:flutter/material.dart';
import 'dart:math' as math;
import '../../../ui/theme/app_theme.dart';
import '../../../state/providers/chat_provider.dart';

class AgentThinkingBubble extends StatefulWidget {
  final AgentState state;
  final String? tool;

  const AgentThinkingBubble({
    super.key,
    required this.state,
    this.tool,
  });

  @override
  State<AgentThinkingBubble> createState() => _AgentThinkingBubbleState();
}

class _AgentThinkingBubbleState extends State<AgentThinkingBubble> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String _getLabel() {
    switch (widget.state) {
      case AgentState.thinking:
        return 'Thinking...';
      case AgentState.callingTools:
        return 'Calling tool: ${widget.tool ?? "unknown"}';
      case AgentState.searchingWeb:
        return 'Searching the web...';
      case AgentState.writingResponse:
        return 'Writing response...';
      case AgentState.listening:
        return 'Listening...';
      default:
        return 'Processing...';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        margin: const EdgeInsets.fromLTRB(16, 4, 60, 16),
        decoration: BoxDecoration(
          color: const Color(0xFF1E1E2E).withValues(alpha: 0.8),
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(20),
            topRight: Radius.circular(20),
            bottomRight: Radius.circular(20),
            bottomLeft: Radius.circular(0),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildAnimatedIcon(),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                _getLabel(),
                style: ZoyaTheme.fontBody.copyWith(
                  color: Colors.white70,
                  fontSize: 14,
                  height: 1.4,
                  fontStyle: FontStyle.italic,
                  letterSpacing: 0.2,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAnimatedIcon() {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Transform.rotate(
          angle: _controller.value * 2 * math.pi,
          child: Icon(
            widget.state == AgentState.callingTools ? Icons.settings : Icons.blur_on,
            size: 18,
            color: ZoyaTheme.accent.withValues(alpha: 0.8),
          ),
        );
      },
    );
  }
}
