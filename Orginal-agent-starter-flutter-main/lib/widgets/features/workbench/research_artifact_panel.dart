import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../state/controllers/conversation_controller.dart';
import '../../../ui/theme/app_theme.dart';

class ResearchArtifactPanel extends StatelessWidget {
  const ResearchArtifactPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final conversation = context.watch<ConversationController>();
    final artifacts = conversation.researchArtifacts;
    final selected = conversation.selectedResearchArtifact ??
        (artifacts.isNotEmpty ? artifacts.last : null);

    if (selected == null) {
      return const Center(
        child: Text('No research results yet', style: TextStyle(color: ZoyaTheme.textMuted)),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          selected.query.isEmpty ? 'Research result' : selected.query,
          style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 18, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 12),
        Text(
          selected.displaySummary,
          style: const TextStyle(color: ZoyaTheme.textMuted),
        ),
        const SizedBox(height: 16),
        Text(
          'Sources (${selected.sources.length})',
          style: const TextStyle(color: ZoyaTheme.textMain, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        if (selected.sources.isEmpty)
          const Text('No sources attached', style: TextStyle(color: ZoyaTheme.textMuted))
        else
          ...selected.sources.map(
            (source) => ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                source.title.isEmpty ? source.url : source.title,
                style: const TextStyle(color: ZoyaTheme.textMain),
              ),
              subtitle: Text(
                source.url,
                style: const TextStyle(color: ZoyaTheme.textMuted, fontSize: 12),
              ),
              trailing: const Icon(Icons.open_in_new, size: 16, color: ZoyaTheme.textMuted),
              onTap: () async {
                final uri = Uri.tryParse(source.url);
                if (uri != null) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                }
              },
            ),
          ),
      ],
    );
  }
}
