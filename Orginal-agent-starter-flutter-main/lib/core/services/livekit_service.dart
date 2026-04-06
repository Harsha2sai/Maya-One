import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:logging/logging.dart';
import 'package:uuid/uuid.dart';

class LiveKitService {
  final Logger _logger = Logger('LiveKitService');
  final _uuid = const Uuid();
  static const String _localTokenUrl = 'http://127.0.0.1:5050/token';
  static const String _localhostTokenUrl = 'http://localhost:5050/token';

  bool _isTruthyEnv(String key, {bool defaultValue = false}) {
    final raw = dotenv.env[key];
    if (raw == null) return defaultValue;
    final normalized = raw.trim().toLowerCase();
    return normalized == '1' || normalized == 'true' || normalized == 'yes' || normalized == 'on';
  }

  /// Get LiveKit token and URL from backend token server
  Future<Map<String, String>> _getToken({
    required String roomName,
    required String participantName,
    Map<String, dynamic>? metadata,
  }) async {
    final requestBody = jsonEncode({
      'roomName': roomName,
      'participantName': participantName,
      'metadata': metadata ?? {},
    });

    // 1. Try Local Backend (127.0.0.1 first to avoid IPv6 localhost mismatch)
    final tokenUrls = [_localTokenUrl, _localhostTokenUrl];
    for (final tokenUrl in tokenUrls) {
      for (int attempt = 1; attempt <= 2; attempt++) {
        try {
          final response = await http
              .post(
                Uri.parse(tokenUrl),
                headers: {'Content-Type': 'application/json'},
                body: requestBody,
              )
              .timeout(const Duration(seconds: 30));

          if (response.statusCode == 200) {
            final data = jsonDecode(response.body);
            _logger.info('✅ Token received from local server ($tokenUrl)');
            return {
              'token': data['token'],
              'url': data['url'] ?? dotenv.env['LIVEKIT_URL'] ?? '',
            };
          }

          _logger.warning('⚠️ Token server returned ${response.statusCode} from $tokenUrl');
        } catch (e) {
          _logger.warning('⚠️ Local backend token request failed ($tokenUrl): $e');
        }

        if (attempt == 1) {
          await Future.delayed(const Duration(milliseconds: 750));
        }
      }
    }

    // 2. Fallback to Sandbox
    final sandboxId = dotenv.env['LIVEKIT_SANDBOX_ID'] ?? '';
    final allowSandboxFallback = _isTruthyEnv('LIVEKIT_ALLOW_SANDBOX_FALLBACK', defaultValue: false);
    if (allowSandboxFallback && sandboxId.isNotEmpty) {
      _logger.info('🔄 Falling back to Sandbox token generation');
      try {
        final tokenSource = lk.SandboxTokenSource(sandboxId: sandboxId);
        final response = await tokenSource.fetch(lk.TokenRequestOptions(
          roomName: roomName,
          participantIdentity: participantName,
        ));
        _logger.info('✅ Sandbox token generated');
        // Sandbox usually implies a specific URL structure or it's handled by SDK,
        // but SDK normally needs a URL. SandboxTokenSource might not provide URL directly
        // in all versions, but typically we rely on env or default.
        return {
          'token': response.participantToken,
          'url': dotenv.env['LIVEKIT_URL'] ?? '',
        };
      } catch (e) {
        _logger.severe('❌ Sandbox token generation failed: $e');
        rethrow;
      }
    } else if (sandboxId.isNotEmpty && !allowSandboxFallback) {
      _logger.info('ℹ️ Sandbox token fallback is disabled (LIVEKIT_ALLOW_SANDBOX_FALLBACK=false)');
    }

    // 3. Failure
    _logger.severe('❌ No token source available');
    throw Exception('Token generation failed. Ensure local backend is running.');
  }

  /// Create a LiveKit session with direct server connection
  Future<lk.Session> createSession(
    lk.Room room, {
    required String roomName,
    required String participantName,
    Map<String, dynamic>? metadata,
  }) async {
    _logger.info('Creating session for room: $roomName, participant: $participantName');

    // Get token and URL from backend
    final result = await _getToken(
      roomName: roomName,
      participantName: participantName,
      metadata: metadata,
    );

    final token = result['token']!;
    final url = result['url']!;

    if (url.isEmpty) {
      throw Exception('LiveKit URL not found. Check backend or .env configuration.');
    }

    _logger.info('Connecting to LiveKit server: $url');

    return lk.Session.fromFixedTokenSource(
      lk.LiteralTokenSource(
        serverUrl: url,
        participantToken: token,
      ),
      options: lk.SessionOptions(
        room: room,
        // Disable preConnectAudio on Linux to prevent native audio renderer crash
        preConnectAudio: !Platform.isLinux,
      ),
    );
  }

  /// Connect to a session
  Future<void> connect(lk.Session session) async {
    try {
      _logger.info('Connecting to LiveKit session...');
      await session.start();
      _logger.info('Session started successfully');
    } catch (e, stackTrace) {
      _logger.severe('Failed to start session', e, stackTrace);
      rethrow;
    }
  }

  /// Disconnect from a session
  Future<void> disconnect(lk.Session session) async {
    try {
      _logger.info('Disconnecting from session...');
      await session.dispose();
      _logger.info('Session disposed');
    } catch (e, stackTrace) {
      _logger.severe('Error disposing session', e, stackTrace);
    }
  }

  /// Send a system command via LiveKit Data Channel
  Future<void> sendCommand(lk.Room room, Map<String, dynamic> command) async {
    if (room.localParticipant == null) {
      _logger.warning('Cannot send command: localParticipant is null');
      return;
    }

    try {
      final jsonStr = jsonEncode(command);
      final bytes = utf8.encode(jsonStr);

      await room.localParticipant!.publishData(
        bytes,
        reliable: true,
        topic: 'system.commands',
      );
      _logger.info('📤 Sent Command: ${command['action']} to system.commands');
    } catch (e) {
      _logger.severe('Failed to send command: $e');
      rethrow;
    }
  }
}
