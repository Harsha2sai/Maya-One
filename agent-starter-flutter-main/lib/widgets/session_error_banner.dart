import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:livekit_client/livekit_client.dart' as sdk;
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../state/providers/session_provider.dart';
import '../ui/zoya_theme.dart';

/// Displays the latest session or agent error as a small banner.
/// Shows a prominent dialog for critical errors like quota exceeded.
class SessionErrorBanner extends StatefulWidget {
  const SessionErrorBanner({super.key});

  @override
  State<SessionErrorBanner> createState() => _SessionErrorBannerState();
}

class _SessionErrorBannerState extends State<SessionErrorBanner> {
  bool _quotaDialogShown = false;

  @override
  Widget build(BuildContext context) {
    return Consumer<SessionProvider>(
      builder: (context, sessionProvider, _) {
        final session = sessionProvider.session;
        if (session == null) return const SizedBox.shrink();

        final sdk.SessionError? sessionError = session.error;
        final sdk.AgentFailure? agentError = session.agent.error;

        String? message = sessionError?.message ?? agentError?.message;
        
        // Hide the audio renderer error on Linux desktop (known limitation)
        if (message != null && !kIsWeb && Platform.isLinux) {
          if (message.contains('Failed to start native audio renderer')) {
            return const SizedBox.shrink();
          }
        }

        // Detect quota exceeded error and show prominent dialog instead of banner
        if (message != null && message.contains('minutes limit exceeded')) {
          if (!_quotaDialogShown) {
            _quotaDialogShown = true;
            WidgetsBinding.instance.addPostFrameCallback((_) {
              _showQuotaExceededDialog(context, sessionProvider);
            });
          }
          // Don't show the banner for quota errors - the dialog handles it
          return const SizedBox.shrink();
        }
        
        if (message == null) {
          _quotaDialogShown = false; // Reset when error clears
          return const SizedBox.shrink();
        }

        Future<void> handleDismiss() async {
          if (sessionError != null) {
            session.dismissError();
          } else {
            await sessionProvider.disconnect();
          }
          setState(() => _quotaDialogShown = false);
        }

        return SafeArea(
          minimum: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 500),
              child: Material(
                elevation: 4,
                borderRadius: BorderRadius.circular(12),
                color: Colors.red.withValues(alpha: 0.9),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline, color: Colors.white),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          message,
                          style: const TextStyle(color: Colors.white),
                        ),
                      ),
                      IconButton(
                        onPressed: handleDismiss,
                        icon: const Icon(Icons.close, color: Colors.white),
                        tooltip: 'Dismiss',
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  void _showQuotaExceededDialog(BuildContext context, SessionProvider sessionProvider) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A2E),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: ZoyaTheme.danger.withValues(alpha: 0.5)),
        ),
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: ZoyaTheme.danger.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.warning_amber_rounded, color: ZoyaTheme.danger, size: 28),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: Text(
                'LiveKit Quota Exceeded',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Your LiveKit Cloud free tier has exceeded its monthly connection minutes.',
              style: TextStyle(color: Colors.white70, fontSize: 14),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.black26,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.white10),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('💡 Solutions:', style: TextStyle(color: ZoyaTheme.accent, fontWeight: FontWeight.bold)),
                  SizedBox(height: 8),
                  Text('1. Create a new LiveKit Cloud project', style: TextStyle(color: Colors.white60, fontSize: 12)),
                  Text('2. Wait for monthly quota reset', style: TextStyle(color: Colors.white60, fontSize: 12)),
                  Text('3. Upgrade to a paid LiveKit plan', style: TextStyle(color: Colors.white60, fontSize: 12)),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              sessionProvider.disconnect();
            },
            child: const Text('Dismiss', style: TextStyle(color: Colors.white54)),
          ),
          ElevatedButton.icon(
            onPressed: () async {
              final uri = Uri.parse('https://cloud.livekit.io');
              if (await canLaunchUrl(uri)) {
                await launchUrl(uri);
              }
            },
            icon: const Icon(Icons.open_in_new, size: 16),
            label: const Text('Open LiveKit Dashboard'),
            style: ElevatedButton.styleFrom(
              backgroundColor: ZoyaTheme.accent,
              foregroundColor: Colors.black,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          ),
        ],
      ),
    );
  }
}
