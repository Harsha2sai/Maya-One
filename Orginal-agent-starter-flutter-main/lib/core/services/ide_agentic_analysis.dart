import 'ide_agentic_service.dart';

const String kUnscopedTaskId = 'unscoped-task';

class AgenticTaskSummary {
  const AgenticTaskSummary({
    required this.taskId,
    required this.status,
    required this.firstSeq,
    required this.lastSeq,
    required this.eventCount,
    required this.latestEventType,
    this.traceId,
  });

  final String taskId;
  final String status;
  final int firstSeq;
  final int lastSeq;
  final int eventCount;
  final String latestEventType;
  final String? traceId;
}

class AgenticTraceGroup {
  const AgenticTraceGroup({
    required this.traceId,
    required this.events,
  });

  final String traceId;
  final List<IdeAgenticEvent> events;
}

enum AgenticGraphNodeType { task, tool }

class AgenticGraphNode {
  const AgenticGraphNode({
    required this.id,
    required this.label,
    required this.type,
    required this.firstSeq,
    required this.lastSeq,
  });

  final String id;
  final String label;
  final AgenticGraphNodeType type;
  final int firstSeq;
  final int lastSeq;
}

class AgenticGraphEdge {
  const AgenticGraphEdge({
    required this.fromNodeId,
    required this.toNodeId,
    required this.kind,
  });

  final String fromNodeId;
  final String toNodeId;
  final String kind;
}

class AgenticGraphSnapshot {
  const AgenticGraphSnapshot({
    required this.nodes,
    required this.edges,
    required this.truncated,
    required this.droppedNodes,
  });

  final List<AgenticGraphNode> nodes;
  final List<AgenticGraphEdge> edges;
  final bool truncated;
  final int droppedNodes;
}

class AgenticAnalysisSnapshot {
  const AgenticAnalysisSnapshot({
    required this.orderedEvents,
    required this.eventsByTask,
    required this.taskSummaries,
    required this.tracesById,
    required this.graph,
  });

  final List<IdeAgenticEvent> orderedEvents;
  final Map<String, List<IdeAgenticEvent>> eventsByTask;
  final List<AgenticTaskSummary> taskSummaries;
  final Map<String, AgenticTraceGroup> tracesById;
  final AgenticGraphSnapshot graph;
}

AgenticAnalysisSnapshot deriveAgenticAnalysis(
  List<IdeAgenticEvent> rawEvents, {
  int maxGraphNodes = 100,
}) {
  final dedupedBySeq = <int, IdeAgenticEvent>{};
  for (final event in rawEvents) {
    dedupedBySeq.putIfAbsent(event.seq, () => event);
  }

  final orderedEvents = dedupedBySeq.values.toList(growable: false)..sort((a, b) => a.seq.compareTo(b.seq));

  final eventsByTask = <String, List<IdeAgenticEvent>>{};
  final tracesById = <String, List<IdeAgenticEvent>>{};

  for (final event in orderedEvents) {
    final taskKey = _normalizeTaskId(event.taskId);
    eventsByTask.putIfAbsent(taskKey, () => <IdeAgenticEvent>[]).add(event);

    final traceKey = _normalizeTraceId(event.traceId);
    if (traceKey != null) {
      tracesById.putIfAbsent(traceKey, () => <IdeAgenticEvent>[]).add(event);
    }
  }

  final taskSummaries =
      eventsByTask.entries.map((entry) => _toTaskSummary(entry.key, entry.value)).toList(growable: false)
        ..sort((a, b) {
          final seqCompare = b.lastSeq.compareTo(a.lastSeq);
          if (seqCompare != 0) return seqCompare;
          return a.taskId.compareTo(b.taskId);
        });

  final normalizedTraceGroups = <String, AgenticTraceGroup>{};
  for (final entry in tracesById.entries) {
    final events = List<IdeAgenticEvent>.from(entry.value)..sort((a, b) => a.seq.compareTo(b.seq));
    normalizedTraceGroups[entry.key] = AgenticTraceGroup(
      traceId: entry.key,
      events: events,
    );
  }

  final graph = _buildGraph(
    taskSummaries: taskSummaries,
    eventsByTask: eventsByTask,
    traceGroups: normalizedTraceGroups,
    maxGraphNodes: maxGraphNodes,
  );

  return AgenticAnalysisSnapshot(
    orderedEvents: orderedEvents,
    eventsByTask: eventsByTask,
    taskSummaries: taskSummaries,
    tracesById: normalizedTraceGroups,
    graph: graph,
  );
}

