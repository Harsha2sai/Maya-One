import 'package:flutter/foundation.dart';

enum IdeWorkspaceMode {
  editor,
  missionControl,
}

enum IdeActivitySection {
  explorer,
  search,
  scm,
  terminal,
  agentic,
}

enum BuddySpecies {
  mayaCore,
  orbitFox,
  terminalOtter,
  neonCat,
}

enum BuddyState {
  idle,
  working,
  complete,
  error,
}

class BuddyConfig {
  const BuddyConfig({
    required this.species,
    required this.isShiny,
    required this.seed,
    required this.userIdHash,
  });

  final BuddySpecies species;
  final bool isShiny;
  final int seed;
  final int userIdHash;
}

class IDEWorkspaceController extends ChangeNotifier {
  IdeWorkspaceMode _mode = IdeWorkspaceMode.editor;
  IdeActivitySection _activeSection = IdeActivitySection.explorer;
  String _workspacePath = '.';
  String? _ideSessionId;
  String? _selectedTaskId;
  String? _selectedFilePath;
  bool _leftPanelVisible = true;
  bool _rightPanelVisible = true;
  bool _terminalVisible = true;
  bool _catchingUp = false;
  double _leftPanelWidth = 280;
  double _rightPanelWidth = 340;
  double _terminalHeight = 240;
  BuddyState _buddyState = BuddyState.idle;
  BuddyConfig _buddyConfig = const BuddyConfig(
    species: BuddySpecies.mayaCore,
    isShiny: false,
    seed: 1,
    userIdHash: 1,
  );

  IdeWorkspaceMode get mode => _mode;
  IdeActivitySection get activeSection => _activeSection;
  String get workspacePath => _workspacePath;
  String? get ideSessionId => _ideSessionId;
  String? get selectedTaskId => _selectedTaskId;
  String? get selectedFilePath => _selectedFilePath;
  bool get leftPanelVisible => _leftPanelVisible;
  bool get rightPanelVisible => _rightPanelVisible;
  bool get terminalVisible => _terminalVisible;
  bool get catchingUp => _catchingUp;
  double get leftPanelWidth => _leftPanelWidth;
  double get rightPanelWidth => _rightPanelWidth;
  double get terminalHeight => _terminalHeight;
  BuddyState get buddyState => _buddyState;
  BuddyConfig get buddyConfig => _buddyConfig;

  void setMode(IdeWorkspaceMode mode) {
    if (_mode == mode) return;
    _mode = mode;
    notifyListeners();
  }

  void setActiveSection(IdeActivitySection section) {
    if (_activeSection == section) return;
    _activeSection = section;
    notifyListeners();
  }

  void setWorkspacePath(String value) {
    final next = value.trim().isEmpty ? '.' : value.trim();
    if (_workspacePath == next) return;
    _workspacePath = next;
    notifyListeners();
  }

  void setIdeSessionId(String? sessionId) {
    if (_ideSessionId == sessionId) return;
    _ideSessionId = sessionId;
    notifyListeners();
  }

  void setSelectedTaskId(String? taskId) {
    if (_selectedTaskId == taskId) return;
    _selectedTaskId = taskId;
    notifyListeners();
  }

  void setSelectedFilePath(String? path) {
    if (_selectedFilePath == path) return;
    _selectedFilePath = path;
    notifyListeners();
  }

  void setLeftPanelVisible(bool visible) {
    if (_leftPanelVisible == visible) return;
    _leftPanelVisible = visible;
    notifyListeners();
  }

  void setRightPanelVisible(bool visible) {
    if (_rightPanelVisible == visible) return;
    _rightPanelVisible = visible;
    notifyListeners();
  }

  void setTerminalVisible(bool visible) {
    if (_terminalVisible == visible) return;
    _terminalVisible = visible;
    notifyListeners();
  }

  void setCatchingUp(bool catchingUp) {
    if (_catchingUp == catchingUp) return;
    _catchingUp = catchingUp;
    notifyListeners();
  }

  void setLeftPanelWidth(double width) {
    final next = width.clamp(220.0, 420.0);
    if ((_leftPanelWidth - next).abs() < 0.01) return;
    _leftPanelWidth = next;
    notifyListeners();
  }

  void setRightPanelWidth(double width) {
    final next = width.clamp(280.0, 520.0);
    if ((_rightPanelWidth - next).abs() < 0.01) return;
    _rightPanelWidth = next;
    notifyListeners();
  }

  void setTerminalHeight(double height) {
    final next = height.clamp(140.0, 420.0);
    if ((_terminalHeight - next).abs() < 0.01) return;
    _terminalHeight = next;
    notifyListeners();
  }

  void setBuddyState(BuddyState state) {
    if (_buddyState == state) return;
    _buddyState = state;
    notifyListeners();
  }

  void configureBuddy(String userId) {
    final normalized = userId.trim().isEmpty ? 'guest-local' : userId.trim();
    final hash = _fnv1a32(normalized);
    final rand = _mulberry32(hash);

    final species = BuddySpecies.values[(rand() * BuddySpecies.values.length).floor()];
    final isShiny = rand() < 0.03;
    final seed = (rand() * 0x7fffffff).floor();

    _buddyConfig = BuddyConfig(
      species: species,
      isShiny: isShiny,
      seed: seed,
      userIdHash: hash,
    );
    notifyListeners();
  }

  static int _fnv1a32(String input) {
    var hash = 0x811c9dc5;
    for (final codePoint in input.codeUnits) {
      hash ^= codePoint;
      hash = (hash * 0x01000193) & 0xffffffff;
    }
    return hash;
  }

  static double Function() _mulberry32(int seed) {
    var state = seed & 0xffffffff;
    return () {
      state = (state + 0x6D2B79F5) & 0xffffffff;
      var t = state;
      t = (t ^ (t >> 15)) * (t | 1);
      t &= 0xffffffff;
      t ^= t + ((t ^ (t >> 7)) * (t | 61));
      t &= 0xffffffff;
      return ((t ^ (t >> 14)) & 0xffffffff) / 4294967296.0;
    };
  }
}
