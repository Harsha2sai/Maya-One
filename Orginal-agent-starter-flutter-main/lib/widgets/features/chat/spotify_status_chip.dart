import 'package:flutter/material.dart';

import '../../../ui/theme/app_theme.dart';

class SpotifyStatusChip extends StatelessWidget {
  final bool connected;
  final String? displayName;
  final VoidCallback? onTap;

  const SpotifyStatusChip({
    super.key,
    required this.connected,
    this.displayName,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = connected ? Colors.greenAccent : Colors.white38;
    final label = connected
        ? 'Spotify${(displayName ?? '').isNotEmpty ? ' · $displayName' : ''}'
        : 'Spotify disconnected';

    return InkWell(
      key: const Key('spotify_status_chip'),
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.white24),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.music_note, size: 14, color: color),
            const SizedBox(width: 6),
            Text(
              label,
              style: ZoyaTheme.fontBody.copyWith(
                fontSize: 11,
                color: Colors.white70,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
