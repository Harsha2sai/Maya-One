import 'package:flutter/material.dart';
import '../ui/zoya_theme.dart';
import '../core/config/provider_config.dart';

Widget buildSectionHeader(String title, String subtitle) {
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        title,
        style: ZoyaTheme.fontDisplay.copyWith(
          fontSize: 18,
          color: Colors.white,
          letterSpacing: 1,
        ),
      ),
      if (subtitle.isNotEmpty) ...[
        const SizedBox(height: 4),
        Text(
          subtitle,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.5),
            fontSize: 13,
          ),
        ),
      ],
    ],
  );
}

Widget buildSubsectionHeader(String title) {
  return Padding(
    padding: const EdgeInsets.only(bottom: 16, top: 8),
    child: Text(
      title,
      style: ZoyaTheme.fontDisplay.copyWith(
        fontSize: 14,
        color: ZoyaTheme.accent.withValues(alpha: 0.8),
        letterSpacing: 1,
      ),
    ),
  );
}

Widget buildStatusBadge(bool isConfigured) {
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: isConfigured 
          ? ZoyaTheme.success.withValues(alpha: 0.1) 
          : ZoyaTheme.danger.withValues(alpha: 0.1),
      borderRadius: BorderRadius.circular(4),
      border: Border.all(
        color: isConfigured 
            ? ZoyaTheme.success.withValues(alpha: 0.3) 
            : ZoyaTheme.danger.withValues(alpha: 0.3)
      ),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          isConfigured ? Icons.check_circle : Icons.error_outline,
          size: 12,
          color: isConfigured ? ZoyaTheme.success : ZoyaTheme.danger,
        ),
        const SizedBox(width: 4),
        Text(
          isConfigured ? 'READY' : 'MISSING',
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.bold,
            color: isConfigured ? ZoyaTheme.success : ZoyaTheme.danger,
          ),
        ),
      ],
    ),
  );
}
