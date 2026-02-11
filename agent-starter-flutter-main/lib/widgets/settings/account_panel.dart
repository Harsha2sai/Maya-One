import 'package:flutter/material.dart';
import '../shared_widgets.dart';
import '../../ui/zoya_theme.dart';
import '../../state/providers/auth_provider.dart';
import 'package:provider/provider.dart';

class AccountPanel extends StatelessWidget {
  const AccountPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('👤 User Account', 'Manage your authentication and synced data.'),
        const SizedBox(height: 30),
        if (auth.isAuthenticated) ...[
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: ZoyaTheme.accent.withValues(alpha: 0.05),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: ZoyaTheme.accent.withValues(alpha: 0.1)),
            ),
            child: Row(
              children: [
                const CircleAvatar(
                  backgroundColor: ZoyaTheme.accent,
                  child: Icon(Icons.person, color: Colors.black),
                ),
                const SizedBox(width: 16),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Logged in as', style: TextStyle(color: Colors.white60, fontSize: 12)),
                    Text(auth.user!.email!, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16)),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 30),
          ElevatedButton.icon(
            onPressed: () {
              auth.signOut();
              Navigator.pop(context);
            },
            icon: const Icon(Icons.logout),
            label: const Text('SIGN OUT'),
            style: ElevatedButton.styleFrom(
              backgroundColor: ZoyaTheme.danger.withValues(alpha: 0.2),
              foregroundColor: ZoyaTheme.danger,
              minimumSize: const Size(200, 50),
            ),
          ),
        ] else ...[
          const Center(
            child: Column(
              children: [
                Icon(Icons.account_circle_outlined, size: 80, color: Colors.white24),
                SizedBox(height: 16),
                Text('Guest Account', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
                SizedBox(height: 8),
                Text(
                  'Log in to sync your settings across devices.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white38, fontSize: 14),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}
