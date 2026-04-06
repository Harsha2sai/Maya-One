import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import '../theme/app_theme.dart';
import '../../state/providers/session_provider.dart';
import '../../state/controllers/orb_controller.dart';
import '../../state/controllers/app_init_controller.dart';
import '../../state/controllers/workspace_controller.dart';
import '../../state/controllers/overlay_controller.dart';
import '../../state/models/workspace_models.dart';
import '../../widgets/features/visuals/cosmic_orb.dart';
import '../../widgets/features/visuals/classic_orb.dart';
import '../../widgets/layout/agent_orb_state_bridge.dart';
import '../../widgets/layout/workspace_scaffold.dart';
import '../../widgets/features/chat/chat_overlay.dart';
import '../../state/providers/settings_provider.dart';
import '../../widgets/features/workbench/workbench_pane.dart';


class AgentScreen extends StatefulWidget {
  final bool showSidebar;
  const AgentScreen({super.key, this.showSidebar = true});

  @override
  State<AgentScreen> createState() => _AgentScreenState();
}

class _AgentScreenState extends State<AgentScreen> {
  bool _chatOpen = false;

  @override
  void initState() {
    super.initState();
  }

  void _openWorkbenchTab(WorkbenchTab tab) {
    final workspace = Provider.of<WorkspaceController?>(context, listen: false);
    final overlay = Provider.of<OverlayController?>(context, listen: false);

    if (workspace == null || overlay == null) {
      debugPrint(
        'Workbench open ignored: missing workspace/overlay controller '
        '(workspace=${workspace != null}, overlay=${overlay != null})',
      );
      return;
    }

    final isCompact = workspace.layoutMode == WorkspaceLayoutMode.compact;
    final isSameTab = workspace.selectedWorkbenchTab == tab;

    if (isCompact) {
      if (overlay.compactWorkbenchSheetOpen && isSameTab) {
        overlay.setCompactWorkbenchSheetOpen(false);
        return;
      }
      workspace.selectWorkbenchTab(tab);
      overlay.setCompactWorkbenchSheetOpen(true);
    } else {
      if (workspace.workbenchVisible && isSameTab) {
        workspace.setWorkbenchVisible(false);
        return;
      }
      workspace
        ..setWorkbenchVisible(true)
        ..setWorkbenchCollapsed(false)
        ..selectWorkbenchTab(tab);
    }
  }

