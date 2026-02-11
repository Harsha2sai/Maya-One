import '../base_provider.dart';

class UIProvider extends BaseProvider {
  bool _sidebarCollapsed = true; // Start collapsed by default
  String _activeModal = '';
  String _currentPage = 'home';

  UIProvider() : super('UIProvider');

  bool get sidebarCollapsed => _sidebarCollapsed;
  String get activeModal => _activeModal;
  String get currentPage => _currentPage;
  bool get hasActiveModal => _activeModal.isNotEmpty;
  
  bool _showTranscription = false;
  bool get showTranscription => _showTranscription;
  
  void toggleTranscription() {
    _showTranscription = !_showTranscription;
    notifyListeners();
  }

  /// Toggle sidebar collapsed state
  void toggleSidebar() {
    _sidebarCollapsed = !_sidebarCollapsed;
    log('Sidebar ${_sidebarCollapsed ? 'collapsed' : 'expanded'}');
    notifyListeners();
  }

  /// Set sidebar collapsed state
  void setSidebarCollapsed(bool value) {
    if (_sidebarCollapsed != value) {
      _sidebarCollapsed = value;
      log('Sidebar ${_sidebarCollapsed ? 'collapsed' : 'expanded'}');
      notifyListeners();
    }
  }

  /// Show a modal
  void showModal(String modalName) {
    if (_activeModal != modalName) {
      _activeModal = modalName;
      log('Modal opened: $modalName');
      notifyListeners();
    }
  }

  /// Hide the current modal
  void hideModal() {
    if (_activeModal.isNotEmpty) {
      log('Modal closed: $_activeModal');
      _activeModal = '';
      notifyListeners();
    }
  }

  /// Set current page
  void setCurrentPage(String page) {
    if (_currentPage != page) {
      _currentPage = page;
      log('Page changed: $page');
      notifyListeners();
    }
  }
}
