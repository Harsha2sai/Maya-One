import 'dart:collection';

import 'package:audioplayers/audioplayers.dart';

class SearchCueService {
  static const String _assetPath = 'audio/search_start_chime.wav';

  final AudioPlayer? _injectedPlayer;
  final Future<void> Function()? _preloadOverride;
  final Future<void> Function(String assetPath)? _playOverride;
  final LinkedHashSet<String> _playedTurns = LinkedHashSet<String>();

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
    await _resolvePlayer().setSourceAsset(_assetPath);
    _preloaded = true;
  }

  Future<bool> playCue(
    String turnId, {
    required bool soundEnabled,
  }) async {
    final normalizedTurnId = turnId.trim();
    if (!soundEnabled || normalizedTurnId.isEmpty) {
      return false;
    }
    if (_playedTurns.contains(normalizedTurnId)) {
      return false;
    }
    _playedTurns.add(normalizedTurnId);
    _enforceBoundedState();

    try {
      final playOverride = _playOverride;
      if (playOverride != null) {
        await playOverride(_assetPath);
      } else {
        await preload();
        await _resolvePlayer().play(AssetSource(_assetPath));
      }
      return true;
    } catch (_) {
      _playedTurns.remove(normalizedTurnId);
      rethrow;
    }
  }

  void onTurnComplete(String turnId) {
    final normalizedTurnId = turnId.trim();
    if (normalizedTurnId.isEmpty) {
      return;
    }
    _playedTurns.remove(normalizedTurnId);
  }

  void reset() {
    _playedTurns.clear();
  }

  void _enforceBoundedState() {
    while (_playedTurns.length > 20) {
      final oldest = _playedTurns.first;
      _playedTurns.remove(oldest);
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
