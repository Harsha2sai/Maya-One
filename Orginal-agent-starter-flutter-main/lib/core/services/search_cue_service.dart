import 'dart:collection';

import 'package:audioplayers/audioplayers.dart';

enum CueState {
  searching,
  toolCalling,
  completed,
}

class SearchCueService {
  static const Map<CueState, String> _assetByState = <CueState, String>{
    CueState.searching: 'audio/search_start_chime.wav',
    CueState.toolCalling: 'audio/tool_call_chime.wav',
    CueState.completed: 'audio/turn_complete_chime.wav',
  };

  final AudioPlayer? _injectedPlayer;
  final Future<void> Function()? _preloadOverride;
  final Future<void> Function(String assetPath)? _playOverride;
  final LinkedHashSet<String> _playedCueKeys = LinkedHashSet<String>();

  AudioPlayer? _player;
  bool _preloaded = false;

  SearchCueService({
    AudioPlayer? player,
    Future<void> Function()? preloadOverride,
    Future<void> Function(String assetPath)? playOverride,
  })  : _injectedPlayer = player,
        _preloadOverride = preloadOverride,
        _playOverride = playOverride;

  AudioPlayer _resolvePlayer() {
    final existing = _player;
    if (existing != null) {
      return existing;
    }
    final created = _injectedPlayer ?? AudioPlayer();
    _player = created;
    return created;
  }

  Future<void> preload() async {
    if (_preloaded) {
      return;
    }
    final preloadOverride = _preloadOverride;
    if (preloadOverride != null) {
      await preloadOverride();
      _preloaded = true;
      return;
    }
    final player = _resolvePlayer();
    for (final assetPath in _assetByState.values) {
      await player.setSourceAsset(assetPath);
    }
    _preloaded = true;
  }

  Future<bool> playCue(
    String turnId, {
    required bool soundEnabled,
  }) async {
    return playStateCue(
      turnId,
      state: CueState.searching,
      soundEnabled: soundEnabled,
    );
  }

  Future<bool> playStateCue(
    String turnId, {
    required CueState state,
    required bool soundEnabled,
  }) async {
    final normalizedTurnId = turnId.trim();
    final assetPath = _assetByState[state];
    if (assetPath == null) {
      return false;
    }
    if (!soundEnabled || normalizedTurnId.isEmpty) {
      return false;
    }
    final cueKey = '$normalizedTurnId::${state.name}';
    if (_playedCueKeys.contains(cueKey)) {
      return false;
    }
    _playedCueKeys.add(cueKey);
    _enforceBoundedState();

    try {
      final playOverride = _playOverride;
      if (playOverride != null) {
        await playOverride(assetPath);
      } else {
        await preload();
        await _resolvePlayer().play(AssetSource(assetPath));
      }
      return true;
    } catch (_) {
      _playedCueKeys.remove(cueKey);
      rethrow;
    }
  }

  void onTurnComplete(String turnId) {
    final normalizedTurnId = turnId.trim();
    if (normalizedTurnId.isEmpty) {
      return;
    }
    _playedCueKeys.removeWhere((key) => key.startsWith('$normalizedTurnId::'));
  }

  void reset() {
    _playedCueKeys.clear();
  }

  void _enforceBoundedState() {
    while (_playedCueKeys.length > 60) {
      final oldest = _playedCueKeys.first;
      _playedCueKeys.remove(oldest);
    }
  }

  Future<void> dispose() async {
    final player = _player;
    _player = null;
    if (player != null) {
      await player.dispose();
    }
  }
}
