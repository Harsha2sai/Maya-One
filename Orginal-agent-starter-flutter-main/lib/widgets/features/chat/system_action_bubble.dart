import 'dart:async';

import 'package:flutter/material.dart';

import '../../../ui/theme/app_theme.dart';

class SystemActionBubble extends StatefulWidget {
  final String actionType;
  final String message;
  final String detail;
  final bool success;
  final bool rollbackAvailable;
  final VoidCallback? onDismiss;
  final VoidCallback? onUndo;
  final bool autoDismiss;

  const SystemActionBubble({
    super.key,
    required this.actionType,
    required this.message,
    this.detail = '',
    required this.success,
    this.rollbackAvailable = false,
    this.onDismiss,
    this.onUndo,
    this.autoDismiss = true,
  });

  @override
  State<SystemActionBubble> createState() => _SystemActionBubbleState();
}

class _SystemActionBubbleState extends State<SystemActionBubble> {
  Timer? _dismissTimer;

  @override
  void initState() {
    super.initState();
    if (widget.autoDismiss) {
      _dismissTimer = Timer(const Duration(seconds: 4), () {
        widget.onDismiss?.call();
      });
    }
  }

  @override
  void dispose() {
    _dismissTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final accentColor = widget.success ? ZoyaTheme.success : ZoyaTheme.danger;
    final icon = widget.success ? Icons.check_circle_outline : Icons.error_outline;

    return Material(
      color: Colors.transparent,
      child: Container(
        key: const Key('system_action_bubble'),
        margin: const EdgeInsets.symmetric(horizontal: 24),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF111827).withValues(alpha: 0.96),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: accentColor.withValues(alpha: 0.8), width: 1.4),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.35),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: accentColor, size: 22),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.actionType.replaceAll('_', ' ').toUpperCase(),
                    style: ZoyaTheme.fontDisplay.copyWith(
                      color: Colors.white,
                      fontSize: 12,
                      letterSpacing: 0.8,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    widget.message,
                    style: ZoyaTheme.fontBody.copyWith(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (widget.detail.trim().isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      widget.detail.trim(),
                      style: ZoyaTheme.fontBody.copyWith(
                        color: Colors.white70,
                        fontSize: 12,
                        height: 1.35,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (widget.rollbackAvailable)
              TextButton(
                onPressed: widget.onUndo,
                child: const Text('Undo'),
              ),
            IconButton(
              tooltip: 'Dismiss',
              onPressed: widget.onDismiss,
              icon: const Icon(Icons.close, color: Colors.white54, size: 18),
            ),
          ],
        ),
      ),
    );
  }
}
