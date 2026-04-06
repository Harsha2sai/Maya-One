import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'cosmic_orb.dart'; // For OrbState

class ClassicOrb extends StatefulWidget {
  final OrbState state;
  final bool isMicEnabled;
  final bool minimized;
  final double size;
  final VoidCallback? onTap;

  const ClassicOrb({
    super.key,
    required this.state,
    this.isMicEnabled = true,
    this.minimized = false,
    this.size = 200,
    this.onTap,
  });

  @override
  State<ClassicOrb> createState() => _ClassicOrbState();
}

class _ClassicOrbState extends State<ClassicOrb> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final double orbSize = widget.minimized ? widget.size : widget.size;
    
    return GestureDetector(
      onTap: widget.onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        width: orbSize,
        height: orbSize,
        decoration: const BoxDecoration(
          color: Colors.transparent, // Background removed for floating effect
          shape: BoxShape.circle,
        ),
        child: Center(
          child: _BarVisualizer(
            state: widget.state,
            isMicEnabled: widget.isMicEnabled,
            size: orbSize * 0.5,
          ),
        ),
      ),
    );
  }
}

class _BarVisualizer extends StatelessWidget {
  final OrbState state;
  final bool isMicEnabled;
  final double size;

  const _BarVisualizer({
    required this.state,
    required this.isMicEnabled,
    required this.size,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(5, (index) {
        return _ClassicBar(
          index: index,
          state: state,
          isMicEnabled: isMicEnabled,
          maxHeight: size,
        );
      }),
    );
  }
}

class _ClassicBar extends StatefulWidget {
  final int index;
  final OrbState state;
  final bool isMicEnabled;
  final double maxHeight;

  const _ClassicBar({
    required this.index,
    required this.state,
    required this.isMicEnabled,
    required this.maxHeight,
  });

  @override
  State<_ClassicBar> createState() => _ClassicBarState();
}

class _ClassicBarState extends State<_ClassicBar> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat();
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
      builder: (context, child) {
        double heightFactor = 0.2;
        if (!widget.isMicEnabled) {
          heightFactor = 0.1;
        } else {
          switch (widget.state) {
            case OrbState.listening:
              heightFactor = 0.3 + 0.4 * (0.5 + 0.5 * math.sin(_controller.value * 2 * math.pi + widget.index));
              break;
            case OrbState.speaking:
              heightFactor = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(_controller.value * 5 * math.pi + widget.index * 0.5));
              break;
            case OrbState.thinking:
              heightFactor = 0.2 + 0.3 * (0.5 + 0.5 * math.sin(_controller.value * 3 * math.pi + widget.index * 2));
              break;
            case OrbState.idle:
              heightFactor = 0.2 + 0.1 * math.sin(_controller.value * 2 * math.pi + widget.index);
              break;
          }
        }

        return Container(
          width: 6,
          height: widget.maxHeight * heightFactor,
          margin: const EdgeInsets.symmetric(horizontal: 2),
          decoration: BoxDecoration(
            color: widget.isMicEnabled ? Colors.white : Colors.white24,
            borderRadius: BorderRadius.circular(3),
            boxShadow: [
              if (widget.isMicEnabled)
                BoxShadow(
                  color: Colors.white.withValues(alpha: 0.5),
                  blurRadius: 4,
                ),
            ],
          ),
        );
      },
    );
  }
}
