import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/core/services/search_cue_service.dart';

void main() {
  group('SearchCueService', () {
    test('plays expected asset per cue state', () async {
      final playedAssets = <String>[];
      final service = SearchCueService(
        playOverride: (assetPath) async {
          playedAssets.add(assetPath);
        },
      );

      await service.playStateCue(
        'turn-1',
        state: CueState.searching,
        soundEnabled: true,
      );
      await service.playStateCue(
        'turn-1',
        state: CueState.toolCalling,
        soundEnabled: true,
      );
      await service.playStateCue(
        'turn-1',
        state: CueState.completed,
        soundEnabled: true,
      );

      expect(
        playedAssets,
        equals(<String>[
          'audio/search_start_chime.wav',
          'audio/tool_call_chime.wav',
          'audio/turn_complete_chime.wav',
        ]),
      );
    });

    test('dedupes by turn and cue state', () async {
      var playCount = 0;
      final service = SearchCueService(
        playOverride: (_) async {
          playCount += 1;
        },
      );

      final first = await service.playStateCue(
        'turn-2',
        state: CueState.searching,
        soundEnabled: true,
      );
      final second = await service.playStateCue(
        'turn-2',
        state: CueState.searching,
        soundEnabled: true,
      );
      final third = await service.playStateCue(
        'turn-2',
        state: CueState.toolCalling,
        soundEnabled: true,
      );

      expect(first, isTrue);
      expect(second, isFalse);
      expect(third, isTrue);
      expect(playCount, 2);
    });

    test('onTurnComplete clears all cue states for turn', () async {
      var playCount = 0;
      final service = SearchCueService(
        playOverride: (_) async {
          playCount += 1;
        },
      );

      await service.playStateCue(
        'turn-3',
        state: CueState.completed,
        soundEnabled: true,
      );
      service.onTurnComplete('turn-3');
      final replayed = await service.playStateCue(
        'turn-3',
        state: CueState.completed,
        soundEnabled: true,
      );

      expect(replayed, isTrue);
      expect(playCount, 2);
    });

    test('sound disabled skips playback', () async {
      var playCount = 0;
      final service = SearchCueService(
        playOverride: (_) async {
          playCount += 1;
        },
      );

      final played = await service.playStateCue(
        'turn-4',
        state: CueState.searching,
        soundEnabled: false,
      );

      expect(played, isFalse);
      expect(playCount, 0);
    });

    test('playCue remains backward-compatible wrapper for searching', () async {
      final playedAssets = <String>[];
      final service = SearchCueService(
        playOverride: (assetPath) async {
          playedAssets.add(assetPath);
        },
      );

      final played = await service.playCue('turn-5', soundEnabled: true);

      expect(played, isTrue);
      expect(playedAssets, equals(<String>['audio/search_start_chime.wav']));
    });
  });
}