AgenticTaskSummary _toTaskSummary(String taskId, List<IdeAgenticEvent> events) {
  final sorted = List<IdeAgenticEvent>.from(events)..sort((a, b) => a.seq.compareTo(b.seq));
  final first = sorted.first;
  final last = sorted.last;
  final status = _deriveTaskStatus(sorted);

  String? traceId;
  for (final event in sorted.reversed) {
    final candidate = _normalizeTraceId(event.traceId);
    if (candidate != null) {
      traceId = candidate;
      break;
    }
  }

  return AgenticTaskSummary(
    taskId: taskId,
    status: status,
    firstSeq: first.seq,
    lastSeq: last.seq,
    eventCount: sorted.length,
    latestEventType: last.eventType,
    traceId: traceId,
  );
}

String _deriveTaskStatus(List<IdeAgenticEvent> events) {
  for (final event in events.reversed) {
    final normalizedType = event.eventType.trim().toLowerCase();
    if (normalizedType == 'task_failed') {
      return 'failed';
    }
    if (normalizedType == 'task_finished') {
      return 'completed';
    }
  }
  return 'running';
}

String _normalizeTaskId(String? rawTaskId) {
  final taskId = rawTaskId?.trim() ?? '';
  if (taskId.isEmpty) return kUnscopedTaskId;
  return taskId;
}

String? _normalizeTraceId(String? rawTraceId) {
  final traceId = rawTraceId?.trim() ?? '';
  if (traceId.isEmpty) return null;
  return traceId;
}

