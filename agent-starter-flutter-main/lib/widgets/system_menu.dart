import 'package:flutter/material.dart';
import '../../ui/zoya_theme.dart';

class SystemMenu extends StatelessWidget {
  const SystemMenu({super.key});

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      icon: const Icon(Icons.more_vert, color: ZoyaTheme.textMuted),
      offset: const Offset(0, 40),
      color: ZoyaTheme.sidebarBg.withValues(alpha: 0.95),
      elevation: 8,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: ZoyaTheme.accent.withValues(alpha: 0.2)),
      ),
      onSelected: (value) {
        // Handle menu actions
        switch (value) {
          case 'docs':
            break;
          case 'shortcuts':
            break;
          case 'feedback':
            break;
        }
      },
      itemBuilder: (context) => [
        _buildMenuItem('docs', Icons.description, 'Documentation'),
        _buildMenuItem('shortcuts', Icons.keyboard, 'Keyboard Shortcuts'),
        _buildMenuItem('feedback', Icons.feedback, 'Send Feedback'),
        const PopupMenuDivider(),
        _buildMenuItem('about', Icons.info, 'About Zoya'),
      ],
    );
  }

  PopupMenuItem<String> _buildMenuItem(String value, IconData icon, String label) {
    return PopupMenuItem<String>(
      value: value,
      child: Row(
        children: [
          Icon(icon, size: 18, color: ZoyaTheme.accent),
          const SizedBox(width: 12),
          Text(
            label,
            style: ZoyaTheme.fontBody.copyWith(fontSize: 13, color: ZoyaTheme.textMain),
          ),
        ],
      ),
    );
  }
}
