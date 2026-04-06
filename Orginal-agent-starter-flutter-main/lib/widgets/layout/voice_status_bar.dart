import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/controllers/agent_activity_controller.dart';
import '../../ui/theme/app_theme.dart';

class VoiceStatusBar extends StatelessWidget {
  const VoiceStatusBar({super.key});

  @override
  Widget build(BuildContext context) {
    final activity = context.watch<AgentActivityController>();
    final stateStyle = _stateStyleFor(activity.voiceUiState);
    final detailText = _detailText(
      activity.voiceUiState,
      activeToolName: activity.activeToolName,
      activeTaskId: activity.activeTaskId,
    );

    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
        child: Container(
          key: const Key('voice_status_bar'),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: ZoyaTheme.sidebarBg.withValues(alpha: 0.82),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: stateStyle.color.withValues(alpha: 0.22)),
            boxShadow: [
              BoxShadow(
                color: stateStyle.color.withValues(alpha: 0.08),
                blurRadius: 20,
                spreadRadius: 0,
              ),
            ],
          ),
          child: Row(
            children: [
              Container(
                key: const Key('voice_status_state_badge'),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: stateStyle.color.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: stateStyle.color,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      stateStyle.label,
                      key: const Key('voice_status_state_label'),
                      style: ZoyaTheme.fontBody.copyWith(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  detailText,
                  key: const Key('voice_status_detail_text'),
                  style: ZoyaTheme.fontBody.copyWith(
                    fontSize: 12,
                    color: ZoyaTheme.textMuted,
                    fontWeight: FontWeight.w500,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _VoiceStateStyle {
  final String label;
  final Color color;

  const _VoiceStateStyle({
    required this.label,
    required this.color,
  });
}

_VoiceStateStyle _stateStyleFor(VoiceUiState state) {
  switch (state) {
    case VoiceUiState.idle:
      return const _VoiceStateStyle(label: 'Idle', color: ZoyaTheme.textMuted);
    case VoiceUiState.listening:
      return const _VoiceStateStyle(label: 'Listening', color: ZoyaTheme.accent);
    case VoiceUiState.thinking:
      return const _VoiceStateStyle(label: 'Thinking...', color: ZoyaTheme.secondaryAccent);
    case VoiceUiState.toolRunning:
      return const _VoiceStateStyle(label: 'Working...', color: ZoyaTheme.success);
    case VoiceUiState.speaking:
      return const _VoiceStateStyle(label: 'Speaking', color: ZoyaTheme.accent);
    case VoiceUiState.greeting:
      return const _VoiceStateStyle(label: 'Greeting', color: ZoyaTheme.accent); // Needs to be same visual as speaking, but label is Greeting
    case VoiceUiState.interrupted:
      return const _VoiceStateStyle(label: 'Interrupted', color: ZoyaTheme.textMuted);
    case VoiceUiState.bootstrapping:
      return const _VoiceStateStyle(label: 'Resuming...', color: Colors.amber);
    case VoiceUiState.offline:
      return const _VoiceStateStyle(label: 'Offline', color: ZoyaTheme.danger);
    case VoiceUiState.reconnecting:
      return const _VoiceStateStyle(label: 'Reconnecting...', color: Colors.orange);
  }
}

String _detailText(
  VoiceUiState state, {
  String? activeToolName,
  String? activeTaskId,
}) {
  final toolText = (activeToolName ?? '').trim();
  final taskText = (activeTaskId ?? '').trim();

  if (state == VoiceUiState.toolRunning && toolText.isNotEmpty) {
    return toolText; 
  }

  if (toolText.isNotEmpty && taskText.isNotEmpty) {
    return '${_baseDetailText(state)} • $toolText • $taskText';
  }
  if (toolText.isNotEmpty) {
    return '${_baseDetailText(state)} • $toolText';
  }
  if (taskText.isNotEmpty) {
    return '${_baseDetailText(state)} • $taskText';
  }
  return _baseDetailText(state);
}

String _baseDetailText(VoiceUiState state) {
  switch (state) {
    case VoiceUiState.idle:
      return 'Ready for your next request';
    case VoiceUiState.listening:
      return 'Maya is listening for voice input';
    case VoiceUiState.thinking:
      return 'Maya is reasoning through the current request';
    case VoiceUiState.toolRunning:
      return 'Maya is executing a tool';
    case VoiceUiState.speaking:
      return 'Maya is speaking';
    case VoiceUiState.greeting:
      return 'Maya is greeting the session';
    case VoiceUiState.interrupted:
      return 'Voice response interrupted';
    case VoiceUiState.bootstrapping:
      return 'Switching conversation context';
    case VoiceUiState.offline:
      return 'Connection lost';
    case VoiceUiState.reconnecting:
      return 'Restoring the session';
  }
}
