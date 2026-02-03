import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../ui/zoya_theme.dart';
import '../glass_container.dart';
import '../../state/providers/settings_provider.dart';

// --- Status Dropdown (Top Right) ---
class StatusDropdown extends StatelessWidget {
  const StatusDropdown({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 250,
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: const Color(0xFF000A14).withValues(alpha: 0.6), // rgba(0, 10, 20, 0.6)
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF00F3FF).withValues(alpha: 0.2)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.4),
            blurRadius: 20,
            offset: const Offset(0, 4),
          )
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.only(bottom: 8),
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: ZoyaTheme.accent.withValues(alpha: 0.1))),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'SYSTEM STATUS',
                  style: ZoyaTheme.fontDisplay.copyWith(
                    color: ZoyaTheme.accent,
                    fontSize: 12, // 0.9em
                  ),
                ),
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: const Color(0xFF00FF00), // #0f0
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(color: const Color(0xFF00FF00), blurRadius: 10),
                    ],
                  ),
                ),
              ],
            ),
          ),
          // Rows
          Consumer<SettingsProvider>(
            builder: (ctx, settings, _) {
              return Column(
                children: [
                   _buildStatusRow('LLM Model', settings.llmModel),
                   _buildStatusRow('Provider', settings.llmProvider.toUpperCase()),
                   _buildStatusRow('Latency', '~24ms'),
                   _buildStatusRow('Agent', 'Active', isLast: true),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildStatusRow(String label, String value, {bool isLast = false}) {
    return Padding(
      padding: EdgeInsets.only(bottom: isLast ? 0 : 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: ZoyaTheme.statusLabel),
          Text(value, style: ZoyaTheme.statusValue),
        ],
      ),
    );
  }
}

// --- Floating Widgets (Right) ---
class FloatingWidgets extends StatelessWidget {
  const FloatingWidgets({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        _FloatingWidget(icon: Icons.bolt, label: 'Active Workflows'),
        const SizedBox(height: 15),
        _FloatingWidget(icon: Icons.hub, label: 'n8n Connected'),
        const SizedBox(height: 15),
        _FloatingWidget(icon: Icons.memory, label: 'System Health'),
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
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
        width: _isHovered ? 200 : 50,
        height: 50,
        decoration: BoxDecoration(
          color: _isHovered 
              ? ZoyaTheme.accent.withValues(alpha: 0.1)
              : const Color(0xFF000A14).withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: _isHovered 
                ? ZoyaTheme.accent 
                : Colors.white.withValues(alpha: 0.1),
          ),
          // Backdrop blur is handled by GlassContainer usually, skipping for simple Container
        ),
        child: Row(
          children: [
             Center(
               child: Icon(
                 widget.icon,
                 color: _isHovered ? ZoyaTheme.accent : ZoyaTheme.textMuted,
                 size: 20, // 1.2em
               ),
             ),
             if (_isHovered)
               Expanded(
                 child: FadeTransition(
                   opacity: AlwaysStoppedAnimation(1), // In code: opacity 0 -> 1 with delay
                   child: Text(
                     widget.label,
                     style: ZoyaTheme.fontBody.copyWith(
                       color: ZoyaTheme.textMain,
                       fontSize: 14,
                     ),
                     overflow: TextOverflow.clip,
                     maxLines: 1,
                     softWrap: false,
                   ),
                 ),
               ),
          ],
        ),
      ),
    );
  }
}

// --- Voice Panel (Left) ---
class VoicePanel extends StatelessWidget {
  final bool isUserSpeaking;
  const VoicePanel({super.key, this.isUserSpeaking = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 60,
      height: 200,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
         color: const Color(0xFF000A14).withValues(alpha: 0.4),
         borderRadius: BorderRadius.circular(30),
         border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _VBar(duration: 800, isAnimating: isUserSpeaking),
          const SizedBox(height: 8),
          _VBar(duration: 1200, isAnimating: isUserSpeaking),
          const SizedBox(height: 8),
          _VBar(duration: 900, isAnimating: isUserSpeaking),
          const SizedBox(height: 8),
          _VBar(duration: 1100, isAnimating: isUserSpeaking),
          const SizedBox(height: 8),
          _VBar(duration: 700, isAnimating: isUserSpeaking),
        ],
      ),
    );
  }
}

class _VBar extends StatefulWidget {
  final int duration;
  final bool isAnimating;
  const _VBar({required this.duration, required this.isAnimating});

  @override
  State<_VBar> createState() => _VBarState();
}

class _VBarState extends State<_VBar> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _heightAnim;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: Duration(milliseconds: widget.duration),
    );
    
    _heightAnim = Tween<double>(begin: 10, end: 30).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
    
    _opacityAnim = Tween<double>(begin: 0.3, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );

    if (widget.isAnimating) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void didUpdateWidget(_VBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isAnimating != oldWidget.isAnimating) {
      if (widget.isAnimating) {
        _controller.repeat(reverse: true);
      } else {
        _controller.animateTo(0); // Return to base state
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (ctx, _) {
        return Container(
          width: 6,
          height: _heightAnim.value,
          decoration: BoxDecoration(
            color: ZoyaTheme.accent.withValues(alpha: _opacityAnim.value),
            borderRadius: BorderRadius.circular(3),
          ),
        );
      },
    );
  }
}
