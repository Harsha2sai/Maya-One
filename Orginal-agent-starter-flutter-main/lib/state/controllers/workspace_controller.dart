import 'package:flutter/foundation.dart';

import '../models/workspace_models.dart';

class WorkspaceController extends ChangeNotifier {
  WorkspaceLayoutMode _layoutMode = WorkspaceLayoutMode.medium;
  WorkbenchTab _selectedWorkbenchTab = WorkbenchTab.agents;
  WorkbenchArtifactRef? _selectedArtifact;
  bool _sidebarCollapsed = true;
  String _currentPage = 'home';
  bool _showTranscription = false;
  bool _workbenchVisible = true;
  bool _workbenchCollapsed = false;

  WorkspaceLayoutMode get layoutMode => _layoutMode;
  WorkbenchTab get selectedWorkbenchTab => _selectedWorkbenchTab;
  WorkbenchArtifactRef? get selectedArtifact => _selectedArtifact;
  bool get sidebarCollapsed => _sidebarCollapsed;
  String get currentPage => _currentPage;
  bool get showTranscription => _showTranscription;
  bool get workbenchVisible => _workbenchVisible;
  bool get workbenchCollapsed => _workbenchCollapsed;

  void setLayoutMode(WorkspaceLayoutMode mode) {
    if (_layoutMode == mode) {
      return;
    }
    _layoutMode = mode;
    notifyListeners();
  }

  void selectWorkbenchTab(WorkbenchTab tab) {
    if (_selectedWorkbenchTab == tab) {
      return;
    }
    _selectedWorkbenchTab = tab;
    notifyListeners();
  }

  void selectArtifact(WorkbenchArtifactRef? artifact) {
    final current = _selectedArtifact;
    if (current?.id == artifact?.id &&
        current?.type == artifact?.type &&
        current?.conversationId == artifact?.conversationId &&
        current?.taskId == artifact?.taskId) {
      return;
    }
    _selectedArtifact = artifact;
    notifyListeners();
  }

  void clearSelectedArtifact() {
    if (_selectedArtifact == null) {
      return;
    }
    _selectedArtifact = null;
    notifyListeners();
  }

  void toggleSidebar() {
    _sidebarCollapsed = !_sidebarCollapsed;
    notifyListeners();
  }

  void setSidebarCollapsed(bool value) {
    if (_sidebarCollapsed == value) {
      return;
    }
    _sidebarCollapsed = value;
    notifyListeners();
  }

  void setCurrentPage(String page) {
    if (_currentPage == page) {
      return;
    }
    _currentPage = page;
    notifyListeners();
  }

  void toggleTranscription() {
    _showTranscription = !_showTranscription;
    notifyListeners();
  }

  void setWorkbenchVisible(bool value) {
    if (_workbenchVisible == value) {
      return;
    }
    _workbenchVisible = value;
    notifyListeners();
  }

  void setWorkbenchCollapsed(bool value) {
    if (_workbenchCollapsed == value) {
      return;
    }
    _workbenchCollapsed = value;
    notifyListeners();
  }

  String? _selectedTaskId;
  bool _isTaskInspectorOpen = false;

  String? get selectedTaskId => _selectedTaskId;
  bool get isTaskInspectorOpen => _isTaskInspectorOpen;

  void selectTask(String? taskId) {
    if (_selectedTaskId == taskId) return;
    _selectedTaskId = taskId;
    _isTaskInspectorOpen = taskId != null;
    notifyListeners();
  }

  void setTaskInspectorOpen(bool isOpen) {
    if (_isTaskInspectorOpen == isOpen) return;
    _isTaskInspectorOpen = isOpen;
    notifyListeners();
  }
}
