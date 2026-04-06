import 'package:flutter/material.dart';
import '../../../ui/theme/app_theme.dart';

class MemoryStubPanel extends StatelessWidget {
  const MemoryStubPanel({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.memory, size: 64, color: ZoyaTheme.accent.withValues(alpha: 0.5)),
            const SizedBox(height: 16),
            Text(
              'Memory & Core Context',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: ZoyaTheme.textMain,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Explicit placeholder for future memory timeline and core context management.',
              textAlign: TextAlign.center,
              style: TextStyle(color: ZoyaTheme.textMuted),
            ),
          ],
        ),
      ),
    );
  }
}
