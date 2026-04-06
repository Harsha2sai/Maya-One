import 'dart:async';

import 'package:flutter/material.dart';

import '../../../ui/theme/app_theme.dart';

class ConfirmationCard extends StatefulWidget {
  final String actionType;
  final String description;
  final bool destructive;
  final int timeoutSeconds;
  final ValueChanged<bool> onRespond;

  const ConfirmationCard({
    super.key,
    required this.actionType,
    required this.description,
    required this.destructive,
    required this.timeoutSeconds,
    required this.onRespond,
  });

  @override
  State<ConfirmationCard> createState() => _ConfirmationCardState();
}

class _ConfirmationCardState extends State<ConfirmationCard> {
  Timer? _timer;
  late int _remainingSeconds;
  bool _resolved = false;
  String? _resolutionText;

  @override
  void initState() {
    super.initState();
    _remainingSeconds = widget.timeoutSeconds;
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _resolved) return;
      if (_remainingSeconds <= 1) {
        _resolved = true;
        _resolutionText = 'Timed out — cancelled';
        timer.cancel();
        widget.onRespond(false);
        setState(() {});
        return;
      }
      setState(() {
        _remainingSeconds -= 1;
      });
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _respond(bool confirmed) {
    if (_resolved) return;
    _resolved = true;
    _resolutionText = confirmed ? 'Confirmed' : 'Cancelled';
    _timer?.cancel();
    widget.onRespond(confirmed);
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('confirmation_card'),
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color:
              widget.destructive ? ZoyaTheme.danger.withValues(alpha: 0.8) : ZoyaTheme.accent.withValues(alpha: 0.45),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                widget.destructive ? Icons.warning_amber_rounded : Icons.help_outline,
                color: widget.destructive ? ZoyaTheme.danger : ZoyaTheme.accent,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.actionType.replaceAll('_', ' ').toUpperCase(),
                  style: ZoyaTheme.fontDisplay.copyWith(
                    color: Colors.white,
                    fontSize: 13,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
              if (widget.destructive)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: ZoyaTheme.danger.withValues(alpha: 0.16),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    'Destructive',
                    style: ZoyaTheme.fontBody.copyWith(
                      color: ZoyaTheme.danger,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            widget.description,
            style: ZoyaTheme.fontBody.copyWith(
              color: Colors.white,
              fontSize: 14,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            _resolutionText ?? '${_remainingSeconds}s remaining',
            style: ZoyaTheme.fontBody.copyWith(
              color: Colors.white70,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              ElevatedButton(
                onPressed: _resolved ? null : () => _respond(true),
                style: ElevatedButton.styleFrom(
                  backgroundColor: ZoyaTheme.accent,
                  foregroundColor: Colors.black,
                ),
                child: const Text('Confirm'),
              ),
              const SizedBox(width: 10),
              OutlinedButton(
                onPressed: _resolved ? null : () => _respond(false),
                style: OutlinedButton.styleFrom(
                  foregroundColor: ZoyaTheme.danger,
                  side: BorderSide(color: ZoyaTheme.danger.withValues(alpha: 0.8)),
                ),
                child: const Text('Cancel'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
