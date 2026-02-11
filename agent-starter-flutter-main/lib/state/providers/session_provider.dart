import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/foundation.dart';
import 'package:livekit_client/livekit_client.dart' as lk;
import '../base_provider.dart';
import '../../core/services/livekit_service.dart';
import '../../widgets/cosmic_orb.dart'; // For OrbState enum
import '../../managers/agent_process_manager.dart';
import 'dart:io';

enum SessionConnectionState {
  disconnected,
  connecting,
  connected,
  reconnecting,
  disconnecting,
}

class SessionProvider extends BaseProvider {
  final LiveKitService _liveKitService;

  lk.Room? _room;
  lk.Session? _session;
  SessionConnectionState _connectionState = SessionConnectionState.disconnected;
  DateTime? _sessionStartTime;
  bool _disposed = false;
  bool _userRequestedDisconnect = false;
  String? _currentUserId;

  SessionProvider(this._liveKitService) : super('SessionProvider');

  // Getters
  lk.Room? get room => _room;
  lk.Session? get session => _session;
  SessionConnectionState get connectionState => _connectionState;
  bool get isConnected => _connectionState == SessionConnectionState.connected;
  bool get isConnecting => _connectionState == SessionConnectionState.connecting;
  DateTime? get sessionStartTime => _sessionStartTime;

  // Agent State Logic
  OrbState get agentState {
    if (_room == null) return OrbState.idle;
    // Check if any remote participant is speaking
    // In a 1:1 agent scenario, the agent is the remote participant
    // We check activeSpeakers list.
    final isActive = _room!.activeSpeakers.any((p) => p is lk.RemoteParticipant);
    if (isActive) {
      return OrbState.speaking;
    }
    // If user is speaking (LocalParticipant), agent is listening
    final isUserSpeaking = _room!.activeSpeakers.any((p) => p is lk.LocalParticipant);
    if (isUserSpeaking) {
      return OrbState.listening;
    }

    return OrbState.idle;
  }

  /// Send a text message to the agent
  Future<void> sendUserMessage(String text) async {
    if (_room == null) {
      debugPrint('WARNING: Room is null, cannot send message');
      return;
    }
    try {
      debugPrint('Attempting to send message via data channel: "$text"');
      // Use standard LiveKit data publish for chat
      final data = utf8.encode(text);
      await _room!.localParticipant?.publishData(
        data,
        topic: 'lk.chat',
        reliable: true,
      );
      debugPrint('Message published to data channel successfully');
    } catch (e) {
      debugPrint('Error sending message: $e');
      rethrow; // Let caller know
    }
  }

  /// Toggle microphone
  Future<void> setMicrophoneEnabled(bool enabled) async {
    if (_room?.localParticipant != null) {
      await _room!.localParticipant!.setMicrophoneEnabled(enabled);
      notifyListeners();
    }
  }

  String _loadingStatus = '';
  String get loadingStatus => _loadingStatus;

  /// Check if the backend token server is reachable
  Future<bool> _checkBackendHealth() async {
    try {
      // Try to connect to the token server port
      final socket = await Socket.connect('localhost', 5050, timeout: const Duration(milliseconds: 500));
      socket.destroy();
      return true;
    } catch (_) {
      return false;
    }
  }

  void _updateLoadingStatus(String status) {
    _loadingStatus = status;
    notifyListeners();
  }

  /// Connect to LiveKit session
  Future<bool> connect({String? userId, Map<String, dynamic>? clientConfig}) async {
    if (_connectionState == SessionConnectionState.connected) {
      log('Already connected');
      return true;
    }

    _userRequestedDisconnect = false;
    if (userId != null) _currentUserId = userId;

    _updateConnectionState(SessionConnectionState.connecting);
    _updateLoadingStatus('Initializing system core...');

    return await safeExecute(() async {
          // 1. Verify Backend Status
          _updateLoadingStatus('Verifying neural backend...');
          final bool isBackendUp = await _checkBackendHealth();

          if (!isBackendUp) {
            log('Backend not reachable, attempting auto-start...');
            _updateLoadingStatus('Booting local neural engine...');

            final agentManager = AgentProcessManager();
            await agentManager.startAgent();

            // Wait for backend to come online (max 10 seconds)
            bool ready = false;
            for (int i = 0; i < 20; i++) {
              // Pulse the message
              final dots = '.' * ((i % 3) + 1);
              _updateLoadingStatus('Starting neural engine$dots');

              if (await _checkBackendHealth()) {
                ready = true;
                break;
              }
              await Future.delayed(const Duration(milliseconds: 500));
            }

            if (!ready) {
              throw Exception('Backend failed to initialize. Please check logs.');
            }
            log('Backend started successfully.');
          }

          log('Creating LiveKit room...');
          _updateLoadingStatus('Configuring secure room...');

          // Initialize room with optimization options
          _room = lk.Room(
            roomOptions: const lk.RoomOptions(
              adaptiveStream: true,
              dynacast: true,
              enableVisualizer: true,
              defaultAudioPublishOptions: lk.AudioPublishOptions(
                name: 'audio_track',
              ),
            ),
          );

          final finalUserId = userId ?? _currentUserId ?? 'guest_${DateTime.now().millisecondsSinceEpoch}';
          _currentUserId = finalUserId;
          final roomName =
              'voice-assistant-${finalUserId.substring(0, math.min(finalUserId.length, 8))}-${DateTime.now().millisecondsSinceEpoch}';

          final metadata = {
            'user_id': finalUserId,
            'timestamp': DateTime.now().toIso8601String(),
            ...?clientConfig,
          };

          log('Creating LiveKit session for room: $roomName');
          _updateLoadingStatus('Authenticating & Token Exchange...');

          _session = await _liveKitService.createSession(
            _room!,
            roomName: roomName,
            participantName: finalUserId,
            metadata: metadata,
          );

          _session!.addListener(_onSessionChange);
          _room!.addListener(_onRoomChange);

          _room!.createListener()
            ..on<lk.ActiveSpeakersChangedEvent>((_) => notifyListeners())
            ..on<lk.DataReceivedEvent>(_onDataReceived)
            ..on<lk.TranscriptionEvent>((event) => _onTranscription(event))
            ..on<lk.RoomDisconnectedEvent>((event) {
              log('Room Disconnected Event: ${event.reason}');
              _updateConnectionState(SessionConnectionState.disconnected);
            });

          log('Starting session...');
          _updateLoadingStatus('Establishing uplink...');
          await _session!.start();

          // Wait a moment for the agent to potentially join (optional aesthetic wait)
          _updateLoadingStatus('Synchronizing state...');
          await Future.delayed(const Duration(milliseconds: 800));

          _sessionStartTime = DateTime.now();
          _updateConnectionState(SessionConnectionState.connected);
          _updateLoadingStatus('System Ready');

          log('Session connected successfully');
          return true;
        }) ??
        false;
  }

