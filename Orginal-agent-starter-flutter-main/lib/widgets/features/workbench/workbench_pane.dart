import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../state/controllers/workspace_controller.dart';
import '../../../state/controllers/overlay_controller.dart';
import '../../../state/models/workspace_models.dart';
import '../../../ui/theme/app_theme.dart';
import 'task_list_panel.dart';
import 'plan_timeline_panel.dart';
import 'task_inspector.dart';
import 'logs_panel.dart';
import 'research_artifact_panel.dart';
import 'artifacts_tab.dart';
import 'ide_tab.dart';

final GlobalKey workbenchPaneKey = GlobalKey(debugLabel: 'workbench_pane');

class WorkbenchPane extends StatelessWidget {
  const WorkbenchPane({super.key});

  @override
  Widget build(BuildContext context) {
    final workspace = context.watch<WorkspaceController>();
    if (!workspace.workbenchVisible) {
      return const SizedBox.shrink();
    }

    final isCompact = workspace.layoutMode == WorkspaceLayoutMode.compact;
    final double width = workspace.workbenchCollapsed ? 48.0 : 320.0;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
      width: isCompact ? double.infinity : width,
      decoration: BoxDecoration(
        color: ZoyaTheme.glassBg,
        border: isCompact ? null : Border(
          left: BorderSide(color: ZoyaTheme.glassBorder),
        ),
      ),
      child: workspace.workbenchCollapsed && !isCompact
          ? _buildCollapsed(context)
          : _buildExpanded(context, workspace, isCompact),
    );
  }

  Widget _buildCollapsed(BuildContext context) {
    return Column(
      children: [
        const SizedBox(height: 16),
        IconButton(
          icon: const Icon(Icons.chevron_left, color: ZoyaTheme.textMain),
          onPressed: () => context.read<WorkspaceController>().setWorkbenchCollapsed(false),
        ),
      ],
    );
  }

  Widget _buildExpanded(BuildContext context, WorkspaceController workspace, bool isCompact) {
    return Column(
      children: [
        // Header
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
          ),
          child: Row(
            children: [
              const Expanded(
                child: Padding(
                  padding: EdgeInsets.only(left: 8.0),
                  child: Text('Workbench', style: TextStyle(color: ZoyaTheme.textMain, fontWeight: FontWeight.bold)),
                ),
              ),
              IconButton(
                key: const Key('workbench_pane_close'),
                icon: const Icon(Icons.close, color: ZoyaTheme.textMuted, size: 18),
                tooltip: 'Close workbench',
                onPressed: () {
                  if (isCompact) {
                    context.read<OverlayController>().setCompactWorkbenchSheetOpen(false);
                  } else {
                    workspace.setWorkbenchVisible(false);
                  }
                },
              ),
            ],
          ),
        ),
        // Tabs
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.start,
            children: [
              _TabButton(
                label: 'Agents',
                isActive: workspace.selectedWorkbenchTab == WorkbenchTab.agents,
                onTap: () => workspace.selectWorkbenchTab(WorkbenchTab.agents),
              ),
              _TabButton(
                label: 'Tasks',
                isActive: workspace.selectedWorkbenchTab == WorkbenchTab.tasks,
                onTap: () => workspace.selectWorkbenchTab(WorkbenchTab.tasks),
              ),
              _TabButton(
                label: 'Logs',
                isActive: workspace.selectedWorkbenchTab == WorkbenchTab.logs,
                onTap: () => workspace.selectWorkbenchTab(WorkbenchTab.logs),
              ),
              _TabButton(
                label: 'Research',
                isActive: workspace.selectedWorkbenchTab == WorkbenchTab.research,
                onTap: () => workspace.selectWorkbenchTab(WorkbenchTab.research),
              ),
              _TabButton(
                label: 'Artifacts',
                isActive: workspace.selectedWorkbenchTab == WorkbenchTab.artifacts,
                onTap: () => workspace.selectWorkbenchTab(WorkbenchTab.artifacts),
              ),
              _TabButton(
                label: 'Memory',
                isActive: workspace.selectedWorkbenchTab == WorkbenchTab.memory,
                onTap: () => workspace.selectWorkbenchTab(WorkbenchTab.memory),
              ),
              _TabButton(
                label: 'IDE',
                isActive: workspace.selectedWorkbenchTab == WorkbenchTab.ide,
                onTap: () => workspace.selectWorkbenchTab(WorkbenchTab.ide),
              ),
            ],
          ),
        ),
        // Content
        Expanded(
          child: _buildTabContent(workspace.selectedWorkbenchTab),
        ),
      ],
    );
  }

  Widget _buildTabContent(WorkbenchTab tab) {
    switch (tab) {
      case WorkbenchTab.agents:
        return const Center(
          child: Text(
            'Agent management coming soon',
            style: TextStyle(color: ZoyaTheme.textMuted),
          ),
        );
      case WorkbenchTab.tasks:
        return const _TasksWorkbenchView();
      case WorkbenchTab.logs:
        return const LogsPanel();
      case WorkbenchTab.research:
        return const ResearchArtifactPanel();
      case WorkbenchTab.artifacts:
        return const ArtifactsTab();
      case WorkbenchTab.memory:
        return const Center(
          child: Text(
            'Memory visibility coming in Phase 9',
            style: TextStyle(color: ZoyaTheme.textMuted),
          ),
        );
      case WorkbenchTab.ide:
        return const IDETab();
    }
  }
}

class _TasksWorkbenchView extends StatelessWidget {
  const _TasksWorkbenchView();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Expanded(flex: 4, child: TaskListPanel()),
        Divider(height: 1, color: ZoyaTheme.glassBorder),
        const Expanded(flex: 3, child: PlanTimelinePanel()),
        Divider(height: 1, color: ZoyaTheme.glassBorder),
        const Expanded(flex: 4, child: TaskInspector()),
      ],
    );
  }
}

class _TabButton extends StatelessWidget {
  final String label;
  final bool isActive;
  final VoidCallback onTap;

  const _TabButton({required this.label, required this.isActive, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: isActive ? ZoyaTheme.accent : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isActive ? ZoyaTheme.accent : ZoyaTheme.textMuted,
            fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}
