import 'dart:async';

import 'package:flutter/material.dart';

import '../../../state/controllers/ide_workspace_controller.dart';
import '../../../ui/theme/app_theme.dart';

class BuddyMonitor extends StatefulWidget {
  const BuddyMonitor({
    super.key,
    required this.species,
    required this.state,
    required this.isShiny,
    required this.catchingUp,
  });

  final BuddySpecies species;
  final BuddyState state;
  final bool isShiny;
  final bool catchingUp;

  @override
  State<BuddyMonitor> createState() => _BuddyMonitorState();
}

class _BuddyMonitorState extends State<BuddyMonitor> {
  Timer? _timer;
  int _frame = 0;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 320), (_) {
      if (!mounted) return;
      setState(() {
        _frame = (_frame + 1) % 3;
      });
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sprite = _spriteForState(widget.species, widget.state, _frame);
    return Container(
      key: const Key('buddy-monitor'),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF0D1422),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: ZoyaTheme.glassBorder),
      ),
      child: Row(
        children: [
          _PixelSprite(
            matrix: sprite,
            pixelSize: 4,
            isShiny: widget.isShiny,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Buddy Monitor',
                  style: ZoyaTheme.fontBody.copyWith(
                    color: ZoyaTheme.textMain,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  _stateLabel(widget.state),
                  style: TextStyle(
                    color: _stateColor(widget.state),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  widget.catchingUp ? 'Catching up' : 'Live',
                  style: TextStyle(
                    color: widget.catchingUp ? Colors.orangeAccent : Colors.greenAccent,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _stateLabel(BuddyState state) {
    switch (state) {
      case BuddyState.idle:
        return 'Idle';
      case BuddyState.working:
        return 'Working';
      case BuddyState.complete:
        return 'Complete';
      case BuddyState.error:
        return 'Error';
    }
  }

  static Color _stateColor(BuddyState state) {
    switch (state) {
      case BuddyState.idle:
        return ZoyaTheme.textMuted;
      case BuddyState.working:
        return Colors.orangeAccent;
      case BuddyState.complete:
        return Colors.greenAccent;
      case BuddyState.error:
        return ZoyaTheme.danger;
    }
  }

  static List<String> _spriteForState(
    BuddySpecies species,
    BuddyState state,
    int frame,
  ) {
    final idle = switch (species) {
      BuddySpecies.mayaCore => const [
          '..1111..',
          '.122221.',
          '12333221',
          '12333221',
          '.122221.',
          '..1441..',
          '.114411.',
          '...11...',
        ],
      BuddySpecies.orbitFox => const [
          '..1111..',
          '.122221.',
          '12322321',
          '12322321',
          '.122221.',
          '..1441..',
          '.114411.',
          '..1..1..',
        ],
      BuddySpecies.terminalOtter => const [
          '..1111..',
          '.122221.',
          '12333321',
          '12333321',
          '.122221.',
          '..1441..',
          '.114411.',
          '..1111..',
        ],
      BuddySpecies.neonCat => const [
          '1......1',
          '.122221.',
          '12333221',
          '12333221',
          '.122221.',
          '..1441..',
          '.114411.',
          '..1..1..',
        ],
    };

    if (state == BuddyState.working) {
      return frame.isEven ? idle : idle.map((line) => line.replaceAll('4', '5')).toList(growable: false);
    }
    if (state == BuddyState.complete) {
      return idle.map((line) => line.replaceAll('3', frame.isEven ? '3' : '5')).toList(growable: false);
    }
    if (state == BuddyState.error) {
      return idle.map((line) => line.replaceAll('2', frame.isEven ? '6' : '2')).toList(growable: false);
    }
    return idle;
  }
}

class _PixelSprite extends StatelessWidget {
  const _PixelSprite({
    required this.matrix,
    required this.pixelSize,
    required this.isShiny,
  });

  final List<String> matrix;
  final double pixelSize;
  final bool isShiny;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: matrix.first.length * pixelSize,
      height: matrix.length * pixelSize,
      child: Column(
        children: matrix
            .map(
              (line) => Row(
                children: line.split('').map((cell) {
                  final color = _colorFor(cell, isShiny);
                  return Container(
                    width: pixelSize,
                    height: pixelSize,
                    color: color,
                  );
                }).toList(growable: false),
              ),
            )
            .toList(growable: false),
      ),
    );
  }

  static Color _colorFor(String token, bool isShiny) {
    switch (token) {
      case '1':
        return isShiny ? const Color(0xFF67E8F9) : const Color(0xFF38BDF8);
      case '2':
        return const Color(0xFF0EA5E9);
      case '3':
        return const Color(0xFF7DD3FC);
      case '4':
        return const Color(0xFF1E293B);
      case '5':
        return const Color(0xFF22D3EE);
      case '6':
        return const Color(0xFFF87171);
      default:
        return Colors.transparent;
    }
  }
}