AgenticGraphSnapshot _buildGraph({
  required List<AgenticTaskSummary> taskSummaries,
  required Map<String, List<IdeAgenticEvent>> eventsByTask,
  required Map<String, AgenticTraceGroup> traceGroups,
  required int maxGraphNodes,
}) {
  final nodes = <String, AgenticGraphNode>{};
  final edges = <String, AgenticGraphEdge>{};

  for (final task in taskSummaries) {
    final taskNodeId = _taskNodeId(task.taskId);
    nodes[taskNodeId] = AgenticGraphNode(
      id: taskNodeId,
      label: task.taskId,
      type: AgenticGraphNodeType.task,
      firstSeq: task.firstSeq,
      lastSeq: task.lastSeq,
    );

    final taskEvents = eventsByTask[task.taskId] ?? const <IdeAgenticEvent>[];
    for (final event in taskEvents) {
      final type = event.eventType.trim().toLowerCase();
      if (type != 'tool_started' && type != 'tool_finished') {
        continue;
      }
      final toolName = _extractToolName(event.payload);
      final toolNodeId = _toolNodeId(task.taskId, toolName);
      final existingToolNode = nodes[toolNodeId];
      if (existingToolNode == null) {
        nodes[toolNodeId] = AgenticGraphNode(
          id: toolNodeId,
          label: toolName,
          type: AgenticGraphNodeType.tool,
          firstSeq: event.seq,
          lastSeq: event.seq,
        );
      } else {
        nodes[toolNodeId] = AgenticGraphNode(
          id: existingToolNode.id,
          label: existingToolNode.label,
          type: existingToolNode.type,
          firstSeq: existingToolNode.firstSeq < event.seq ? existingToolNode.firstSeq : event.seq,
          lastSeq: existingToolNode.lastSeq > event.seq ? existingToolNode.lastSeq : event.seq,
        );
      }

      final edgeKey = '$taskNodeId->$toolNodeId:uses_tool';
      edges.putIfAbsent(
        edgeKey,
        () => AgenticGraphEdge(
          fromNodeId: taskNodeId,
          toNodeId: toolNodeId,
          kind: 'uses_tool',
        ),
      );
    }
  }

  for (final traceGroup in traceGroups.values) {
    final taskBounds = <String, _TaskTraceBounds>{};
    for (final event in traceGroup.events) {
      final taskId = _normalizeTaskId(event.taskId);
      final current = taskBounds[taskId];
      final normalizedType = event.eventType.trim().toLowerCase();
      final isTerminal = normalizedType == 'task_finished' || normalizedType == 'task_failed';
      if (current == null) {
        taskBounds[taskId] = _TaskTraceBounds(
          taskId: taskId,
          startSeq: event.seq,
          latestSeq: event.seq,
          terminalSeq: isTerminal ? event.seq : null,
        );
      } else {
        taskBounds[taskId] = _TaskTraceBounds(
          taskId: current.taskId,
          startSeq: current.startSeq < event.seq ? current.startSeq : event.seq,
          latestSeq: current.latestSeq > event.seq ? current.latestSeq : event.seq,
          terminalSeq: isTerminal
              ? ((current.terminalSeq == null || event.seq > current.terminalSeq!) ? event.seq : current.terminalSeq)
              : current.terminalSeq,
        );
      }
    }

    final orderedTasks = taskBounds.values.toList(growable: false)
      ..sort((a, b) {
        final startCompare = a.startSeq.compareTo(b.startSeq);
        if (startCompare != 0) return startCompare;
        return a.taskId.compareTo(b.taskId);
      });

    for (var i = 0; i < orderedTasks.length; i++) {
      final source = orderedTasks[i];
      final sourceEnd = source.terminalSeq ?? source.latestSeq;
      for (var j = i + 1; j < orderedTasks.length; j++) {
        final target = orderedTasks[j];
        if (target.startSeq <= sourceEnd) {
          continue;
        }
        final fromNodeId = _taskNodeId(source.taskId);
        final toNodeId = _taskNodeId(target.taskId);
        final edgeKey = '$fromNodeId->$toNodeId:depends_on';
        edges.putIfAbsent(
          edgeKey,
          () => AgenticGraphEdge(
            fromNodeId: fromNodeId,
            toNodeId: toNodeId,
            kind: 'depends_on',
          ),
        );
      }
    }
  }

  final allNodes = nodes.values.toList(growable: false)
    ..sort((a, b) {
      if (a.firstSeq != b.firstSeq) {
        return a.firstSeq.compareTo(b.firstSeq);
      }
      return a.id.compareTo(b.id);
    });

  final normalizedCap = maxGraphNodes < 1 ? 1 : maxGraphNodes;
  final keepIds = allNodes.map((node) => node.id).toSet();
  var droppedNodes = 0;

  if (allNodes.length > normalizedCap) {
    final toDropCount = allNodes.length - normalizedCap;
    droppedNodes = toDropCount;

    final sortedTools = allNodes.where((node) => node.type == AgenticGraphNodeType.tool).toList(growable: false)
      ..sort((a, b) {
        if (a.lastSeq != b.lastSeq) {
          return a.lastSeq.compareTo(b.lastSeq);
        }
        return a.id.compareTo(b.id);
      });

    final sortedTasks = allNodes.where((node) => node.type == AgenticGraphNodeType.task).toList(growable: false)
      ..sort((a, b) {
        if (a.lastSeq != b.lastSeq) {
          return a.lastSeq.compareTo(b.lastSeq);
        }
        return a.id.compareTo(b.id);
      });

    var remaining = toDropCount;
    for (final node in <AgenticGraphNode>[...sortedTools, ...sortedTasks]) {
      if (remaining <= 0) break;
      if (keepIds.remove(node.id)) {
        remaining -= 1;
      }
    }
  }

  final keptNodes = allNodes.where((node) => keepIds.contains(node.id)).toList(growable: false)
    ..sort((a, b) {
      if (a.type != b.type) {
        return a.type.index.compareTo(b.type.index);
      }
      if (a.lastSeq != b.lastSeq) {
        return b.lastSeq.compareTo(a.lastSeq);
      }
      return a.id.compareTo(b.id);
    });

  final keptEdges = edges.values
      .where((edge) => keepIds.contains(edge.fromNodeId) && keepIds.contains(edge.toNodeId))
      .toList(growable: false)
    ..sort((a, b) {
      final fromCompare = a.fromNodeId.compareTo(b.fromNodeId);
      if (fromCompare != 0) return fromCompare;
      final toCompare = a.toNodeId.compareTo(b.toNodeId);
      if (toCompare != 0) return toCompare;
      return a.kind.compareTo(b.kind);
    });

  return AgenticGraphSnapshot(
    nodes: keptNodes,
    edges: keptEdges,
    truncated: droppedNodes > 0,
    droppedNodes: droppedNodes,
  );
}

String _taskNodeId(String taskId) => 'task:$taskId';

String _toolNodeId(String taskId, String toolName) => 'tool:$taskId:$toolName';

String _extractToolName(Map<String, dynamic> payload) {
  const keys = <String>['tool', 'tool_name', 'toolName', 'name'];
  for (final key in keys) {
    final value = payload[key];
    final text = value?.toString().trim() ?? '';
    if (text.isNotEmpty) {
      return text;
    }
  }
  return 'unknown_tool';
}

class _TaskTraceBounds {
  const _TaskTraceBounds({
    required this.taskId,
    required this.startSeq,
    required this.latestSeq,
    required this.terminalSeq,
  });

  final String taskId;
  final int startSeq;
  final int latestSeq;
  final int? terminalSeq;
}
