import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../state/providers/chat_provider.dart';
import '../../../state/controllers/workspace_controller.dart';
import '../../../state/models/workspace_models.dart';
import '../../../state/controllers/conversation_controller.dart';
import '../../../state/controllers/overlay_controller.dart';
import '../../../ui/zoya_theme.dart';
import 'source_cards_panel.dart';

class ResearchResultBubble extends StatelessWidget {
  final String summary;
  final List<Source> sources;
  final String traceId;

  const ResearchResultBubble({
    super.key,
    required this.summary,
    required this.sources,
    required this.traceId,
  });

  String _cleanLine(String line) {
    var cleaned = line.trim();
    if (cleaned.startsWith('**') && cleaned.endsWith('**') && cleaned.length >= 4) {
      cleaned = cleaned.substring(2, cleaned.length - 2).trim();
    } else {
      cleaned = cleaned.replaceAll('**', '').trim();
    }
    cleaned = cleaned.replaceFirst(RegExp(r'^[\-\*\u2022◆🔹✅🚀]+\s*'), '').trim();
    return cleaned;
  }

  @override
  Widget build(BuildContext context) {
    final lines = summary
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList();
    final header = lines.isNotEmpty ? _cleanLine(lines.first) : 'Research Results';
    final bodyLines = lines.length > 1 ? lines.sublist(1) : <String>[];
    final sourceLineIndex =
        bodyLines.lastIndexWhere((line) => line.toLowerCase().startsWith('sources:'));
    String? sourceText;
    if (sourceLineIndex >= 0) {
      sourceText = bodyLines[sourceLineIndex];
      bodyLines.removeAt(sourceLineIndex);
    }

    return Container(
      key: const Key('research_result_bubble'),
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ZoyaTheme.glassBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: ZoyaTheme.glassBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SelectableText(
            header,
            style: ZoyaTheme.fontBody.copyWith(
              color: ZoyaTheme.textMain,
              fontSize: 16,
              fontWeight: FontWeight.w700,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 10),
          ...bodyLines.map((line) {
            final bulletText = _cleanLine(line);
            if (bulletText.isEmpty) {
              return const SizedBox.shrink();
            }
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '◆ ',
                    style: ZoyaTheme.fontBody.copyWith(
                      color: ZoyaTheme.accent,
                      fontSize: 15,
                      height: 1.5,
                    ),
                  ),
                  Expanded(
                    child: SelectableText(
                      bulletText,
                      style: ZoyaTheme.fontBody.copyWith(
                        color: ZoyaTheme.textMain,
                        fontSize: 15,
                        height: 1.5,
                      ),
                    ),
                  ),
                ],
              ),
            );
          }),
          if (sourceText != null && sources.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: SelectableText(
                sourceText,
                style: ZoyaTheme.fontBody.copyWith(
                  color: ZoyaTheme.textMuted,
                  fontSize: 13,
                  height: 1.4,
                ),
              ),
            ),
          SourceCardsPanel(sources: sources),
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: () {
              context.read<ConversationController>().selectResearchArtifact(traceId);
              final workspace = context.read<WorkspaceController>();
              final overlay = context.read<OverlayController>();
              workspace.selectWorkbenchTab(WorkbenchTab.research);
              if (workspace.layoutMode == WorkspaceLayoutMode.compact) {
                overlay.setCompactWorkbenchSheetOpen(true);
              } else if (workspace.workbenchCollapsed) {
                workspace.setWorkbenchCollapsed(false);
              }
            },
            icon: const Icon(Icons.open_in_new, size: 16),
            label: const Text('View Deep Dive'),
            style: ElevatedButton.styleFrom(
              backgroundColor: ZoyaTheme.accent.withValues(alpha: 0.1),
              foregroundColor: ZoyaTheme.accent,
              elevation: 0,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          ),
        ],
      ),
    );
  }
}
