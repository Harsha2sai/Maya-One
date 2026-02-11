import 'dart:math';
import 'package:flutter/material.dart';
import '../ui/zoya_theme.dart';

enum OrbState { idle, listening, thinking, speaking }

class CosmicOrb extends StatefulWidget {
  final OrbState state;
  final VoidCallback? onTap;
  final VoidCallback? onDoubleTap;
  final VoidCallback? onLongPress;
  final Function(Offset)? onPanUpdate;
  final bool isMicEnabled;
  final bool minimized;
  final double? size;
  final bool showStatus;

  const CosmicOrb({
    super.key, 
    this.state = OrbState.idle,
    this.onTap,
    this.onDoubleTap,
    this.onLongPress,
    this.onPanUpdate,
    this.isMicEnabled = true,
    this.minimized = false,
    this.size,
    this.showStatus = true,
  });

  @override
  State<CosmicOrb> createState() => _CosmicOrbState();
}

class _CosmicOrbState extends State<CosmicOrb> with TickerProviderStateMixin {
  late AnimationController _pulseController;
  late AnimationController _rotateController;
  
  // Particles
  late AnimationController _particleController;
  final List<OrbParticle> _particles = [];
  final Random _rng = Random();

  @override
  void initState() {
    super.initState();
    
    // Scale/Pulse Animation
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat(reverse: true);

    // Rotation Animation (for thinking state)
    _rotateController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();

    // Particle Animation
    _particleController = AnimationController(
      vsync: this,
      duration: const Duration(minutes: 5),
    )..repeat();

    _initParticles();
  }

  void _initParticles() {
    _particles.clear();
    // More particles spread across the full screen
    for (int i = 0; i < 100; i++) {
      _particles.add(OrbParticle(
        angle: _rng.nextDouble() * 2 * pi,
        radius: 100 + _rng.nextDouble() * 400, // Spread across screen
        speed: 0.1 + _rng.nextDouble() * 0.5,
        size: 0.5 + _rng.nextDouble() * 2.5, // Varied sizes
        opacity: 0.05 + _rng.nextDouble() * 0.3, // Subtle
      ));
    }
  }

