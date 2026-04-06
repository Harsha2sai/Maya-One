import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../../state/controllers/agent_activity_controller.dart';
import '../../../ui/theme/app_theme.dart';

class LogsPanel extends StatelessWidget {
  const LogsPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final logs = context.watch<AgentActivityController>().logs;
    if (logs.isEmpty) {
      return const Center(
        child: Text('No logs yet', style: TextStyle(color: ZoyaTheme.textMuted)),
      );
    }

    return ListView.builder(
      itemCount: logs.length,
      itemBuilder: (context, index) {
        final log = logs[index];
        final ts = DateFormat('HH:mm:ss').format(log.timestamp);
        final color = switch (log.level.toLowerCase()) {
          'error' => ZoyaTheme.danger,
          'warning' => ZoyaTheme.warning,
          _ => ZoyaTheme.textMuted,
        };

        return ListTile(
          dense: true,
          title: Text(
            log.message,
            style: TextStyle(color: color, fontFamily: 'monospace', fontSize: 12),
          ),
          leading: Text(
            ts,
            style: TextStyle(
              color: ZoyaTheme.textMuted.withValues(alpha: 0.7),
              fontFamily: 'monospace',
              fontSize: 11,
            ),
          ),
        );
      },
    );
  }
}
