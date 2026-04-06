import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../state/controllers/agent_activity_controller.dart';
import '../../../state/controllers/workspace_controller.dart';
import '../../../state/models/workspace_models.dart';
import '../../../ui/theme/app_theme.dart';
import 'task_ui_utils.dart';

class PlanTimelinePanel extends StatelessWidget {
  const PlanTimelinePanel({super.key});

  @override
  Widget build(BuildContext context) {
    final workspace = context.watch<WorkspaceController>();
    final activity = context.watch<AgentActivityController>();
    final selectedTaskId = workspace.selectedTaskId;

    if (selectedTaskId == null) {
      return const Center(
        child: Text(
          'Select a task to see its plan',
          key: Key('timeline_no_task_selected'),
          style: TextStyle(color: ZoyaTheme.textMuted),
        ),
      );
    }

    AgentTask? task;
    for (final item in activity.tasks) {
      if (item.id == selectedTaskId) {
        task = item;
        break;
      }
    }
    if (task == null) {
      return const Center(
        child: Text(
          'Select a task to see its plan',
          style: TextStyle(color: ZoyaTheme.textMuted),
        ),
      );
    }

    final state = parseTaskUiState(task.status);
    final items = _buildSyntheticSteps(task.name, state);

    return ListView.separated(
      itemCount: items.length,
      separatorBuilder: (_, __) => Divider(color: ZoyaTheme.glassBorder, height: 1),
      itemBuilder: (context, index) {
        final item = items[index];
        return ListTile(
          key: Key('timeline_step_$index'),
          leading: _StepIcon(
            state: item.state,
            isCurrent: item.isCurrent,
          ),
          title: Text(
            item.title,
            style: TextStyle(
              color: ZoyaTheme.textMain,
              fontWeight: item.isCurrent ? FontWeight.w700 : FontWeight.w500,
            ),
          ),
          subtitle: Text(
            taskUiStateLabel(item.state),
            style: TextStyle(
              color: item.state == TaskUiState.failed || item.state == TaskUiState.planFailed
                  ? ZoyaTheme.danger
                  : ZoyaTheme.textMuted,
            ),
          ),
        );
      },
    );
  }
}

class _TimelineItem {
  final String title;
  final TaskUiState state;
  final bool isCurrent;

  const _TimelineItem({
    required this.title,
    required this.state,
    required this.isCurrent,
  });
}

List<_TimelineItem> _buildSyntheticSteps(String taskName, TaskUiState state) {
  final steps = <_TimelineItem>[
    const _TimelineItem(title: 'Plan', state: TaskUiState.completed, isCurrent: false),
    const _TimelineItem(title: 'Execute', state: TaskUiState.running, isCurrent: true),
    const _TimelineItem(title: 'Finalize', state: TaskUiState.pending, isCurrent: false),
  ];

  if (state == TaskUiState.completed) {
    return const <_TimelineItem>[
      _TimelineItem(title: 'Plan', state: TaskUiState.completed, isCurrent: false),
      _TimelineItem(title: 'Execute', state: TaskUiState.completed, isCurrent: false),
      _TimelineItem(title: 'Finalize', state: TaskUiState.completed, isCurrent: false),
    ];
  }
  if (state == TaskUiState.failed || state == TaskUiState.planFailed) {
    return <_TimelineItem>[
      const _TimelineItem(title: 'Plan', state: TaskUiState.completed, isCurrent: false),
      _TimelineItem(
        title: taskName.isEmpty ? 'Execute' : taskName,
        state: state,
        isCurrent: true,
      ),
      const _TimelineItem(title: 'Finalize', state: TaskUiState.pending, isCurrent: false),
    ];
  }
  if (state == TaskUiState.waitingInput) {
    return const <_TimelineItem>[
      _TimelineItem(title: 'Plan', state: TaskUiState.completed, isCurrent: false),
      _TimelineItem(title: 'Waiting for input', state: TaskUiState.waitingInput, isCurrent: true),
      _TimelineItem(title: 'Finalize', state: TaskUiState.pending, isCurrent: false),
    ];
  }
  if (state == TaskUiState.cancelled) {
    return const <_TimelineItem>[
      _TimelineItem(title: 'Plan', state: TaskUiState.completed, isCurrent: false),
      _TimelineItem(title: 'Execute', state: TaskUiState.cancelled, isCurrent: false),
      _TimelineItem(title: 'Finalize', state: TaskUiState.cancelled, isCurrent: false),
    ];
  }
  return steps;
}

class _StepIcon extends StatelessWidget {
  final TaskUiState state;
  final bool isCurrent;

  const _StepIcon({
    required this.state,
    required this.isCurrent,
  });

  @override
  Widget build(BuildContext context) {
    if (state == TaskUiState.completed) {
      return const Icon(Icons.check_circle, color: Colors.green);
    }
    if (state == TaskUiState.failed || state == TaskUiState.planFailed) {
      return const Icon(Icons.error, key: Key('timeline_failed_indicator'), color: ZoyaTheme.danger);
    }
    if (isCurrent) {
      return const Icon(Icons.radio_button_checked, key: Key('timeline_current_step'), color: ZoyaTheme.info);
    }
    return const Icon(Icons.radio_button_unchecked, color: ZoyaTheme.textMuted);
  }
}