  @override
  void didUpdateWidget(CosmicOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) {
      _updateAnimations();
    }
  }

  void _updateAnimations() {
    switch (widget.state) {
      case OrbState.listening:
        _pulseController.duration = const Duration(milliseconds: 1500);
        _pulseController.repeat(reverse: true);
        break;
      case OrbState.speaking:
        _pulseController.duration = const Duration(milliseconds: 800);
        _pulseController.repeat(reverse: true);
        break;
      case OrbState.thinking:
        _rotateController.duration = const Duration(seconds: 2);
        _rotateController.repeat();
        break;
      case OrbState.idle:
      default:
        _pulseController.duration = const Duration(seconds: 3);
        _pulseController.repeat(reverse: true);
        break;
    }
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _rotateController.dispose();
    _particleController.dispose();
    super.dispose();
  }

  String get _statusText {
    if (widget.minimized) return widget.state.name.toUpperCase();
    if (!widget.isMicEnabled) return 'MUTED';
    switch (widget.state) {
      case OrbState.listening: return 'LISTENING...';
      case OrbState.thinking: return 'PROCESSING...'; // React says PROCESSING
      case OrbState.speaking: return 'SPEAKING';
      case OrbState.idle: return 'AWAITING INPUT';
    }
  }

  @override
  Widget build(BuildContext context) {
    // Minimized state logic
    final double size = widget.size ?? (widget.minimized ? 80 : 200);
    final double fontSize = widget.minimized ? 10 : 18; // approx 1.2em
    final double textMargin = widget.minimized ? 15 : 40;

    return GestureDetector(
      onTap: widget.onTap,
      onDoubleTap: widget.onDoubleTap,
      onLongPress: widget.onLongPress,
      onPanUpdate: widget.onPanUpdate != null 
          ? (details) => widget.onPanUpdate!(details.delta) 
          : null,
      child: Column(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // The Orb Stack
        SizedBox(
          width: size * 1.5, // Allow space for glow/particles
          height: size * 1.5,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Particles (Background) - Full screen
              if (!widget.minimized)
                Positioned.fill(
                  child: AnimatedBuilder(
                    animation: _particleController,
                    builder: (ctx, child) {
                      final screenSize = MediaQuery.of(context).size;
                      return CustomPaint(
                        size: screenSize,
                        painter: OrbParticlePainter(
                          particles: _particles,
                          rotation: _particleController.value * 2 * pi,
                          color: ZoyaTheme.orbCore,
                        ),
                      );
                    },
                  ),
                ),
                
              // Main Orb
              AnimatedBuilder(
                animation: Listenable.merge([_pulseController, _rotateController]),
                builder: (context, child) {
                  return Transform.scale(
                    scale: _getScale(),
                    child: Transform.rotate(
                      angle: widget.state == OrbState.thinking 
                          ? _rotateController.value * 2 * pi 
                          : 0,
                      child: GestureDetector(
                        onTap: widget.onTap,
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          width: size,
                          height: size,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            gradient: RadialGradient(
                              center: Alignment.center,
                              radius: 0.5,
                              colors: widget.isMicEnabled 
                                ? [
                                    ZoyaTheme.orbCore.withValues(alpha: 0.9),
                                    ZoyaTheme.orbInner.withValues(alpha: 0.6),
                                  ]
                                : [
                                    const Color(0xFFFF3B30).withValues(alpha: 0.4), // Muted red
                                    const Color(0xFF501414).withValues(alpha: 0.4),
                                  ],
                            ),
                            boxShadow: widget.isMicEnabled
                                ? [
                                    BoxShadow(
                                      color: ZoyaTheme.orbCore.withValues(alpha: 0.8),
                                      blurRadius: 60 * (size / 200),
                                      spreadRadius: 0,
                                    ),
                                    BoxShadow(
                                      color: ZoyaTheme.orbInner.withValues(alpha: 0.5),
                                      blurRadius: 120 * (size / 200),
                                      spreadRadius: 0,
                                    ),
                                  ]
                                : [
                                    BoxShadow(
                                      color: const Color(0xFFFF3B30).withValues(alpha: 0.2),
                                      blurRadius: 30 * (size / 200),
                                    )
                                  ],
                          ),
                          // Simulated Inset Shadow using inner container
                          child: Container(
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: RadialGradient(
                                center: Alignment.center,
                                radius: 0.9,
                                colors: [
                                  Colors.transparent,
                                  widget.isMicEnabled 
                                      ? ZoyaTheme.orbOuter.withValues(alpha: 0.4)
                                      : const Color(0xFFFF3B30).withValues(alpha: 0.2),
                                ],
                                stops: const [0.6, 1.0], // Inner transparent, outer colored
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ],
          ),
        ),
        
        if (widget.showStatus) ...[
          SizedBox(height: textMargin),
          // Status Text
          _StatusText(
            text: _statusText,
            fontSize: fontSize,
          ),
        ],
      ],
    ),);
  }

  double _getScale() {
    final t = _pulseController.value;
    
    switch (widget.state) {
      case OrbState.listening:
        // React: 0% 1, 25% 1.1, 50% 1.05, 75% 1.15, 100% 1
        if (t < 0.25) return 1.0 + (t / 0.25) * 0.1;
        if (t < 0.5) return 1.1 - ((t - 0.25) / 0.25) * 0.05;
        if (t < 0.75) return 1.05 + ((t - 0.5) / 0.25) * 0.1;
        return 1.15 - ((t - 0.75) / 0.25) * 0.15;
      case OrbState.speaking:
        // React: 0/100 scale 1, 50% scale 1.12
        return 1.0 + (sin(t * pi) * 0.12);
      case OrbState.thinking:
        // React: rotate (handled) scale 1 -> 1.08
        return 1.0 + (sin(t * pi) * 0.08);
      case OrbState.idle:
      default:
        // React: scale(1) -> scale(1.05)
        return 1.0 + (sin(t * pi) * 0.05);
    }
  }
}

class _StatusText extends StatefulWidget {
  final String text;
  final double fontSize;

  const _StatusText({required this.text, required this.fontSize});

  @override
  State<_StatusText> createState() => _StatusTextState();
}

class _StatusTextState extends State<_StatusText> with SingleTickerProviderStateMixin {
  late AnimationController _glowController;
  late Animation<double> _glowAnimation;

  @override
  void initState() {
    super.initState();
    _glowController = AnimationController(
       vsync: this,
       duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    
    _glowAnimation = Tween<double>(begin: 20, end: 30).animate(
      CurvedAnimation(parent: _glowController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _glowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _glowAnimation,
      builder: (context, child) {
        return Text(
          widget.text,
          style: ZoyaTheme.fontDisplay.copyWith(
            fontSize: widget.fontSize,
            letterSpacing: widget.fontSize / 4, // 4px for 1.2em
            color: ZoyaTheme.accent,
            shadows: [
              Shadow(color: ZoyaTheme.accentGlow, blurRadius: _glowAnimation.value),
              Shadow(color: ZoyaTheme.accent, blurRadius: _glowAnimation.value / 2),
            ],
          ),
        );
      },
    );
  }
}

class OrbParticle {
  double angle;
  double radius;
  double speed;
  double size;
  double opacity;

  OrbParticle({
    required this.angle,
    required this.radius,
    required this.speed,
    required this.size,
    required this.opacity,
  });
}

class OrbParticlePainter extends CustomPainter {
  final List<OrbParticle> particles;
  final double rotation;
  final Color color;

  OrbParticlePainter({
    required this.particles, 
    required this.rotation,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final paint = Paint()
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.fill;

    for (var p in particles) {
      // Rotate the particle
      final currentAngle = p.angle + (rotation * p.speed * 0.1); 
      
      final x = center.dx + cos(currentAngle) * p.radius;
      final y = center.dy + sin(currentAngle) * p.radius;

      paint.color = color.withValues(alpha: p.opacity);
      canvas.drawCircle(Offset(x, y), p.size, paint);
    }
  }

  @override
  bool shouldRepaint(covariant OrbParticlePainter oldDelegate) => true;
}
