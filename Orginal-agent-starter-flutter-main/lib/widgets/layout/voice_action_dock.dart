import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/controllers/agent_activity_controller.dart';
import '../../state/controllers/composer_controller.dart';
import '../../state/controllers/overlay_controller.dart';
import '../../state/controllers/workspace_controller.dart';
import '../../state/models/workspace_models.dart';
import '../../ui/theme/app_theme.dart';

class VoiceActionDock extends StatelessWidget {
  const VoiceActionDock({super.key});

  @override
  Widget build(BuildContext context) {
    final activity = context.watch<AgentActivityController>();
    final composer = context.watch<ComposerController>();
    final workspace = context.watch<WorkspaceController>();
    final overlay = context.watch<OverlayController>();

    bool isVisible = false;
    switch (workspace.layoutMode) {
      case WorkspaceLayoutMode.compact:
        isVisible = true;
        break;
      case WorkspaceLayoutMode.medium:
        isVisible = !overlay.compactWorkbenchSheetOpen;
        break;
      case WorkspaceLayoutMode.wide:
        isVisible = false;
        break;
    }

    if (!isVisible) {
      return const SizedBox.shrink();
    }

    final isInterruptEnabled =
        activity.voiceUiState == VoiceUiState.speaking || activity.voiceUiState == VoiceUiState.greeting;
    
    // Disable reveal button if already revealed
    final isRevealEnabled = !composer.composerRevealed;

    return Container(
      key: const Key('voice_action_dock'),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: ZoyaTheme.sidebarBg.withValues(alpha: 0.86),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: ZoyaTheme.glassBorder.withValues(alpha: 0.5)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _DockButton(
            key: const Key('voice_action_primary_toggle'),
            icon: composer.voiceMode == VoiceInputMode.pushToTalk ? Icons.mic_none : Icons.hearing,
            label: composer.voiceMode == VoiceInputMode.pushToTalk ? 'Push to talk' : 'Continuous',
            emphasized: true,
            enabled: true,
            onTap: () => context.read<ComposerController>().toggleVoiceMode(),
          ),
          const SizedBox(width: 8),
          _DockButton(
            key: const Key('voice_action_interrupt'),
            icon: Icons.stop_circle_outlined,
            label: 'Interrupt',
            color: Colors.orangeAccent,
            enabled: isInterruptEnabled,
            onTap: () {
              if (isInterruptEnabled) {
                context.read<ComposerController>().interrupt();
              }
            },
          ),
          const SizedBox(width: 8),
          _DockButton(
            key: const Key('voice_action_reveal_composer'),
            icon: Icons.keyboard_outlined,
            label: 'Compose',
            enabled: isRevealEnabled,
            onTap: () {
              if (isRevealEnabled) {
                context.read<ComposerController>().revealComposer(requestFocus: true);
              }
            },
          ),
        ],
      ),
    );
  }
}

class _DockButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool emphasized;
  final bool enabled;
  final Color? color;

  const _DockButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.emphasized = false,
    this.enabled = true,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final accentColor = color ?? (emphasized ? ZoyaTheme.accent : ZoyaTheme.textMain);
    final effectiveColor = enabled ? accentColor : accentColor.withValues(alpha: 0.3);
    
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: enabled ? onTap : null,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: emphasized ? effectiveColor.withValues(alpha: 0.16) : Colors.white.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: effectiveColor.withValues(alpha: emphasized ? 0.28 : 0.18),
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 18, color: effectiveColor),
              const SizedBox(width: 8),
              Text(
                label,
                style: ZoyaTheme.fontBody.copyWith(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: enabled ? Colors.white : Colors.white.withValues(alpha: 0.3),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
