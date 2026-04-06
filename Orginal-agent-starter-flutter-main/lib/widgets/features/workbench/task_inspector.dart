import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../state/controllers/agent_activity_controller.dart';
import '../../../state/controllers/conversation_controller.dart';
import '../../../state/controllers/workspace_controller.dart';
import '../../../state/models/workspace_models.dart';
import '../../../ui/theme/app_theme.dart';
import 'task_ui_utils.dart';

class TaskInspector extends StatelessWidget {
  const TaskInspector({super.key});

  @override
  Widget build(BuildContext context) {
    final workspace = context.watch<WorkspaceController>();
    final activity = context.watch<AgentActivityController>();
    final conversation = context.watch<ConversationController>();
    final selectedTaskId = workspace.selectedTaskId;

    if (selectedTaskId == null) {
      return const Center(
        child: Text(
          'Select a task to inspect',
          key: Key('task_inspector_no_selection'),
          style: TextStyle(color: ZoyaTheme.textMuted),
        ),
      );
    }

    AgentTask? selectedTask;
    for (final task in activity.tasks) {
      if (task.id == selectedTaskId) {
        selectedTask = task;
        break;
      }
    }
    if (selectedTask == null) {
      return const Center(
        child: Text(
          'Select a task to inspect',
          style: TextStyle(color: ZoyaTheme.textMuted),
        ),
      );
    }

    final state = parseTaskUiState(selectedTask.status);
    final relatedMessages = conversation.taskRelatedMessages(selectedTaskId);
    final originatingMessage = relatedMessages.isNotEmpty ? relatedMessages.first.content : null;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          selectedTask.name.isEmpty ? selectedTask.id : selectedTask.name,
          style: const TextStyle(
            color: ZoyaTheme.textMain,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Status: ${taskUiStateLabel(state)}',
          style: const TextStyle(color: ZoyaTheme.textMuted),
        ),
        const SizedBox(height: 4),
        Text(
          'Started: ${selectedTask.startTime.toIso8601String()}',
          style: const TextStyle(color: ZoyaTheme.textMuted),
        ),
        const SizedBox(height: 16),
        if (originatingMessage != null && originatingMessage.trim().isNotEmpty) ...[
          const Text(
            'Originating message',
            style: TextStyle(color: ZoyaTheme.textMain, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          Text(
            originatingMessage,
            key: const Key('task_inspector_origin_message'),
            style: const TextStyle(color: ZoyaTheme.textMuted),
          ),
          const SizedBox(height: 16),
        ],
        if (state == TaskUiState.failed || state == TaskUiState.planFailed) ...[
          const Text(
            'Error details',
            style: TextStyle(color: ZoyaTheme.danger, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          Text(
            selectedTask.result?.trim().isNotEmpty == true
                ? selectedTask.result!.trim()
                : 'Task failed without a detailed error message.',
            key: const Key('task_inspector_error_detail'),
            style: const TextStyle(color: ZoyaTheme.textMuted),
          ),
          const SizedBox(height: 16),
        ],
      ],
    );
  }
}
