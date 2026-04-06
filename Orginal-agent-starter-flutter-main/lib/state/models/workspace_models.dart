import 'conversation_models.dart';

enum WorkspaceLayoutMode {
  compact,
  medium,
  wide,
}

enum WorkbenchTab {
  agents,
  tasks,
  research,
  logs,
  artifacts,
  memory,
}

enum TaskUiState {
  pending,
  running,
  completed,
  failed,
  planFailed,
  waitingInput,
  cancelled,
}

class WorkbenchArtifactRef {
  final String id;
  final String type;
  final String title;
  final String? conversationId;
  final String? taskId;

  const WorkbenchArtifactRef({
    required this.id,
    required this.type,
    this.title = '',
    this.conversationId,
    this.taskId,
  });
}

class AgentCardModel {
  final String id;
  final String name;
  final String stateSummary;
  final String activeTool;
  final String lastAction;
  final bool isPrimary;

  const AgentCardModel({
    required this.id,
    required this.name,
    this.stateSummary = '',
    this.activeTool = '',
    this.lastAction = '',
    this.isPrimary = false,
  });
}

class TaskStepModel {
  final String id;
  final String title;
  final TaskUiState state;
  final DateTime updatedAt;
  final String detail;

  const TaskStepModel({
    required this.id,
    required this.title,
    required this.state,
    required this.updatedAt,
    this.detail = '',
  });
}

class TaskTimelineModel {
  final String taskId;
  final String summary;
  final TaskUiState state;
  final DateTime startedAt;
  final DateTime updatedAt;
  final String activeTool;
  final String outcomeSummary;
  final String failureReason;
  final List<TaskStepModel> steps;

  const TaskTimelineModel({
    required this.taskId,
    required this.summary,
    required this.state,
    required this.startedAt,
    required this.updatedAt,
    this.activeTool = '',
    this.outcomeSummary = '',
    this.failureReason = '',
    this.steps = const <TaskStepModel>[],
  });
}

class ResearchArtifactModel {
  final int schemaVersion;
  final String traceId;
  final String taskId;
  final String query;
  final String voiceSummary;
  final String displaySummary;
  final List<ConversationSourceItem> citations;
  final List<ConversationSourceItem> sources;
  final double confidence;
  final DateTime generatedAt;

  const ResearchArtifactModel({
    this.schemaVersion = 1,
    required this.traceId,
    required this.taskId,
    required this.query,
    required this.voiceSummary,
    required this.displaySummary,
    this.citations = const <ConversationSourceItem>[],
    this.sources = const <ConversationSourceItem>[],
    this.confidence = 0,
    required this.generatedAt,
  });
}

class ExecutionLogEntry {
  final String id;
  final String level;
  final String message;
  final DateTime timestamp;
  final String? taskId;
  final String? traceId;

  const ExecutionLogEntry({
    required this.id,
    required this.level,
    required this.message,
    required this.timestamp,
    this.taskId,
    this.traceId,
  });
}
