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

  /// Get LiveKit token and URL from backend token server
  Future<Map<String, String>> _getToken({
    required String roomName,
    required String participantName,
    Map<String, dynamic>? metadata,
  }) async {
    // 1. Try Local Backend
    try {
      final response = await http.post(
        Uri.parse('http://localhost:5050/token'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'roomName': roomName,
          'participantName': participantName,
          'metadata': metadata ?? {},
        }),
      ).timeout(const Duration(seconds: 2));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _logger.info('✅ Token received from local server');
        return {
          'token': data['token'],
          'url': data['url'] ?? dotenv.env['LIVEKIT_URL'] ?? '',
        };
      }
    } catch (e) {
      _logger.warning('⚠️ Local backend not available: $e');
    }

    // 2. Fallback to Sandbox
    final sandboxId = dotenv.env['LIVEKIT_SANDBOX_ID'] ?? '';
    if (sandboxId.isNotEmpty) {
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
    }
    
    // 3. Failure
    _logger.severe('❌ No token source available');
    throw Exception(
      'Token generation failed. Ensure local backend is running.'
    );
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
