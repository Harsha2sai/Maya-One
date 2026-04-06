import 'package:flutter/material.dart';

import '../../../ui/theme/app_theme.dart';

class ConversationHeader extends StatelessWidget {
  final String title;
  final VoidCallback onClose;

  const ConversationHeader({
    super.key,
    required this.title,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 18, 24, 12),
      child: Stack(
        alignment: Alignment.center,
        children: [
          Center(
            child: Text(
              title,
              style: ZoyaTheme.fontDisplay.copyWith(
                fontSize: 18,
                color: Colors.white,
                letterSpacing: 0.4,
              ),
            ),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: IconButton(
              onPressed: onClose,
              icon: const Icon(Icons.close, color: Colors.white70, size: 20),
              splashRadius: 18,
              tooltip: 'Close Chat',
            ),
          ),
        ],
      ),
    );
  }
}
