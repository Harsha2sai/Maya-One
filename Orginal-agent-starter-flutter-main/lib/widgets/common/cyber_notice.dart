import 'package:flutter/material.dart';
import '../../ui/theme/app_theme.dart';

enum CyberNoticePriority { info, success, warning, critical }

class _CyberPalette {
  final Color accent;
  final Color bg;
  final Color fg;
  final IconData icon;

  const _CyberPalette({
    required this.accent,
    required this.bg,
    required this.fg,
    required this.icon,
  });
}

_CyberPalette _paletteFor(CyberNoticePriority priority) {
  switch (priority) {
    case CyberNoticePriority.success:
      return const _CyberPalette(
        accent: Color(0xFF00E7A7),
        bg: Color(0xFF0A1F1C),
        fg: Color(0xFFE9FFF9),
        icon: Icons.check_circle_outline,
      );
    case CyberNoticePriority.warning:
      return const _CyberPalette(
        accent: Color(0xFFFFB347),
        bg: Color(0xFF241708),
        fg: Color(0xFFFFF2DC),
        icon: Icons.warning_amber_rounded,
      );
    case CyberNoticePriority.critical:
      return const _CyberPalette(
        accent: Color(0xFFFF2A6D),
        bg: Color(0xFF2A0E1D),
        fg: Color(0xFFFFE7F0),
        icon: Icons.error_outline,
      );
    case CyberNoticePriority.info:
      return const _CyberPalette(
        accent: Color(0xFF00F3FF),
        bg: Color(0xFF0A1528),
        fg: Color(0xFFE8FDFF),
        icon: Icons.info_outline,
      );
  }
}

class CyberInlineNotice extends StatelessWidget {
  final String message;
  final CyberNoticePriority priority;
  final VoidCallback? onClose;
  final EdgeInsetsGeometry? padding;

  const CyberInlineNotice({
    super.key,
    required this.message,
    this.priority = CyberNoticePriority.info,
    this.onClose,
    this.padding,
  });

  @override
  Widget build(BuildContext context) {
    final p = _paletteFor(priority);
    return Container(
      padding: padding ?? const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: p.bg.withValues(alpha: 0.95),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: p.accent.withValues(alpha: 0.75)),
        boxShadow: [
          BoxShadow(
            color: p.accent.withValues(alpha: 0.2),
            blurRadius: 18,
            spreadRadius: 1,
          ),
        ],
      ),
      child: Row(
        children: [
          Icon(p.icon, color: p.accent, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: ZoyaTheme.fontBody.copyWith(color: p.fg, fontSize: 13),
            ),
          ),
          if (onClose != null)
            IconButton(
              onPressed: onClose,
              icon: Icon(Icons.close, color: p.fg.withValues(alpha: 0.9), size: 18),
              tooltip: 'Dismiss',
            ),
        ],
      ),
    );
  }
}

class CyberNoticeSnackBar {
  static SnackBar build(
    BuildContext context, {
    required String message,
    CyberNoticePriority priority = CyberNoticePriority.info,
    Duration duration = const Duration(seconds: 3),
  }) {
    return SnackBar(
      duration: duration,
      behavior: SnackBarBehavior.floating,
      elevation: 0,
      backgroundColor: Colors.transparent,
      content: CyberInlineNotice(
        message: message,
        priority: priority,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      ),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
    );
  }
}

class CyberAlertDialog extends StatelessWidget {
  final String title;
  final String message;
  final Widget? details;
  final CyberNoticePriority priority;
  final List<Widget> actions;

  const CyberAlertDialog({
    super.key,
    required this.title,
    required this.message,
    required this.actions,
    this.details,
    this.priority = CyberNoticePriority.info,
  });

  @override
  Widget build(BuildContext context) {
    final p = _paletteFor(priority);
    return AlertDialog(
      backgroundColor: const Color(0xFF13142A),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: BorderSide(color: p.accent.withValues(alpha: 0.7)),
      ),
      titlePadding: const EdgeInsets.fromLTRB(22, 20, 22, 0),
      contentPadding: const EdgeInsets.fromLTRB(22, 14, 22, 0),
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(
              color: p.accent.withValues(alpha: 0.18),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: p.accent.withValues(alpha: 0.35)),
            ),
            child: Icon(p.icon, color: p.accent, size: 24),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              title,
              style: ZoyaTheme.fontDisplay.copyWith(
                color: const Color(0xFFEFF3FF),
                fontSize: 26,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            message,
            style: ZoyaTheme.fontBody.copyWith(
              color: const Color(0xFFB7B9CC),
              fontSize: 16,
              height: 1.35,
            ),
          ),
          if (details != null) ...[
            const SizedBox(height: 14),
            details!,
          ],
        ],
      ),
      actionsPadding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
      actions: actions,
    );
  }
}
