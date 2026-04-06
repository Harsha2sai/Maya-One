import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../state/controllers/overlay_controller.dart';
import '../../state/controllers/workspace_controller.dart';
import '../../state/models/workspace_models.dart';
import '../../state/providers/session_provider.dart';
import '../../widgets/features/chat/system_action_bubble.dart';
import '../../widgets/features/chat/media_result_bubble.dart';
import '../../widgets/features/chat/confirmation_card.dart';
import '../../widgets/features/workbench/workbench_pane.dart';
import '../../ui/zoya_theme.dart';

class GlobalOverlayHost extends StatelessWidget {
  final Widget child;

  const GlobalOverlayHost({super.key, required this.child});

  void _sendConfirmationResponse({
    required SessionProvider session,
    required String traceId,
    required bool confirmed,
  }) {
    unawaited(
      session.sendConfirmationResponse(
        traceId: traceId,
        confirmed: confirmed,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        child,
        Consumer2<OverlayController, SessionProvider>(
          builder: (context, controller, session, _) {
            final systemToast = controller.systemActionToast;
            final mediaToast = controller.mediaResultToast;
            final confirmation = controller.pendingConfirmation;
            final workspace = context.watch<WorkspaceController?>();
            final layoutMode = workspace?.layoutMode ?? WorkspaceLayoutMode.medium;
            final currentPage = workspace?.currentPage ?? 'home';
            final showWorkbenchOverlay = controller.compactWorkbenchSheetOpen && currentPage == 'home';
            final showCompactWorkbenchSheet =
                showWorkbenchOverlay && layoutMode == WorkspaceLayoutMode.compact;
            final showReconnectPrompt = controller.isReconnectPromptVisible &&
                session.connectionState != SessionConnectionState.connected;
            final reconnecting = session.connectionState == SessionConnectionState.reconnecting;

            return Stack(
              children: [
                if (showCompactWorkbenchSheet)
                  Positioned.fill(
                    key: const Key('global_overlay_compact_workbench_sheet'),
                    child: Container(
                      color: Colors.black.withValues(alpha: 0.24),
                      alignment: Alignment.bottomCenter,
                      child: SizedBox(
                        height: MediaQuery.of(context).size.height * 0.8,
                        width: double.infinity,
                        child: Material(
                          color: Colors.transparent,
                          child: WorkbenchPane(key: workbenchPaneKey),
                        ),
                      ),
                    ),
                  ),
                if (showReconnectPrompt)
                  Positioned(
                    top: 24,
                    left: 0,
                    right: 0,
                    child: Center(
                      child: Container(
                        constraints: const BoxConstraints(maxWidth: 520),
                        margin: const EdgeInsets.symmetric(horizontal: 16),
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: ZoyaTheme.sidebarBg.withValues(alpha: 0.92),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                            color: reconnecting
                                ? Colors.orangeAccent.withValues(alpha: 0.35)
                                : ZoyaTheme.danger.withValues(alpha: 0.35),
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              reconnecting ? Icons.sync : Icons.wifi_off_rounded,
                              color: reconnecting ? Colors.orangeAccent : ZoyaTheme.danger,
                              size: 18,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                reconnecting
                                    ? 'Reconnecting to Maya session...'
                                    : 'Disconnected from Maya session.',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 13,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                            const SizedBox(width: 10),
                            TextButton(
                              onPressed: reconnecting
                                  ? null
                                  : () {
                                      unawaited(
                                        session.reconnectWithMetadata(
                                          userId: session.currentUserId,
                                        ),
                                      );
                                    },
                              child: Text(reconnecting ? 'Working...' : 'Reconnect'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                if (systemToast != null)
                  Positioned(
                    top: 24,
                    left: 0,
                    right: 0,
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 600),
                          child: SystemActionBubble(
                            actionType: systemToast.actionType,
                            message: systemToast.message,
                            detail: systemToast.detail,
                            success: systemToast.success,
                            rollbackAvailable: systemToast.rollbackAvailable,
                            onDismiss: () => controller.clearSystemActionToast(),
                          ),
                        ),
                      ),
                    ),
                  ),
                if (mediaToast != null)
                  Positioned(
                    top: 24,
                    left: 0,
                    right: 0,
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 600),
                          child: MediaResultBubble(
                            trackName: mediaToast.trackName,
                            provider: mediaToast.provider,
                            statusText: mediaToast.statusText,
                            artist: mediaToast.artist,
                            albumArtUrl: mediaToast.albumArtUrl,
                            onDismiss: () => controller.clearMediaResultToast(),
                          ),
                        ),
                      ),
                    ),
                  ),
                if (confirmation != null)
                  Positioned.fill(
                    child: Container(
                      color: ZoyaTheme.mainBg.withValues(alpha: 0.75),
                      alignment: Alignment.center,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 400),
                          child: ConfirmationCard(
                            actionType: confirmation.actionType,
                            description: confirmation.description,
                            destructive: confirmation.destructive,
                            timeoutSeconds: confirmation.timeoutSeconds,
                            onRespond: (confirmed) {
                              _sendConfirmationResponse(
                                session: session,
                                traceId: confirmation.traceId,
                                confirmed: confirmed,
                              );
                              controller.clearConfirmationPrompt();
                            },
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}
