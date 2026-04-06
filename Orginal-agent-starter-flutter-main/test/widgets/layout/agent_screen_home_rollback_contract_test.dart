import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('AgentScreen rollback contract removes unplanned shell slots', () {
    final source = File('lib/ui/screens/agent_screen.dart').readAsStringSync();

    expect(source, contains('leftNavigationRail: const LeftNavigationRail()'));
    expect(source, contains('voiceStatusBar: null'));
    expect(source, contains('statusPanel: null'));
    expect(source, contains('voiceActionDock: null'));
    expect(source, isNot(contains('agentWorkbenchPane: null')));
  });

  test('AgentScreen right icon strip maps to expected workbench tabs', () {
    final source = File('lib/ui/screens/agent_screen.dart').readAsStringSync();

    expect(source, contains("Key('floating_icon_active_workflows')"));
    expect(source, contains('onTap: () => onOpenTab(WorkbenchTab.agents)'));

    expect(source, contains("Key('floating_icon_n8n')"));
    expect(source, contains('onTap: () => onOpenTab(WorkbenchTab.logs)'));

    expect(source, contains("Key('floating_icon_system_health')"));
    expect(source, contains('onTap: () => onOpenTab(WorkbenchTab.memory)'));
  });

  test('AgentScreen workbench open path guards unavailable controllers', () {
    final source = File('lib/ui/screens/agent_screen.dart').readAsStringSync();

    expect(
      source,
      contains('if (workspace == null || overlay == null)'),
    );
    expect(source, contains('debugPrint('));
  });

  test('AgentScreen toggles workbench closed when same icon is tapped again', () {
    final source = File('lib/ui/screens/agent_screen.dart').readAsStringSync();

    expect(source, contains('final isSameTab = workspace.selectedWorkbenchTab == tab;'));
    expect(source, contains('if (overlay.compactWorkbenchSheetOpen && isSameTab)'));
    expect(source, contains('overlay.setCompactWorkbenchSheetOpen(false);'));
  });
}
