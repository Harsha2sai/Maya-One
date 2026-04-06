import 'package:flutter/material.dart';

import '../../../ui/theme/app_theme.dart';

class JumpToLatestChip extends StatelessWidget {
  final VoidCallback onTap;

  const JumpToLatestChip({
    super.key,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: const Key('jump_to_latest_chip'),
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: const Color(0xFF111827).withValues(alpha: 0.96),
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: ZoyaTheme.glassBorder.withValues(alpha: 0.8)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.arrow_downward_rounded, size: 16, color: Colors.white),
              const SizedBox(width: 8),
              Text(
                'Jump to latest',
                style: ZoyaTheme.fontBody.copyWith(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