  @override
  Widget build(BuildContext context) {
    // We do NOT use OrbController for minimized state anymore, we use local state or pass it down
    // consistent with React's uni-directional flow for this view.
    final sessionProvider = context.watch<SessionProvider>();
    final settings = context.watch<SettingsProvider>();
    final interfaceTheme = settings.interfaceTheme;

    return AgentOrbStateBridge(
      child: WorkspaceScaffold(
        backgroundColor: Colors.transparent,
        background: interfaceTheme == 'classic'
            ? Container(
                decoration: const BoxDecoration(
                  gradient: RadialGradient(
                    center: Alignment.center,
                    radius: 1.0,
                    colors: [
                      Color(0xFF0F172A),
                      Color(0xFF020617),
                    ],
                  ),
                ),
              )
            : null,
        centerStage: _chatOpen
            ? (interfaceTheme == 'zoya'
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 48,
                          height: 1,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: [
                                Colors.transparent,
                                ZoyaTheme.accent.withValues(alpha: 0.3),
                                Colors.transparent,
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 20),
                        Text(
                          'NEURAL LINK ACTIVE',
                          style: ZoyaTheme.fontDisplay.copyWith(
                            fontSize: 10,
                            color: ZoyaTheme.accent.withValues(alpha: 0.4),
                            letterSpacing: 4,
                          ),
                        ),
                        const SizedBox(height: 20),
                        Container(
                          width: 48,
                          height: 1,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: [
                                Colors.transparent,
                                ZoyaTheme.accent.withValues(alpha: 0.3),
                                Colors.transparent,
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  )
                : const SizedBox.shrink())
            : Center(
                child: Consumer2<OrbController, AppInitController>(
                  builder: (ctx, orb, init, _) {
                    final canShowOrb = init.state.index >= InitState.orbAppear.index || sessionProvider.isConnected;
                    if (!canShowOrb) {
                      return const SizedBox.shrink();
                    }

                    final isMicEnabled = !orb.isMuted;

                    if (interfaceTheme == 'classic') {
                      return ClassicOrb(
                        state: orb.orbState,
                        isMicEnabled: isMicEnabled,
                        minimized: false,
                        size: 300,
                        onTap: () {
                          orb.handleTap();
                          setState(() => _chatOpen = !_chatOpen);
                        },
                      );
                    }

                    return CosmicOrb(
                      state: orb.orbState,
                      isMicEnabled: isMicEnabled,
                      minimized: false,
                      onTap: () {
                        orb.handleTap();
                        setState(() => _chatOpen = !_chatOpen);
                      },
                      onDoubleTap: () {
                        orb.toggleMute();
                        unawaited(sessionProvider.setMicrophoneEnabled(!orb.isMuted));
                      },
                      onLongPress: () => orb.resetPosition(),
                      onPanUpdate: (delta) => orb.updatePosition(delta),
                    );
                  },
                ),
              ),
        voiceStatusBar: null,
        floatingRightPanel: interfaceTheme == 'zoya'
            ? _FloatingWidgetsPanel(
                onOpenTab: _openWorkbenchTab,
              )
            : null,
        statusPanel: null,
        conversationOverlay: _chatOpen
            ? ChatOverlay(
                onClose: () => setState(() => _chatOpen = false),
              )
            : null,
        minimizedOrb: _chatOpen
            ? Consumer2<OrbController, AppInitController>(
                builder: (ctx, orb, init, _) {
                  final canShowOrb = init.state.index >= InitState.orbAppear.index || sessionProvider.isConnected;
                  if (!canShowOrb) {
                    return const SizedBox.shrink();
                  }

                  final isMicEnabled = !orb.isMuted;

                  if (interfaceTheme == 'classic') {
                    return ClassicOrb(
                      state: orb.orbState,
                      isMicEnabled: isMicEnabled,
                      minimized: true,
                      size: 120,
                      onTap: () {
                        orb.handleTap();
                        setState(() => _chatOpen = !_chatOpen);
                      },
                    );
                  }

                  return CosmicOrb(
                    state: orb.orbState,
                    isMicEnabled: isMicEnabled,
                    minimized: true,
                    size: 80,
                    onTap: () {
                      orb.handleTap();
                      setState(() => _chatOpen = !_chatOpen);
                    },
                    onDoubleTap: () {
                      orb.toggleMute();
                      unawaited(sessionProvider.setMicrophoneEnabled(!orb.isMuted));
                    },
                  );
                },
              )
            : null,

        leftControlBar: _ControlBar(
          onChatToggle: () => setState(() => _chatOpen = !_chatOpen),
          isChatOpen: _chatOpen,
        ),
        agentWorkbenchPane: Consumer<WorkspaceController>(
          builder: (context, workspace, child) {
            // Only render in medium/wide layout; compact uses the bottom sheet
            if (!workspace.workbenchVisible) return const SizedBox.shrink();
            if (workspace.layoutMode == WorkspaceLayoutMode.compact) return const SizedBox.shrink();

            // WorkbenchPane owns its own header + close button — no wrapper needed
            return ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Container(
                margin: const EdgeInsets.only(top: 16, right: 16, bottom: 16),
                constraints: const BoxConstraints(maxWidth: 360, minWidth: 320),
                decoration: BoxDecoration(
                  color: ZoyaTheme.mainBg.withValues(alpha: 0.92),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: ZoyaTheme.glassBorder),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.4),
                      blurRadius: 28,
                      offset: const Offset(0, 12),
                    ),
                  ],
                ),
                child: Material(
                  color: Colors.transparent,
                  child: WorkbenchPane(key: workbenchPaneKey),
                ),
              ),
            );
          },
        ),
        overlays: const [],
        voiceActionDock: null,
      ),
    );
  }
}

class _ControlBar extends StatefulWidget {
  final VoidCallback onChatToggle;
  final bool isChatOpen;

  const _ControlBar({required this.onChatToggle, required this.isChatOpen});

  @override
  State<_ControlBar> createState() => _ControlBarState();
}

