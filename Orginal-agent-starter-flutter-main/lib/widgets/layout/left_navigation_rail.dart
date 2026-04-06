import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '../../state/controllers/workspace_controller.dart';
import '../../state/models/workspace_models.dart';
import '../../ui/theme/app_theme.dart';

class LeftNavigationRail extends StatelessWidget {
  const LeftNavigationRail({super.key});

  @override
  Widget build(BuildContext context) {
    final workspace = context.watch<WorkspaceController>();

    if (workspace.layoutMode == WorkspaceLayoutMode.compact) {
      return const SizedBox.shrink();
    }

    return Container(
      key: const Key('left_navigation_rail'),
      width: 64,
      decoration: BoxDecoration(
        color: ZoyaTheme.sidebarBg.withValues(alpha: 0.9),
        border: Border(
          right: BorderSide(color: ZoyaTheme.glassBorder.withValues(alpha: 0.5)),
        ),
      ),
      child: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 12),
            _RailDestination(
              key: const Key('rail_tab_agents'),
              icon: FontAwesomeIcons.boxesStacked,
              label: 'Tasks',
              selected: workspace.selectedWorkbenchTab == WorkbenchTab.agents,
              onTap: () => _handleTap(context, workspace, WorkbenchTab.agents),
            ),
            _RailDestination(
              key: const Key('rail_tab_timeline'),
              icon: FontAwesomeIcons.timeline,
              label: 'Timeline',
              selected: workspace.selectedWorkbenchTab == WorkbenchTab.tasks,
              onTap: () => _handleTap(context, workspace, WorkbenchTab.tasks),
            ),
            _RailDestination(
              key: const Key('rail_tab_logs'),
              icon: FontAwesomeIcons.terminal,
              label: 'Logs',
              selected: workspace.selectedWorkbenchTab == WorkbenchTab.logs,
              onTap: () => _handleTap(context, workspace, WorkbenchTab.logs),
            ),
            _RailDestination(
              key: const Key('rail_tab_research'),
              icon: FontAwesomeIcons.magnifyingGlassChart,
              label: 'Research',
              selected: workspace.selectedWorkbenchTab == WorkbenchTab.research,
              onTap: () => _handleTap(context, workspace, WorkbenchTab.research),
            ),
            _RailDestination(
              key: const Key('rail_tab_artifacts'),
              icon: FontAwesomeIcons.fileCode,
              label: 'Artifacts',
              selected: workspace.selectedWorkbenchTab == WorkbenchTab.artifacts,
              onTap: () => _handleTap(context, workspace, WorkbenchTab.artifacts),
            ),
            _RailDestination(
              key: const Key('rail_tab_memory'),
              icon: FontAwesomeIcons.microchip,
              label: 'Memory',
              selected: workspace.selectedWorkbenchTab == WorkbenchTab.memory,
              onTap: () => _handleTap(context, workspace, WorkbenchTab.memory),
            ),
            const Spacer(),
          ],
        ),
      ),
    );
  }

  void _handleTap(BuildContext context, WorkspaceController workspace, WorkbenchTab tab) {
    if (workspace.selectedWorkbenchTab == tab && workspace.workbenchVisible) {
      workspace.setWorkbenchVisible(false);
    } else {
      workspace.selectWorkbenchTab(tab);
      if (!workspace.workbenchVisible) {
        workspace.setWorkbenchVisible(true);
        workspace.setWorkbenchCollapsed(false);
      }
    }
  }
}

class _RailDestination extends StatefulWidget {
  final FaIconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _RailDestination({
    super.key,
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  State<_RailDestination> createState() => _RailDestinationState();
}

class _RailDestinationState extends State<_RailDestination> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final color = widget.selected ? ZoyaTheme.accent : ZoyaTheme.textMuted;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: MouseRegion(
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() => _hover = false),
        child: Tooltip(
          message: widget.label,
          waitDuration: const Duration(milliseconds: 400),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: widget.onTap,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                curve: Curves.easeOut,
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: widget.selected 
                      ? ZoyaTheme.accent.withValues(alpha: 0.12) 
                      : (_hover ? Colors.white.withValues(alpha: 0.05) : Colors.transparent),
                  borderRadius: BorderRadius.circular(12),
                  border: widget.selected 
                      ? Border.all(color: ZoyaTheme.accent.withValues(alpha: 0.28)) 
                      : Border.all(color: Colors.transparent),
                ),
                child: Center(
                  child: FaIcon(widget.icon, size: 20, color: color),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
