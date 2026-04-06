import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../state/providers/conversation_history_provider.dart';
import '../../../ui/theme/app_theme.dart';

class ConversationSwitchBlocker extends StatelessWidget {
  const ConversationSwitchBlocker({super.key});

  @override
  Widget build(BuildContext context) {
    return Selector<ConversationHistoryProvider, _BlockerState>(
      selector: (context, history) => _BlockerState(
        isSwitching: history.isSwitchingConversation,
        status: history.switchStatus,
      ),
      builder: (context, state, child) {
        if (!state.isSwitching) return const SizedBox.shrink();

        return IgnorePointer(
          child: Container(
            color: Colors.black.withValues(alpha: 0.18),
            alignment: Alignment.center,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF111827).withValues(alpha: 0.94),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: ZoyaTheme.glassBorder),
              ),
              child: Text(
                state.status.isEmpty ? 'Switching conversation…' : state.status,
                style: ZoyaTheme.fontBody.copyWith(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _BlockerState {
  final bool isSwitching;
  final String status;
  _BlockerState({required this.isSwitching, required this.status});

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is _BlockerState &&
          runtimeType == other.runtimeType &&
          isSwitching == other.isSwitching &&
          status == other.status;

  @override
  int get hashCode => Object.hash(isSwitching, status);
}