class _ControlBarState extends State<_ControlBar> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    // Watch state to update UI when Mic/Chat toggles
    final session = context.watch<SessionProvider>();
    final orb = context.watch<OrbController>();
    final isMuted = orb.isMuted;

    // Define all controls with their active state
    controls() => [
          // Mic: Active if NOT muted
          (
            id: 'mic',
            isActive: !isMuted,
            widget: _ControlToggle(
              icon: isMuted ? FontAwesomeIcons.microphoneSlash : FontAwesomeIcons.microphone,
              isActive: !isMuted,
              activeColor: Colors.white,
              inactiveColor: const Color(0xFFEF4444),
              useVisualizer: !isMuted,
              onTap: () {
                orb.toggleMute();
                unawaited(session.setMicrophoneEnabled(!orb.isMuted));
              },
            ),
          ),
          // Camera: Inactive for now
          (
            id: 'camera',
            isActive: false,
            widget: _ControlToggle(
              icon: FontAwesomeIcons.videoSlash,
              isActive: false,
              onTap: () {},
            ),
          ),
          // Screen Share: Inactive for now
          (
            id: 'screen',
            isActive: false,
            widget: _ControlToggle(
              icon: FontAwesomeIcons.desktop,
              isActive: false,
              onTap: () {},
            ),
          ),
          // Disconnect: Always show on Hover, never essentially "active" state persistence
          (
            id: 'disconnect',
            isActive: false, // Don't show in collapsed mode
            widget: _DisconnectButton(onTap: () => session.disconnect(), vertical: true),
          ),
        ];

    // Filter controls: Show if Hovered OR Active
    // Exception: Disconnect only shows on Hover (to avoid accidental clicks and visual clutter)
    final visibleControls = controls().where((c) {
      if (_isHovered) return true; // Show all on hover
      if (c.id == 'disconnect') return false; // Hide disconnect if not hovered
      return c.isActive; // Show active ones (Mic On, Chat Open)
    }).toList();

    final backgroundColor = const Color(0xFF0B2727).withValues(alpha: 0.95);
    final borderColor = const Color(0xFF1A3D3D).withValues(alpha: 0.8);

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(36),
        child: BackdropFilter(
          filter: ui.ImageFilter.blur(sigmaX: 8, sigmaY: 8),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOut,
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: backgroundColor,
              borderRadius: BorderRadius.circular(36),
              border: Border.all(color: borderColor),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.3),
                  blurRadius: 16,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Trigger / Main Icon
                Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(22),
                    onTap: widget.onChatToggle,
                    child: Container(
                      width: 44,
                      height: 44,
                      margin: EdgeInsets.only(bottom: visibleControls.isNotEmpty ? 8 : 0),
                      decoration: BoxDecoration(
                        color: _isHovered ? Colors.white.withValues(alpha: 0.1) : Colors.transparent,
                        shape: BoxShape.circle,
                      ),
                      child: Center(
                        child: FaIcon(
                          FontAwesomeIcons.atom, // Abstract "Agent" icon
                          color: _isHovered ? ZoyaTheme.accent : Colors.white.withValues(alpha: 0.8),
                          size: 20,
                        ),
                      ),
                    ),
                  ),
                ),

                // Controls List
                ...visibleControls.map(
                  (c) => Padding(
                    padding: const EdgeInsets.only(bottom: 8.0),
                    child: c.widget,
                  ),
                ),
                // Note: Disconnect is last in the list logic
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ControlToggle extends StatelessWidget {
  final FaIconData icon;
  final bool isActive;
  final VoidCallback onTap;
  final Color activeColor;
  final Color inactiveColor;
  final bool useVisualizer;

  const _ControlToggle({
    required this.icon,
    required this.isActive,
    required this.onTap,
    this.activeColor = Colors.white,
    this.inactiveColor = const Color(0xFF94A3B8),
    this.useVisualizer = false,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(50),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          width: useVisualizer ? 60 : 44, // Expand horizontally
          height: 44,
          padding: useVisualizer ? const EdgeInsets.symmetric(horizontal: 12) : EdgeInsets.zero,
          decoration: BoxDecoration(
            color: useVisualizer ? Colors.white.withValues(alpha: 0.1) : Colors.transparent,
            borderRadius: BorderRadius.circular(22),
            border: useVisualizer ? Border.all(color: Colors.white.withValues(alpha: 0.1)) : null,
          ),
          child: Center(
            child: useVisualizer
                ? const _MobileVisualizer() // Standard horizontal Row
                : FaIcon(
                    icon,
                    color: isActive ? activeColor : inactiveColor,
                    size: 18,
                  ),
          ),
        ),
      ),
    );
  }
}

class _MobileVisualizer extends StatefulWidget {
  const _MobileVisualizer();

