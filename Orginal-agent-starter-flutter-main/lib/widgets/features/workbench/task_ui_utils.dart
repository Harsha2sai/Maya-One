import '../../../state/models/workspace_models.dart';

TaskUiState parseTaskUiState(String? rawStatus) {
  final normalized = (rawStatus ?? '').trim().toLowerCase();
  switch (normalized) {
    case 'pending':
    case 'queued':
      return TaskUiState.pending;
    case 'running':
    case 'in_progress':
    case 'started':
      return TaskUiState.running;
    case 'completed':
    case 'finished':
    case 'success':
      return TaskUiState.completed;
    case 'failed':
    case 'error':
      return TaskUiState.failed;
    case 'planfailed':
    case 'plan_failed':
      return TaskUiState.planFailed;
    case 'waiting_input':
    case 'waiting':
      return TaskUiState.waitingInput;
    case 'cancelled':
    case 'canceled':
      return TaskUiState.cancelled;
    default:
      return TaskUiState.pending;
  }
}

String taskUiStateLabel(TaskUiState state) {
  switch (state) {
    case TaskUiState.pending:
      return 'Pending';
    case TaskUiState.running:
      return 'Running';
    case TaskUiState.completed:
      return 'Completed';
    case TaskUiState.failed:
      return 'Failed';
    case TaskUiState.planFailed:
      return 'Plan failed';
    case TaskUiState.waitingInput:
      return 'Waiting input';
    case TaskUiState.cancelled:
      return 'Cancelled';
  }
}
