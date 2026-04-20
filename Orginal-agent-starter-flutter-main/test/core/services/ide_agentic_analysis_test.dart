import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/services/ide_agentic_analysis.dart';
import 'package:voice_assistant/core/services/ide_agentic_service.dart';

IdeAgenticEvent _event(
  int seq,
  String eventType, {
  String? taskId,
  String? traceId,
  String? status,
  String? agentId,
  Map<String, dynamic>? payload,
}) {
  return IdeAgenticEvent(
    seq: seq,
    eventType: eventType,
    timestamp: seq.toDouble(),
    taskId: taskId,
    traceId: traceId,
    status: status,
    agentId: agentId,
    payload: payload ?? const <String, dynamic>{},
  );
}

void main() {
  group('deriveAgenticAnalysis', () {
    test('dedupes by seq (first seen wins) and sorts ascending', () {
      final snapshot = deriveAgenticAnalysis(<IdeAgenticEvent>[
        _event(5, 'task_started', taskId: 'task-a', traceId: 'trace-1'),
        _event(2, 'task_step', taskId: 'task-a', traceId: 'trace-1'),
        _event(5, 'task_failed', taskId: 'task-a', traceId: 'trace-1'),
      ]);

      expect(snapshot.orderedEvents.map((e) => e.seq).toList(), <int>[2, 5]);
      expect(snapshot.orderedEvents.last.eventType, 'task_started');
    });

    test('resolves task status from terminal task events', () {
      final snapshot = deriveAgenticAnalysis(<IdeAgenticEvent>[
        _event(1, 'task_started', taskId: 'task-success'),
        _event(2, 'task_step', taskId: 'task-success'),
        _event(3, 'task_finished', taskId: 'task-success'),
        _event(10, 'task_started', taskId: 'task-fail'),
        _event(11, 'task_failed', taskId: 'task-fail'),
      ]);

      final byTask = <String, AgenticTaskSummary>{
        for (final task in snapshot.taskSummaries) task.taskId: task,
      };

      expect(byTask['task-success']?.status, 'completed');
      expect(byTask['task-fail']?.status, 'failed');
    });

    test('groups trace correlation by trace_id and excludes missing trace', () {
      final snapshot = deriveAgenticAnalysis(<IdeAgenticEvent>[
        _event(1, 'task_started', taskId: 'a', traceId: 'trace-1'),
        _event(2, 'task_step', taskId: 'a', traceId: 'trace-1'),
        _event(3, 'task_started', taskId: 'b', traceId: 'trace-2'),
        _event(4, 'task_step', taskId: 'none'),
      ]);

      expect(snapshot.tracesById.keys.toSet(), <String>{'trace-1', 'trace-2'});
      expect(snapshot.tracesById['trace-1']?.events.length, 2);
      expect(snapshot.tracesById['trace-2']?.events.length, 1);
    });

    test('builds dependency edges using terminal marker and latest-seq fallback', () {
      final snapshot = deriveAgenticAnalysis(<IdeAgenticEvent>[
        _event(1, 'task_started', taskId: 'task-a', traceId: 'trace-1'),
        _event(2, 'tool_started', taskId: 'task-a', traceId: 'trace-1', payload: <String, dynamic>{'tool': 'search'}),
        _event(3, 'tool_finished', taskId: 'task-a', traceId: 'trace-1', payload: <String, dynamic>{'tool': 'search'}),
        _event(4, 'task_finished', taskId: 'task-a', traceId: 'trace-1'),
        _event(5, 'task_started', taskId: 'task-b', traceId: 'trace-1'),
        _event(10, 'task_started', taskId: 'task-x', traceId: 'trace-2'),
        _event(11, 'task_step', taskId: 'task-x', traceId: 'trace-2'),
        _event(12, 'task_started', taskId: 'task-y', traceId: 'trace-2'),
      ]);

      final edges = snapshot.graph.edges.map((edge) => '${edge.fromNodeId}->${edge.toNodeId}:${edge.kind}').toSet();

      expect(edges.contains('task:task-a->tool:task-a:search:uses_tool'), isTrue);
      expect(edges.contains('task:task-a->task:task-b:depends_on'), isTrue);
      expect(edges.contains('task:task-x->task:task-y:depends_on'), isTrue);
    });

    test('enforces 100-node cap and trims oldest tool nodes first', () {
      final events = <IdeAgenticEvent>[];
      var seq = 1;
      for (var i = 0; i < 60; i++) {
        events.add(_event(seq++, 'task_started', taskId: 'task-$i', traceId: 'trace-main'));
        events.add(
          _event(
            seq++,
            'tool_started',
            taskId: 'task-$i',
            traceId: 'trace-main',
            payload: <String, dynamic>{'tool': 'tool-$i'},
          ),
        );
      }

      final snapshot = deriveAgenticAnalysis(events, maxGraphNodes: 100);
      final nodeIds = snapshot.graph.nodes.map((node) => node.id).toSet();

      expect(snapshot.graph.truncated, isTrue);
      expect(snapshot.graph.droppedNodes, 20);
      expect(snapshot.graph.nodes.length, 100);

      expect(nodeIds.contains('task:task-0'), isTrue);
      expect(nodeIds.contains('tool:task-0:tool-0'), isFalse);
      expect(nodeIds.contains('tool:task-59:tool-59'), isTrue);
    });
  });
}
