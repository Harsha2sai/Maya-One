import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../state/controllers/agent_activity_controller.dart';
import '../../../state/controllers/workspace_controller.dart';
import '../../../state/models/workspace_models.dart';
import '../../../ui/theme/app_theme.dart';
import 'task_ui_utils.dart';

class TaskListPanel extends StatelessWidget {
  const TaskListPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final activity = context.watch<AgentActivityController>();
    final workspace = context.watch<WorkspaceController>();
    final tasks = activity.tasks;

    if (tasks.isEmpty) {
      return const Center(
        child: Text(
          'No active tasks',
          key: Key('task_list_empty_placeholder'),
          style: TextStyle(color: ZoyaTheme.textMuted),
        ),
      );
    }

    return ListView.separated(
      itemCount: tasks.length,
      separatorBuilder: (_, __) => Divider(color: ZoyaTheme.glassBorder, height: 1),
      itemBuilder: (context, index) {
        final task = tasks[index];
        final state = parseTaskUiState(task.status);
        final isSelected = workspace.selectedTaskId == task.id;
        final isLoadingState = task.status.trim().isEmpty;

        return ListTile(
          key: Key('task_row_${task.id}'),
          selected: isSelected,
          selectedTileColor: ZoyaTheme.accent.withValues(alpha: 0.10),
          title: Text(
            task.name.isEmpty ? task.id : task.name,
            style: const TextStyle(color: ZoyaTheme.textMain, fontWeight: FontWeight.w600),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          subtitle: Row(
            children: [
              _TaskStateChip(
                state: state,
                showLoading: isLoadingState,
              ),
              if (state == TaskUiState.running) ...[
                const SizedBox(width: 8),
                Text(
                  _formatElapsed(task.startTime),
                  style: const TextStyle(color: ZoyaTheme.textMuted, fontSize: 12),
                ),
              ],
            ],
          ),
          onTap: () {
            workspace.selectTask(task.id);
            workspace.selectArtifact(
              WorkbenchArtifactRef(
                id: task.id,
                type: 'task',
                title: task.name,
                taskId: task.id,
              ),
            );
          },
        );
      },
    );
  }
}

class _TaskStateChip extends StatelessWidget {
  final TaskUiState state;
  final bool showLoading;

  const _TaskStateChip({
    required this.state,
    required this.showLoading,
  });

  @override
  Widget build(BuildContext context) {
    final Color color;
    switch (state) {
      case TaskUiState.pending:
        color = Colors.blueGrey;
      case TaskUiState.running:
        color = ZoyaTheme.info;
      case TaskUiState.completed:
        color = Colors.green;
      case TaskUiState.failed:
      case TaskUiState.planFailed:
        color = ZoyaTheme.danger;
      case TaskUiState.waitingInput:
        color = ZoyaTheme.warning;
      case TaskUiState.cancelled:
        color = Colors.orange;
    }

    return Container(
      key: Key('task_state_${state.name}'),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.20),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showLoading) ...[
            const SizedBox(
              width: 10,
              height: 10,
              child: CircularProgressIndicator(strokeWidth: 1.8),
            ),
            const SizedBox(width: 6),
          ],
          Text(
            taskUiStateLabel(state),
            style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

String _formatElapsed(DateTime startedAt) {
  final duration = DateTime.now().difference(startedAt);
  if (duration.inHours > 0) {
    return '${duration.inHours}h ${duration.inMinutes.remainder(60)}m';
  }
  if (duration.inMinutes > 0) {
    return '${duration.inMinutes}m ${duration.inSeconds.remainder(60)}s';
  }
  return '${duration.inSeconds}s';
}