  /// Send a command to the Agent
  Future<void> sendCommand(String action, [Map<String, dynamic>? payload]) async {
    if (_room == null) return;

    final cmd = {
      'type': 'COMMAND',
      'id': DateTime.now().millisecondsSinceEpoch.toString(), // Simple ID
      'source': 'flutter',
      'action': action,
      'payload': payload ?? {},
    };

    await _liveKitService.sendCommand(_room!, cmd);
  }

  void _onDataReceived(lk.DataReceivedEvent event) {
    if (event.topic == 'system.events') {
      try {
        final jsonStr = utf8.decode(event.data);
        final msg = jsonDecode(jsonStr);
        _routeSystemMessage(msg);
      } catch (e) {
        log('Error parsing system event: $e');
      }
    }
    // Also notify for generic chat/data updates
    notifyListeners();
  }

  void _routeSystemMessage(Map msg) {
    log('📥 RECEIVED SYSTEM MSG: ${msg['type']} / ${msg['category']}');
    // Future expansion: Route to TaskProvider, LogProvider, etc.
  }

  /// Disconnect from session
  Future<void> disconnect() async {
    _userRequestedDisconnect = true;

    if (_connectionState == SessionConnectionState.disconnected) {
      log('Already disconnected');
      return;
    }

    _updateConnectionState(SessionConnectionState.disconnecting);

    await safeExecute(() async {
      log('Disconnecting from session...');

      _session?.removeListener(_onSessionChange);
      _room?.removeListener(_onRoomChange);

      await _session?.dispose();
      await _room?.dispose();

      _session = null;
      _room = null;
      _sessionStartTime = null;

      _updateConnectionState(SessionConnectionState.disconnected);
      log('Session disconnected');
    });
  }

  void _onSessionChange() {
    if (_session != null && !_disposed) {
      log('Session state changed');
      notifyListeners();
    }
  }

  void _onRoomChange() {
    if (_room != null && !_disposed) {
      var newState = _mapLiveKitState(_room!.connectionState);

      // Intercept unintential disconnects
      if (newState == SessionConnectionState.disconnected && !_userRequestedDisconnect) {
        log('⚠️ Unintentional disconnect detected. Attempting auto-reconnect...');
        newState = SessionConnectionState.reconnecting;
        _attemptAutoReconnect();
      }

      _updateConnectionState(newState);
    }
  }

  Future<void> _attemptAutoReconnect() async {
    if (_connectionState == SessionConnectionState.connecting) return;

    await Future.delayed(const Duration(seconds: 1));

    if (_disposed || _userRequestedDisconnect) return;

    log('🔄 Executing auto-reconnect sequence...');

    try {
      _session?.removeListener(_onSessionChange);
      _room?.removeListener(_onRoomChange);
      await _session?.dispose();
      await _room?.dispose();
    } catch (e) {
      log('Cleanup error during reconnect: $e');
    }

    _session = null;
    _room = null;

    try {
      await connect(userId: _currentUserId);
    } catch (e) {
      log('❌ Auto-reconnect failed: $e');
      _updateConnectionState(SessionConnectionState.disconnected);
    }
  }

  SessionConnectionState _mapLiveKitState(lk.ConnectionState lkState) {
    switch (lkState) {
      case lk.ConnectionState.disconnected:
        return SessionConnectionState.disconnected;
      case lk.ConnectionState.connecting:
        return SessionConnectionState.connecting;
      case lk.ConnectionState.connected:
        return SessionConnectionState.connected;
      case lk.ConnectionState.reconnecting:
        return SessionConnectionState.reconnecting;
    }
  }

  void _onTranscription(lk.TranscriptionEvent event) {
    if (_disposed) return;

    // We expect the ChatProvider to be available via a callback or we can use a global register
    // But standard practice in this app seems to be separate providers.
    // I'll add a helper method to be used by the UI or a registration.
    log('Transcription received: ${event.segments.first.text}');

    // For now, I'll rely on the AgentScreen to use a listener if I can't find a direct link.
    // Better: let's add a list of transcriptions here or a dedicated stream.
  }

  void _updateConnectionState(SessionConnectionState state) {
    if (_connectionState != state && !_disposed) {
      _connectionState = state;
      log('Connection state: $state');
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    disconnect();
    super.dispose();
  }
}
