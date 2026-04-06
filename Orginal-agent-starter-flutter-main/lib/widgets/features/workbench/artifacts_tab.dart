import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../state/controllers/conversation_controller.dart';
import '../../../state/controllers/workspace_controller.dart';
import '../../../state/models/workspace_models.dart';
import '../../../ui/theme/app_theme.dart';

class ArtifactsTab extends StatelessWidget {
  const ArtifactsTab({super.key});

  @override
  Widget build(BuildContext context) {
    final conversation = context.watch<ConversationController>();
    final artifacts = conversation.researchArtifacts;

    if (artifacts.isEmpty) {
      return const Center(
        child: Text('No artifacts yet', style: TextStyle(color: ZoyaTheme.textMuted)),
      );
    }

    return ListView.separated(
      itemCount: artifacts.length,
      separatorBuilder: (_, __) => Divider(color: ZoyaTheme.glassBorder, height: 1),
      itemBuilder: (context, index) {
        final artifact = artifacts[artifacts.length - 1 - index];
        return ListTile(
          title: Text(
            artifact.query.isEmpty ? 'Research artifact' : artifact.query,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: ZoyaTheme.textMain),
          ),
          subtitle: Text(
            '${artifact.generatedAt.toIso8601String()} • ${artifact.sources.length} sources',
            style: const TextStyle(color: ZoyaTheme.textMuted, fontSize: 12),
          ),
          onTap: () {
            context.read<ConversationController>().selectResearchArtifact(artifact.traceId);
            context.read<WorkspaceController>().selectArtifact(
                  WorkbenchArtifactRef(
                    id: artifact.traceId,
                    type: 'research',
                    title: artifact.query,
                    taskId: artifact.taskId,
                  ),
                );
            context.read<WorkspaceController>().selectWorkbenchTab(WorkbenchTab.research);
          },
        );
      },
    );
  }
}
