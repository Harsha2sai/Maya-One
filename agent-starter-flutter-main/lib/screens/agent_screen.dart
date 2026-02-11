import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:provider/provider.dart';
import '../ui/zoya_theme.dart';
import '../state/providers/session_provider.dart';
import '../state/controllers/orb_controller.dart';
import '../state/controllers/app_init_controller.dart';
import '../widgets/cosmic_orb.dart';
import '../widgets/classic_orb.dart';
import '../widgets/shell_sidebar.dart';
import '../widgets/session/chat_overlay.dart';
import '../state/providers/chat_provider.dart';
import '../state/providers/settings_provider.dart';

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
    _setupTranscriptionListener();
  }

  void _setupTranscriptionListener() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final session = context.read<SessionProvider>();
      final chat = context.read<ChatProvider>();

      final room = session.room;
      if (room != null) {
        room.createListener().on<lk.TranscriptionEvent>((event) {
          chat.addTranscription(event);
        });
      } else {
        // If room not ready yet, try again in a bit
        Future.delayed(const Duration(seconds: 1), _setupTranscriptionListener);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    // We do NOT use OrbController for minimized state anymore, we use local state or pass it down
    // consistent with React's uni-directional flow for this view.
    final initController = context.watch<AppInitController>();
    final sessionProvider = context.watch<SessionProvider>();
    final orb = context.watch<OrbController>(); // Still used for mute state etc
    final settings = context.watch<SettingsProvider>();
    final interfaceTheme = settings.interfaceTheme;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. Background Layer (if any specific, otherwise inherited)
          if (interfaceTheme == 'classic')
            Positioned.fill(
              child: Container(
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
              ),
            ),
          // 2. Main Content Layer (Orb OR "Neural Link Active" text)
          if (!_chatOpen)
            // Centered Orb when chat is closed (moved down 1.5cm / 57px)
            Positioned.fill(
              child: Center(
                child: Consumer2<OrbController, AppInitController>(
                  builder: (ctx, orb, init, _) {
                    if (init.state.index < InitState.orbAppear.index) {
                      return const SizedBox.shrink();
                    }

                    final isMicEnabled = !orb.isMuted;

                    if (interfaceTheme == 'classic') {
                      return ClassicOrb(
                        state: orb.orbState,
                        isMicEnabled: isMicEnabled,
                        minimized: false,
                        size: 300, // Increased from default 200
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
                        sessionProvider.setMicrophoneEnabled(!orb.isMuted);
                      },
                      onLongPress: () => orb.resetPosition(),
                      onPanUpdate: (delta) => orb.updatePosition(delta),
                    );
                  },
                ),
              ),
            ),

          // "NEURAL LINK ACTIVE" text when chat is open
          if (_chatOpen && interfaceTheme == 'zoya')
            Positioned.fill(
              child: Center(
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
              ),
            ),

          // Floating Widgets (Right)
          if (interfaceTheme == 'zoya')
            Positioned(
              right: 20,
              top: 0,
              bottom: 0,
              child: Center(
                child: _FloatingWidgetsPanel(),
              ),
            ),

          // 3. Status Panel (Top Right)
          // Z-Index: 20
          if (interfaceTheme == 'zoya')
            Positioned(
              top: 20,
              right: 20,
              child: _SystemStatusPanel(),
            ),

          // 4. Chat Overlay Layer
          // Z-Index: 30
          // In React, this is "absolute inset-0" (fullscreen) but with pointer-events logic.
          if (_chatOpen)
            Positioned.fill(
              // We use a stack to replicate the "inset-0" but the child is the panel.
              // To ensure clicks pass through outside the panel, we wrap the panel in a layout
              // that allows transparency hits if the panel itself doesn't cover everything.
              // However, ChatOverlay in flutter is designed as a distinct widget.
              // We need to ensure it doesn't block clicks on the bottom bar.
              bottom: 0, // Take full screen height
              child: ChatOverlay(
                onClose: () => setState(() => _chatOpen = false),
              ),
            ),

          // Minimized Orb (bottom right) when chat is open - Re-positioned for Z-Index
          if (_chatOpen)
            Positioned(
              right: 40,
              bottom: 140,
              child: Consumer2<OrbController, AppInitController>(
                builder: (ctx, orb, init, _) {
                  if (init.state.index < InitState.orbAppear.index) {
                    return const SizedBox.shrink();
                  }

                  final isMicEnabled = !orb.isMuted;

                  if (interfaceTheme == 'classic') {
                    return ClassicOrb(
                      state: orb.orbState,
                      isMicEnabled: isMicEnabled,
                      minimized: true,
                      size: 120, // Increased from 80
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
                      sessionProvider.setMicrophoneEnabled(!orb.isMuted);
                    },
                  );
                },
              ),
            ),

          // 5. Sidebar Layer (Left)
          // Global navigation
          if (widget.showSidebar)
            Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              child: ShellSidebar(
                activePage: 'home',
                onNavigate: (_) {},
              ),
            ),

          // 6. Left Vertical Control Bar
          // Z-Index: 50 (Highest Priority)
          Positioned(
            left: 20, // Floating slightly off the left edge
            top: 0,
            bottom: 0, // Centered vertically
            child: Center(
              child: _ControlBar(
                onChatToggle: () => setState(() => _chatOpen = !_chatOpen),
                isChatOpen: _chatOpen,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SystemStatusPanel extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final connectionState = context.watch<SessionProvider>().connectionState;
    final isConnected = connectionState == SessionConnectionState.connected;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF000A14).withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFF00F3FF).withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Status indicator dot
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: isConnected ? const Color(0xFF00FF00) : Colors.orange,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: isConnected ? const Color(0xFF00FF00) : Colors.orange,
                  blurRadius: 8,
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          // Status text
          Text(
            isConnected ? 'CONNECTED' : connectionState.name.toUpperCase(),
            style: ZoyaTheme.fontDisplay.copyWith(
              fontSize: 10,
              color: ZoyaTheme.accent,
              letterSpacing: 1,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  final String label;
  final String value;
  const _StatusRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.white60, fontSize: 13)),
          Text(
            value,
            style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 13, fontFamily: 'GeistMono'),
          ),
        ],
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
    final isChatOpen = widget.isChatOpen;

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
            session.setMicrophoneEnabled(!orb.isMuted);
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
                Container(
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
                      // Animate color based on hover?
                      color: _isHovered ? ZoyaTheme.accent : Colors.white.withValues(alpha: 0.8),
                      size: 20,
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
  final IconData icon;
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
    )..repeat();
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
  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      spacing: 10, // Reduced gap
      children: [
        _FloatingWidget(icon: FontAwesomeIcons.bolt, label: 'Active Workflows'),
        _FloatingWidget(icon: FontAwesomeIcons.networkWired, label: 'n8n Connected'),
        _FloatingWidget(icon: FontAwesomeIcons.microchip, label: 'System Health'),
      ],
    );
  }
}

class _FloatingWidget extends StatefulWidget {
  final IconData icon;
  final String label;

  const _FloatingWidget({required this.icon, required this.label});

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
    );
  }
}
