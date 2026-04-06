import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/state/controllers/workspace_controller.dart';
import 'package:voice_assistant/state/models/workspace_models.dart';

void main() {
  group('WorkspaceController', () {
    test('updates layout mode and workbench selection', () {
      final controller = WorkspaceController();

      controller.setLayoutMode(WorkspaceLayoutMode.wide);
      controller.selectWorkbenchTab(WorkbenchTab.research);

      expect(controller.layoutMode, WorkspaceLayoutMode.wide);
      expect(controller.selectedWorkbenchTab, WorkbenchTab.research);
    });

    test('tracks sidebar, page, and compact workbench sheet state', () {
      final controller = WorkspaceController();

      controller.toggleSidebar();
      controller.setCurrentPage('projects');

      expect(controller.sidebarCollapsed, isFalse);
      expect(controller.currentPage, 'projects');
    });

    test('selects and clears artifacts', () {
      final controller = WorkspaceController();
      const artifact = WorkbenchArtifactRef(
        id: 'artifact-1',
        type: 'research',
        title: 'Python history',
        conversationId: 'conversation-1',
      );

      controller.selectArtifact(artifact);
      expect(controller.selectedArtifact?.id, 'artifact-1');

      controller.clearSelectedArtifact();
      expect(controller.selectedArtifact, isNull);
    });
  });
}