  @override
  State<_MobileVisualizer> createState() => _MobileVisualizerState();
}

class _MobileVisualizerState extends State<_MobileVisualizer> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    unawaited(_controller.repeat());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(4, (index) {
        return AnimatedBuilder(
          animation: _controller,
          builder: (context, child) {
            // Get real audio level from LiveKit
            final session = context.read<SessionProvider>();
            double vol = 0;
            if (session.room?.localParticipant != null) {
              vol = session.room!.localParticipant!.audioLevel;
            }

            // Apply gain to make it visible
            // Audio level is 0.0-1.0 but speech often hovers low
            final double activeGain = (vol * 5).clamp(0.0, 1.0);

            // Allow very subtle breathing when idle so it doesn't look broken
            final double idleGain = 0.15;
            final double effectiveGain = math.max(activeGain, idleGain);

            final t = _controller.value;
            // Phase shifted sine waves
            final val = math.sin(t * 2 * math.pi + (index * 0.8));
            final normalized = (val + 1) / 2; // 0.0 to 1.0

            // Modulate height by volume
            final height = 4.0 + (normalized * 12.0 * effectiveGain);

            return Container(
              width: 3,
              height: height,
              margin: const EdgeInsets.symmetric(horizontal: 1.5),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(1.5),
              ),
            );
          },
        );
      }),
    );
  }
}

class _DisconnectButton extends StatelessWidget {
  final VoidCallback onTap;
  final bool vertical;

  const _DisconnectButton({required this.onTap, this.vertical = false});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(24),
        child: Container(
          height: 44,
          padding: EdgeInsets.symmetric(horizontal: vertical ? 0 : 20),
          width: vertical ? 44 : null, // Fixed width if vertical
          decoration: BoxDecoration(
            color: const Color(0xFF1F1212), // Very dark red/black bg for button
            borderRadius: BorderRadius.circular(24),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const FaIcon(FontAwesomeIcons.phoneSlash, color: Color(0xFFEF4444), size: 16),
              if (!vertical) ...[
                const SizedBox(width: 10),
                const Text(
                  'END CALL',
                  style: TextStyle(
                    color: Color(0xFFEF4444), // Red-500
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.0,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

// Removing _Dash class as it is no longer used in the new React-aligned design

class _FloatingWidgetsPanel extends StatelessWidget {
  final ValueChanged<WorkbenchTab> onOpenTab;

  const _FloatingWidgetsPanel({required this.onOpenTab});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      spacing: 10, // Reduced gap
      children: [
        _FloatingWidget(
          key: const Key('floating_icon_active_workflows'),
          icon: FontAwesomeIcons.bolt,
          label: 'Active Workflows',
          onTap: () => onOpenTab(WorkbenchTab.agents),
        ),
        _FloatingWidget(
          key: const Key('floating_icon_n8n'),
          icon: FontAwesomeIcons.networkWired,
          label: 'n8n Connected',
          onTap: () => onOpenTab(WorkbenchTab.logs),
        ),
        _FloatingWidget(
          key: const Key('floating_icon_system_health'),
          icon: FontAwesomeIcons.microchip,
          label: 'System Health',
          onTap: () => onOpenTab(WorkbenchTab.memory),
        ),
      ],
    );
  }
}

class _FloatingWidget extends StatefulWidget {
  final FaIconData icon;
  final String label;
  final VoidCallback onTap;

  const _FloatingWidget({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  State<_FloatingWidget> createState() => _FloatingWidgetState();
}

class _FloatingWidgetState extends State<_FloatingWidget> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: InkWell(
        onTap: widget.onTap,
        borderRadius: BorderRadius.circular(12),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          height: 44,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: const Color(0xFF000A14).withValues(alpha: _hover ? 0.8 : 0.4),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: _hover ? ZoyaTheme.accent.withValues(alpha: 0.3) : Colors.white.withValues(alpha: 0.05),
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              FaIcon(widget.icon, color: _hover ? ZoyaTheme.accent : Colors.white70, size: 16),
              AnimatedSize(
                duration: const Duration(milliseconds: 300),
                child: SizedBox(
                  width: _hover ? null : 0,
                  child: Padding(
                    padding: EdgeInsets.only(left: _hover ? 10 : 0),
                    child: Text(
                      _hover ? widget.label : '',
                      style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w500),
                      maxLines: 1,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
