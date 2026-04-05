import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:app_links/app_links.dart';
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:url_launcher/url_launcher.dart';
import '../base_provider.dart';
import '../controllers/overlay_controller.dart';
import '../../core/events/agent_event_models.dart';
import '../../core/events/agent_event_validator.dart';
import '../../core/services/livekit_service.dart';
import '../../core/services/gatekeeper_event_logger.dart';
import '../../widgets/features/visuals/cosmic_orb.dart'; // For OrbState enum
import 'chat_provider.dart';
// import '../../core/services/agent_process_manager.dart'; // Removed as auto-start is disabled

enum SessionConnectionState {
  disconnected,
  connecting,
  connected,
  reconnecting,
  disconnecting,
}

class SessionProvider extends BaseProvider {
  final LiveKitService _liveKitService;
  static const bool _gatekeeperAutopilotEnabled = bool.fromEnvironment(
    'FLUTTER_GATEKEEPER_AUTOPILOT',
    defaultValue: false,
  );
  static const String _gatekeeperCommandPath = String.fromEnvironment(
    'FLUTTER_GATEKEEPER_COMMAND_PATH',
    defaultValue: '/tmp/maya_flutter_gatekeeper_cmd.jsonl',
  );

  lk.Room? _room;
  lk.Session? _session;
  lk.EventsListener<lk.RoomEvent>? _roomEventListener;
  SessionConnectionState _connectionState = SessionConnectionState.disconnected;
  DateTime? _sessionStartTime;
  bool _disposed = false;
  bool _userRequestedDisconnect = false;
  String? _currentUserId;
  Map<String, dynamic>? _lastAgentEvent;
  Map<String, dynamic>? _lastAgentMetaEvent;
  ChatProvider? _chatProvider;
  OverlayController? _overlayController;
  DateTime? _lastAssistantChatEventAt;
  int? _lastStructuredEventMs;
  final GatekeeperEventLogger _gatekeeperLogger = GatekeeperEventLogger.instance;
  Timer? _gatekeeperCommandPoller;
  Timer? _backendLivenessTimer;
  int _gatekeeperCommandOffset = 0;
  bool _gatekeeperPolling = false;
  String? _lastGatekeeperCommandId;
  DateTime? _lastBackendHeartbeatAt;
  bool _backendDisconnectInProgress = false;
  bool _autoReconnectInProgress = false;
  Future<bool>? _connectFuture;
  int _autoReconnectAttempts = 0;
  bool _hasEverConnected = false;
  final AppLinks _appLinks = AppLinks();
  StreamSubscription<Uri>? _deepLinkSubscription;
  Completer<bool>? _bootstrapAckCompleter;
  String? _pendingBootstrapConversationId;
  int? _pendingBootstrapVersion;
  final StreamController<AgentUiEvent> _agentEventsController = StreamController<AgentUiEvent>.broadcast(sync: true);
  static const int _maxAutoReconnectAttempts = 3;
  static const int _structuredSuppressWindowMs = 8000;
  static const Duration _backendHeartbeatProbeInterval = Duration(seconds: 5);
  static const Duration _backendHeartbeatTimeout = Duration(seconds: 15);

  SessionProvider(this._liveKitService) : super('SessionProvider');

  // Getters
  lk.Room? get room => _room;
  lk.Session? get session => _session;
  SessionConnectionState get connectionState => _connectionState;
  bool get isConnected => _connectionState == SessionConnectionState.connected;
  bool get isConnecting => _connectionState == SessionConnectionState.connecting;
  DateTime? get sessionStartTime => _sessionStartTime;
  Map<String, dynamic>? get lastAgentEvent => _lastAgentEvent;
  Map<String, dynamic>? get lastAgentMetaEvent => _lastAgentMetaEvent;
  String? get currentSessionId => _room?.name;
  String? get currentUserId => _currentUserId;
  Stream<AgentUiEvent> get agentEvents => _agentEventsController.stream;

  void bindChatProvider(ChatProvider provider) {
    _chatProvider = provider;
  }

  void bindOverlayController(OverlayController controller) {
    _overlayController = controller;
    _overlayController?.setReconnectPromptVisible(_shouldShowReconnectPrompt(_connectionState));
  }

  bool _shouldShowReconnectPrompt(SessionConnectionState state) {
    if (state == SessionConnectionState.reconnecting) {
      return true;
    }
    if (state == SessionConnectionState.disconnected) {
      return _hasEverConnected && !_userRequestedDisconnect;
    }
    return false;
  }

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
    if (_connectionState != SessionConnectionState.connected) {
      log('WARNING: Session not connected, cannot send message');
      return;
    }
    if (_room == null) {
      debugPrint('WARNING: Room is null, cannot send message');
      _gatekeeperLogger.logEvent(
        'ui_error',
        sessionId: _room?.name,
        source: 'ui',
        status: 'send_user_message_room_null',
        content: text,
      );
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
      _gatekeeperLogger.logEvent(
        'user_message_sent',
        sessionId: _room?.name,
        source: 'ui',
        content: text,
        extra: {
          'user_id': _currentUserId,
          'topic': 'lk.chat',
        },
      );
    } catch (e) {
      debugPrint('Error sending message: $e');
      _gatekeeperLogger.logEvent(
        'ui_error',
        sessionId: _room?.name,
        source: 'ui',
        status: 'send_user_message_failed',
        content: text,
        extra: {'error': e.toString()},
      );
      rethrow; // Let caller know
    }
  }

  /// Toggle microphone
  Future<void> setMicrophoneEnabled(bool enabled) async {
    if (_connectionState != SessionConnectionState.connected) {
      log('WARNING: Session not connected, cannot toggle microphone');
      return;
    }
    if (_room?.localParticipant != null) {
      await _room!.localParticipant!.setMicrophoneEnabled(enabled);
      notifyListeners();
    }
  }

  String _loadingStatus = '';
  String get loadingStatus => _loadingStatus;

  void _updateLoadingStatus(String status) {
    _loadingStatus = status;
    notifyListeners();
  }

  /// Connect to LiveKit session
  Future<bool> connect({String? userId, Map<String, dynamic>? clientConfig}) async {
    if (_connectFuture != null) {
      log('Connect already in progress; awaiting current attempt');
      return await _connectFuture!;
    }

    _connectFuture = _connectInternal(userId: userId, clientConfig: clientConfig);
    try {
      return await _connectFuture!;
    } finally {
      _connectFuture = null;
    }
  }

  Future<bool> _connectInternal({String? userId, Map<String, dynamic>? clientConfig}) async {
    if (_connectionState == SessionConnectionState.connected) {
      log('Already connected');
      return true;
    }

    _userRequestedDisconnect = false;
    if (userId != null) _currentUserId = userId;

    _updateConnectionState(SessionConnectionState.connecting);
    _updateLoadingStatus('Initializing system core...');

    final connected = await safeExecute(() async {
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
            'client_role': (clientConfig?['client_role'] ?? 'TRUSTED').toString(),
            'timestamp': DateTime.now().toIso8601String(),
            ...?clientConfig,
          };

          _registerTextStreamHandlers(_room!);
          _registerRoomEventHandlers(_room!);

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

          log('Starting session...');
          _updateLoadingStatus('Establishing uplink...');
          await _session!.start();

          // Wait a moment for the agent to potentially join (optional aesthetic wait)
          _updateLoadingStatus('Synchronizing state...');
          await Future.delayed(const Duration(milliseconds: 800));

          _sessionStartTime = DateTime.now();
          _updateConnectionState(SessionConnectionState.connected);
          _startDeepLinkListener();
          _updateLoadingStatus('System Ready');
          _startGatekeeperAutopilotIfEnabled();

          log('Session connected successfully');
          return true;
        }) ??
        false;

    if (!connected) {
      await _cleanupFailedConnect();
      _updateConnectionState(SessionConnectionState.disconnected);
    }
    return connected;
  }

  Future<void> _cleanupFailedConnect() async {
    try {
      _session?.removeListener(_onSessionChange);
      _room?.removeListener(_onRoomChange);
      await _roomEventListener?.dispose();
      _roomEventListener = null;

      await _session?.dispose();
      if (_room != null && _room!.connectionState == lk.ConnectionState.connected) {
        await _room!.disconnect();
      }
      await _room?.dispose();
    } catch (e) {
      log('⚠️ Cleanup after failed connect hit error: $e');
    } finally {
      _session = null;
      _room = null;
      _sessionStartTime = null;
      _stopGatekeeperAutopilot();
      _stopBackendLivenessWatchdog();
    }
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

  Future<void> sendConfirmationResponse({
    required String traceId,
    required bool confirmed,
  }) async {
    if (_room == null) return;

    final normalizedTraceId = traceId.trim();
    if (normalizedTraceId.isEmpty) return;

    final payload = {
      'type': 'confirmation_response',
      'schema_version': '1.0',
      'trace_id': normalizedTraceId,
      'confirmed': confirmed,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    };

    await _room!.localParticipant?.publishData(
      utf8.encode(jsonEncode(payload)),
      topic: 'maya/system/confirmation/response',
      reliable: true,
    );
    _chatProvider?.resolveConfirmationLocally(
      normalizedTraceId,
      confirmed: confirmed,
    );
  }

  void _applySafeEventFallback({String? reason}) {
    _chatProvider?.updateAgentState(AgentState.idle);
    _gatekeeperLogger.logEvent(
      'chat_event_safe_fallback',
      sessionId: _room?.name,
      source: 'chat_events',
      status: 'fallback_applied',
      extra: {
        'reason': reason ?? 'unknown',
      },
    );
  }

  void _emitAgentUiEvent(AgentUiEvent event) {
    if (_disposed || _agentEventsController.isClosed) {
      return;
    }
    _agentEventsController.add(event);
  }

  void _emitLifecycleEvent(
    String eventType, {
    Map<String, dynamic> payload = const <String, dynamic>{},
    int? timestamp,
  }) {
    _emitAgentUiEvent(
      AgentUiEvent(
        eventType: eventType,
        schemaVersion: AgentEventValidator.expectedSchemaVersion,
        timestamp: timestamp ?? DateTime.now().millisecondsSinceEpoch,
        traceId: payload['trace_id']?.toString(),
        taskId: payload['task_id']?.toString(),
        conversationId: payload['conversation_id']?.toString(),
        originSessionId: currentSessionId ?? '',
        payload: payload,
      ),
    );
  }

  void _routeValidatedChatEvent(AgentUiEvent event) {
    final msg = event.copyWith(originSessionId: currentSessionId ?? '').toMap();
    _emitAgentUiEvent(AgentUiEvent.fromNormalizedMap(msg));
    final type = msg['type']?.toString();
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final isStructuredCardEvent = type == 'research_result' || type == 'media_result' || type == 'system_result';
    if (isStructuredCardEvent) {
      _lastStructuredEventMs = nowMs;
    }
    if (type == 'assistant_final') {
      final recentStructured =
          _lastStructuredEventMs != null && (nowMs - _lastStructuredEventMs!) <= _structuredSuppressWindowMs;
      if (recentStructured) {
        _gatekeeperLogger.logEvent(
          'assistant_final',
          turnId: (msg['turn_id'] ?? msg['turnId'])?.toString(),
          traceId: msg['trace_id']?.toString(),
          sessionId: _room?.name,
          source: 'chat_events',
          status: 'suppressed_after_structured',
          content: msg['content']?.toString(),
        );
        return;
      }
    }
    _gatekeeperLogger.logEvent(
      'chat_event_received',
      turnId: (msg['turn_id'] ?? msg['turnId'])?.toString(),
      traceId: msg['trace_id']?.toString(),
      sessionId: _room?.name,
      source: 'chat_events',
      status: type,
      content: msg['content']?.toString(),
      toolName: (msg['tool_name'] ?? msg['tool'])?.toString(),
    );
    if (type == 'assistant_final' ||
        type == 'assistant_delta' ||
        type == 'research_result' ||
        type == 'media_result' ||
        type == 'system_result' ||
        type == 'confirmation_required') {
      _lastAssistantChatEventAt = DateTime.now();
    }
    _chatProvider?.handleChatEvent(msg);
  }

  void _processDecodedChatEvent(Map<String, dynamic> raw) {
    final validation = AgentEventValidator.validateChatEvent(raw);
    if (validation.status == AgentEventValidationStatus.valid) {
      _routeValidatedChatEvent(validation.validatedEvent!);
    } else if (validation.status == AgentEventValidationStatus.schemaVersionMismatch) {
      _gatekeeperLogger.logEvent(
        'schema_version_mismatch',
        turnId: (raw['turn_id'] ?? raw['turnId'])?.toString(),
        traceId: raw['trace_id']?.toString(),
        sessionId: _room?.name,
        source: 'chat_events',
        status: raw['type']?.toString(),
        extra: {
          'expected_schema_version': AgentEventValidator.expectedSchemaVersion,
          'received_schema_version': validation.receivedSchemaVersion ?? '(missing)',
          'reason': validation.reason ?? 'schema_mismatch',
        },
      );
      if (validation.canRoute) {
        _routeValidatedChatEvent(validation.validatedEvent!);
      } else {
        _applySafeEventFallback(reason: validation.reason);
      }
    } else if (validation.status == AgentEventValidationStatus.unknownType) {
      _gatekeeperLogger.logEvent(
        'unknown_event_type',
        turnId: (raw['turn_id'] ?? raw['turnId'])?.toString(),
        traceId: raw['trace_id']?.toString(),
        sessionId: _room?.name,
        source: 'chat_events',
        status: raw['type']?.toString(),
        extra: {'reason': validation.reason ?? 'unknown_type'},
      );
    } else {
      _gatekeeperLogger.logEvent(
        'ui_error',
        turnId: (raw['turn_id'] ?? raw['turnId'])?.toString(),
        traceId: raw['trace_id']?.toString(),
        sessionId: _room?.name,
        source: 'chat_events',
        status: 'validation_failed',
        extra: {
          'reason': validation.reason ?? 'invalid_payload',
          'event_type': raw['type']?.toString(),
        },
      );
      _applySafeEventFallback(reason: validation.reason ?? 'invalid_payload');
    }
  }

  @visibleForTesting
  void processChatEventPayloadForTesting(Map<String, dynamic> raw) {
    _processDecodedChatEvent(raw);
  }

  @visibleForTesting
  void updateConnectionStateForTesting(SessionConnectionState state) {
    _updateConnectionState(state);
  }

  @visibleForTesting
  void handleBootstrapAckForTesting(Map<String, dynamic> msg) {
    _handleBootstrapAck(msg);
  }

  @visibleForTesting
  Future<bool> waitForBootstrapAckForTesting({
    required String conversationId,
    required int bootstrapVersion,
    Duration timeout = const Duration(seconds: 2),
  }) async {
    _bootstrapAckCompleter = Completer<bool>();
    _pendingBootstrapConversationId = conversationId;
    _pendingBootstrapVersion = bootstrapVersion;
    _emitLifecycleEvent(
      'bootstrap_started',
      payload: <String, dynamic>{
        'conversation_id': conversationId,
        'bootstrap_version': bootstrapVersion,
      },
    );

    try {
      return await _bootstrapAckCompleter!.future.timeout(
        timeout,
        onTimeout: () {
          _emitLifecycleEvent(
            'bootstrap_timeout',
            payload: <String, dynamic>{
              'conversation_id': conversationId,
              'bootstrap_version': bootstrapVersion,
            },
          );
          if (_bootstrapAckCompleter != null && !_bootstrapAckCompleter!.isCompleted) {
            _bootstrapAckCompleter!.complete(false);
          }
          _bootstrapAckCompleter = null;
          _pendingBootstrapConversationId = null;
          _pendingBootstrapVersion = null;
          return false;
        },
      );
    } catch (_) {
      _bootstrapAckCompleter = null;
      _pendingBootstrapConversationId = null;
      _pendingBootstrapVersion = null;
      return false;
    }
  }

  @visibleForTesting
  void processAgentResponsePayloadForTesting(String payload) {
    final now = DateTime.now();
    final recentAssistantChatEvent =
        _lastAssistantChatEventAt != null && now.difference(_lastAssistantChatEventAt!).inMilliseconds < 3000;
    if (!recentAssistantChatEvent) {
      _forwardAssistantPayloadToChat(payload);
    }
  }

  void _onDataReceived(lk.DataReceivedEvent event) {
    if (event.topic == 'maya/system/bootstrap/ack') {
      try {
        final jsonStr = utf8.decode(event.data);
        final msg = jsonDecode(jsonStr);
        if (msg is Map) {
          _handleBootstrapAck(msg.cast<String, dynamic>());
        }
      } catch (e) {
        log('Error parsing bootstrap ack: $e');
      }
      notifyListeners();
      return;
    }

    if (event.topic == 'chat_events') {
      try {
        final jsonStr = utf8.decode(event.data);
        final decoded = jsonDecode(jsonStr);
        if (decoded is! Map) {
          _applySafeEventFallback(reason: 'decoded_not_map');
          notifyListeners();
          return;
        }

        final raw = decoded.cast<String, dynamic>();
        _processDecodedChatEvent(raw);
      } catch (e) {
        log('Error parsing chat event: $e');
        _gatekeeperLogger.logEvent(
          'ui_error',
          sessionId: _room?.name,
          source: 'chat_events',
          status: 'parse_failed',
          extra: {'error': e.toString()},
        );
      }
    }

    if (event.topic == 'system.events') {
      try {
        final jsonStr = utf8.decode(event.data);
        final msg = jsonDecode(jsonStr);
        _routeSystemMessage(msg);
      } catch (e) {
        log('Error parsing system event: $e');
        _gatekeeperLogger.logEvent(
          'ui_error',
          sessionId: _room?.name,
          source: 'system.events',
          status: 'parse_failed',
          extra: {'error': e.toString()},
        );
      }
    }
    // Also notify for generic chat/data updates
    notifyListeners();
  }

  void _routeSystemMessage(Map msg) {
    final msgType = msg['type']?.toString() ?? '';
    log('📥 RECEIVED SYSTEM MSG: $msgType / ${msg['category']}');

    if (msgType == 'agent_heartbeat') {
      _markBackendHeartbeat();
      return;
    }

    if (msgType == 'spotify_connected') {
      final connected = msg['connected'] == true;
      final displayName = msg['display_name']?.toString();
      _chatProvider?.updateSpotifyStatus(
        connected: connected,
        displayName: displayName,
      );
      return;
    }

    if (msgType == 'spotify_auth_url') {
      final rawUrl = msg['url']?.toString() ?? '';
      if (rawUrl.isNotEmpty) {
        final uri = Uri.tryParse(rawUrl);
        if (uri != null) {
          unawaited(launchUrl(uri, mode: LaunchMode.externalApplication));
        }
      }
      return;
    }

    if (msgType == 'spotify_error') {
      _chatProvider?.handleChatEvent({
        'type': 'error',
        'message': msg['message']?.toString() ?? 'Spotify operation failed.',
        'timestamp': DateTime.now().millisecondsSinceEpoch,
      });
    }
  }

  void _handleBootstrapAck(Map<String, dynamic> msg) {
    final conversationId = (msg['conversation_id'] ?? '').toString();
    final bootstrapVersion = msg['bootstrap_version'] is int
        ? msg['bootstrap_version'] as int
        : int.tryParse((msg['bootstrap_version'] ?? '').toString());
    final applied = msg['applied'] == true;
    if (!applied) {
      return;
    }
    if (_bootstrapAckCompleter == null || _bootstrapAckCompleter!.isCompleted) {
      return;
    }
    if (_pendingBootstrapConversationId != null && conversationId != _pendingBootstrapConversationId) {
      return;
    }
    if (_pendingBootstrapVersion != null && bootstrapVersion != _pendingBootstrapVersion) {
      return;
    }
    _emitLifecycleEvent(
      'bootstrap_acknowledged',
      payload: <String, dynamic>{
        'conversation_id': conversationId,
        'bootstrap_version': bootstrapVersion,
        'applied': true,
      },
    );
    _bootstrapAckCompleter?.complete(true);
    _bootstrapAckCompleter = null;
    _pendingBootstrapConversationId = null;
    _pendingBootstrapVersion = null;
  }

  void _markBackendHeartbeat() {
    _lastBackendHeartbeatAt = DateTime.now();
  }

  void _startBackendLivenessWatchdog() {
    _stopBackendLivenessWatchdog();
    _markBackendHeartbeat();
    _backendLivenessTimer = Timer.periodic(_backendHeartbeatProbeInterval, (_) {
      unawaited(_runBackendLivenessCheck());
    });
  }

  void _stopBackendLivenessWatchdog() {
    _backendLivenessTimer?.cancel();
    _backendLivenessTimer = null;
  }

  Future<bool> _probeLocalBackendHealth() async {
    const urls = ['http://127.0.0.1:5050/health', 'http://localhost:5050/health'];
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);

    try {
      for (final rawUrl in urls) {
        try {
          final request = await client.getUrl(Uri.parse(rawUrl));
          final response = await request.close().timeout(const Duration(seconds: 2));
          await response.drain();
          if (response.statusCode == 200) {
            return true;
          }
        } catch (_) {
          // Try the next endpoint.
        }
      }
      return false;
    } finally {
      client.close(force: true);
    }
  }

  Future<void> _runBackendLivenessCheck() async {
    if (_disposed ||
        _backendDisconnectInProgress ||
        _room == null ||
        (_connectionState != SessionConnectionState.connected &&
            _connectionState != SessionConnectionState.reconnecting)) {
      return;
    }

    final lastHeartbeat = _lastBackendHeartbeatAt;
    if (lastHeartbeat == null) {
      _markBackendHeartbeat();
      return;
    }
    if (DateTime.now().difference(lastHeartbeat) <= _backendHeartbeatTimeout) {
      return;
    }

    final healthOk = await _probeLocalBackendHealth();
    if (healthOk) {
      _markBackendHeartbeat();
      return;
    }

    await _forceDisconnectBackendUnreachable();
  }

  Future<void> _forceDisconnectBackendUnreachable() async {
    if (_backendDisconnectInProgress || _disposed) return;
    _backendDisconnectInProgress = true;
    try {
      log('⚠️ Backend unreachable; forcing disconnected state');
      _emitLifecycleEvent(
        'session_disconnected',
        payload: <String, dynamic>{'reason': 'backend_unreachable'},
      );
      await disconnect();
      _userRequestedDisconnect = false;
      _overlayController?.setReconnectPromptVisible(_shouldShowReconnectPrompt(_connectionState));
      notifyListeners();
    } finally {
      _backendDisconnectInProgress = false;
    }
  }

  void _startDeepLinkListener() {
    unawaited(_deepLinkSubscription?.cancel());
    _deepLinkSubscription = _appLinks.uriLinkStream.listen((uri) {
      if (uri.scheme != 'maya') return;
      if (uri.host != 'spotify') return;
      final code = uri.queryParameters['code']?.trim();
      if (code == null || code.isEmpty) return;
      unawaited(sendCommand('spotify_auth_code', {
        'platform': 'mobile',
        'code': code,
      }));
    });
  }

  void _forwardAssistantPayloadToChat(String payload) {
    final text = payload.trim();
    if (text.isEmpty) return;

    try {
      final decoded = jsonDecode(text);
      if (decoded is Map<String, dynamic>) {
        final type = decoded['type']?.toString();
        if (type == 'assistant_final' || type == 'assistant_delta') {
          _chatProvider?.handleChatEvent(decoded);
          return;
        }
      } else if (decoded is Map) {
        final map = decoded.cast<String, dynamic>();
        final type = map['type']?.toString();
        if (type == 'assistant_final' || type == 'assistant_delta') {
          _chatProvider?.handleChatEvent(map);
          return;
        }
      }
    } catch (_) {
      // Plain-text assistant payload; fall through to synthetic final event.
    }

    _chatProvider?.handleChatEvent({
      'type': 'assistant_final',
      'turn_id': 'stream_${DateTime.now().microsecondsSinceEpoch}',
      'content': text,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    });
  }

  void _registerTextStreamHandlers(lk.Room room) {
    room.registerTextStreamHandler('lk.agent.events', (reader, participantIdentity) async {
      try {
        final payload = await reader.readAll();
        final parsed = jsonDecode(payload);
        if (parsed is Map<String, dynamic>) {
          _lastAgentMetaEvent = {
            ...parsed,
            'participant': participantIdentity,
            'topic': 'lk.agent.events',
          };
          log('📥 AGENT EVENT: ${parsed['type']} from $participantIdentity');
          _gatekeeperLogger.logEvent(
            'chat_event_received',
            turnId: (parsed['turn_id'] ?? parsed['turnId'])?.toString(),
            traceId: parsed['trace_id']?.toString(),
            sessionId: _room?.name,
            source: 'lk.agent.events',
            status: parsed['type']?.toString(),
            content: parsed['content']?.toString(),
            toolName: parsed['tool']?.toString(),
          );
        } else {
          _lastAgentMetaEvent = {
            'type': 'lk_agent_event_raw',
            'payload': payload,
            'participant': participantIdentity,
            'topic': 'lk.agent.events',
          };
          log('📥 AGENT EVENT RAW from $participantIdentity');
        }
        notifyListeners();
      } catch (e) {
        log('Error handling lk.agent.events stream: $e');
        _gatekeeperLogger.logEvent(
          'ui_error',
          sessionId: _room?.name,
          source: 'lk.agent.events',
          status: 'stream_handler_failed',
          extra: {'error': e.toString()},
        );
      }
    });

    room.registerTextStreamHandler('lk.agent.response', (reader, participantIdentity) async {
      try {
        final payload = await reader.readAll();
        _lastAgentEvent = {
          'type': 'lk_agent_response',
          'payload': payload,
          'participant': participantIdentity,
          'topic': 'lk.agent.response',
        };
        log('📥 AGENT RESPONSE STREAM from $participantIdentity');
        // Prefer structured chat_events for rendering. Forward this stream only as
        // a fallback when chat_events assistant packets are not arriving.
        // Prefer structured cards for a longer window to avoid duplicate plain text bubbles.
        final now = DateTime.now();
        final nowMs = now.millisecondsSinceEpoch;
        final recentAssistantChatEvent =
            _lastAssistantChatEventAt != null && now.difference(_lastAssistantChatEventAt!).inMilliseconds < 3000;
        final recentStructuredCard =
            _lastStructuredEventMs != null && (nowMs - _lastStructuredEventMs!) <= _structuredSuppressWindowMs;
        if (!recentAssistantChatEvent && !recentStructuredCard) {
          _forwardAssistantPayloadToChat(payload);
        } else {
          log('Skipping lk.agent.response fallback - recent chat_event detected');
        }
        _gatekeeperLogger.logEvent(
          'chat_event_received',
          sessionId: _room?.name,
          source: 'lk.agent.response',
          status: 'payload',
          content: payload,
          extra: {'participant': participantIdentity},
        );
        notifyListeners();
      } catch (e) {
        log('Error handling lk.agent.response stream: $e');
        _gatekeeperLogger.logEvent(
          'ui_error',
          sessionId: _room?.name,
          source: 'lk.agent.response',
          status: 'stream_handler_failed',
          extra: {'error': e.toString()},
        );
      }
    });
  }

  void _registerRoomEventHandlers(lk.Room room) {
    if (_roomEventListener != null) {
      unawaited(_roomEventListener!.dispose());
    }
    _roomEventListener = room.createListener()
      ..on<lk.DataReceivedEvent>(_onDataReceived)
      ..on<lk.RoomConnectedEvent>((event) {
        _emitLifecycleEvent(
          'session_connected',
          payload: <String, dynamic>{
            'metadata': event.metadata,
          },
        );
      })
      ..on<lk.RoomDisconnectedEvent>((event) {
        _emitLifecycleEvent(
          'session_disconnected',
          payload: <String, dynamic>{
            'reason': event.reason?.name,
          },
        );
      })
      ..on<lk.RoomReconnectingEvent>((_) {
        _emitLifecycleEvent('session_reconnecting');
      })
      ..on<lk.TrackSubscribedEvent>((event) {
        _emitLifecycleEvent(
          'track_subscribed',
          payload: <String, dynamic>{
            'participant_identity': event.participant.identity,
            'participant_sid': event.participant.sid,
            'track_sid': event.track.sid,
          },
        );
      })
      ..on<lk.ActiveSpeakersChangedEvent>((event) {
        final hasLocalSpeaker = event.speakers.any((participant) => participant is lk.LocalParticipant);
        final hasRemoteSpeaker = event.speakers.any((participant) => participant is lk.RemoteParticipant);
        _emitLifecycleEvent(hasLocalSpeaker ? 'user_speaking' : 'user_silence');
        _emitLifecycleEvent(
          hasRemoteSpeaker ? 'agent_speaking' : 'agent_idle',
          payload: <String, dynamic>{
            'status': hasRemoteSpeaker ? 'speaking' : 'idle',
          },
        );
      })
      ..on<lk.TranscriptionEvent>((event) {
        _chatProvider?.addTranscription(event);
      });
  }

  /// Disconnect from session
  Future<void> disconnect() async {
    _userRequestedDisconnect = true;
    _stopGatekeeperAutopilot();
    _stopBackendLivenessWatchdog();
    if (_bootstrapAckCompleter != null && !_bootstrapAckCompleter!.isCompleted) {
      _bootstrapAckCompleter!.complete(false);
    }
    _bootstrapAckCompleter = null;
    _pendingBootstrapConversationId = null;
    _pendingBootstrapVersion = null;

    if (_connectionState == SessionConnectionState.disconnected) {
      log('Already disconnected');
      return;
    }

    _updateConnectionState(SessionConnectionState.disconnecting);

    await safeExecute(() async {
      log('Disconnecting from session...');

      _session?.removeListener(_onSessionChange);
      _room?.removeListener(_onRoomChange);
      await _roomEventListener?.dispose();
      _roomEventListener = null;

      await _session?.dispose();

      // Safety check before room disposal
      if (_room != null && _room!.connectionState == lk.ConnectionState.connected) {
        await _room!.disconnect();
      }
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
      final newState = _mapLiveKitState(_room!.connectionState);

      // Intercept unintential disconnects
      if (newState == SessionConnectionState.disconnected && !_userRequestedDisconnect) {
        log('⚠️ Unintentional disconnect detected. Attempting auto-reconnect.');
        unawaited(_attemptAutoReconnect());
      }

      _updateConnectionState(newState);
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

  void _updateConnectionState(SessionConnectionState state) {
    if (_connectionState != state && !_disposed) {
      _connectionState = state;
      if (state == SessionConnectionState.connected) {
        _hasEverConnected = true;
        _startBackendLivenessWatchdog();
      }
      _overlayController?.setReconnectPromptVisible(_shouldShowReconnectPrompt(state));
      log('Connection state: $state');
      switch (state) {
        case SessionConnectionState.connected:
          _emitLifecycleEvent('session_connected');
          break;
        case SessionConnectionState.disconnected:
          _emitLifecycleEvent('session_disconnected');
          break;
        case SessionConnectionState.reconnecting:
          _emitLifecycleEvent('session_reconnecting');
          break;
        case SessionConnectionState.connecting:
        case SessionConnectionState.disconnecting:
          break;
      }
      if (state != SessionConnectionState.connected) {
        _stopGatekeeperAutopilot();
        _stopBackendLivenessWatchdog();
      }
      _gatekeeperLogger.logEvent(
        'session_connection_state',
        sessionId: _room?.name,
        source: 'ui',
        status: state.name,
        extra: {'user_id': _currentUserId},
      );
      notifyListeners();
    }
  }

  Future<void> _attemptAutoReconnect() async {
    if (_disposed || _userRequestedDisconnect || _autoReconnectInProgress) {
      return;
    }
    if (_connectFuture != null) {
      log('Auto-reconnect skipped: connect already in progress');
      return;
    }

    final userId = _currentUserId;
    if (userId == null || userId.isEmpty) {
      log('⚠️ Auto-reconnect skipped: missing user id');
      return;
    }

    if (_autoReconnectAttempts >= _maxAutoReconnectAttempts) {
      log('⚠️ Auto-reconnect exhausted ($_autoReconnectAttempts/$_maxAutoReconnectAttempts)');
      return;
    }

    _autoReconnectInProgress = true;
    _autoReconnectAttempts += 1;

    try {
      final delayMs = 800 * _autoReconnectAttempts;
      _updateConnectionState(SessionConnectionState.reconnecting);
      log('🔄 Auto-reconnect attempt $_autoReconnectAttempts/$_maxAutoReconnectAttempts in ${delayMs}ms');
      await Future.delayed(Duration(milliseconds: delayMs));

      if (_disposed || _userRequestedDisconnect) {
        return;
      }

      _session?.removeListener(_onSessionChange);
      _room?.removeListener(_onRoomChange);
      await _roomEventListener?.dispose();
      _roomEventListener = null;

      await _session?.dispose();
      if (_room != null && _room!.connectionState == lk.ConnectionState.connected) {
        await _room!.disconnect();
      }
      await _room?.dispose();

      _session = null;
      _room = null;

      final connected = await connect(userId: userId);
      if (connected) {
        log('✅ Auto-reconnect successful');
        _autoReconnectAttempts = 0;
      } else {
        log('⚠️ Auto-reconnect failed to restore session');
      }
    } catch (e) {
      log('⚠️ Auto-reconnect attempt failed: $e');
    } finally {
      _autoReconnectInProgress = false;
    }
  }

  Future<bool> reconnectWithMetadata({
    String? userId,
    Map<String, dynamic>? clientConfig,
  }) async {
    if (_connectionState != SessionConnectionState.disconnected) {
      await disconnect();
    }
    return await connect(
      userId: userId ?? _currentUserId,
      clientConfig: clientConfig,
    );
  }

  Future<bool> sendBootstrapContext({
    required Map<String, dynamic> payload,
    required String conversationId,
    required int bootstrapVersion,
    bool waitForAck = true,
  }) async {
    if (_room == null) {
      return false;
    }

    if (waitForAck) {
      _bootstrapAckCompleter = Completer<bool>();
      _pendingBootstrapConversationId = conversationId;
      _pendingBootstrapVersion = bootstrapVersion;
    }

    _emitLifecycleEvent(
      'bootstrap_started',
      payload: <String, dynamic>{
        'conversation_id': conversationId,
        'bootstrap_version': bootstrapVersion,
      },
    );
    await sendCommand('bootstrap_context', payload);
    if (!waitForAck) {
      return true;
    }

    try {
      return await _bootstrapAckCompleter!.future.timeout(
        const Duration(seconds: 2),
        onTimeout: () {
          _emitLifecycleEvent(
            'bootstrap_timeout',
            payload: <String, dynamic>{
              'conversation_id': conversationId,
              'bootstrap_version': bootstrapVersion,
            },
          );
          if (_bootstrapAckCompleter != null && !_bootstrapAckCompleter!.isCompleted) {
            _bootstrapAckCompleter!.complete(false);
          }
          _bootstrapAckCompleter = null;
          _pendingBootstrapConversationId = null;
          _pendingBootstrapVersion = null;
          return false;
        },
      );
    } catch (_) {
      _bootstrapAckCompleter = null;
      _pendingBootstrapConversationId = null;
      _pendingBootstrapVersion = null;
      return false;
    }
  }

  void _startGatekeeperAutopilotIfEnabled() {
    if (!_gatekeeperAutopilotEnabled) return;
    _stopGatekeeperAutopilot();
    _gatekeeperPolling = false;
    _gatekeeperCommandOffset = 0;
    _lastGatekeeperCommandId = null;

    final commandFile = File(_gatekeeperCommandPath);
    try {
      if (commandFile.existsSync()) {
        _gatekeeperCommandOffset = commandFile.lengthSync();
      }
    } catch (_) {
      _gatekeeperCommandOffset = 0;
    }

    _gatekeeperLogger.logEvent(
      'autopilot_status',
      sessionId: _room?.name,
      source: 'gatekeeper_autopilot',
      status: 'started',
      extra: {'command_path': _gatekeeperCommandPath},
    );

    _gatekeeperCommandPoller = Timer.periodic(const Duration(milliseconds: 250), (_) {
      unawaited(_pollGatekeeperCommands());
    });
  }

  void _stopGatekeeperAutopilot() {
    if (_gatekeeperCommandPoller != null) {
      _gatekeeperCommandPoller?.cancel();
      _gatekeeperCommandPoller = null;
      _gatekeeperLogger.logEvent(
        'autopilot_status',
        sessionId: _room?.name,
        source: 'gatekeeper_autopilot',
        status: 'stopped',
      );
    }
    _gatekeeperPolling = false;
  }

  Future<void> _pollGatekeeperCommands() async {
    if (!_gatekeeperAutopilotEnabled || _gatekeeperPolling || !isConnected || _room == null) {
      return;
    }

    _gatekeeperPolling = true;
    try {
      final commandFile = File(_gatekeeperCommandPath);
      if (!await commandFile.exists()) return;

      final fileLen = await commandFile.length();
      if (fileLen < _gatekeeperCommandOffset) {
        _gatekeeperCommandOffset = 0;
      }
      if (fileLen == _gatekeeperCommandOffset) return;

      final raf = await commandFile.open(mode: FileMode.read);
      try {
        await raf.setPosition(_gatekeeperCommandOffset);
        final bytes = await raf.read(fileLen - _gatekeeperCommandOffset);
        _gatekeeperCommandOffset = fileLen;
        final chunk = utf8.decode(bytes, allowMalformed: true);
        for (final raw in chunk.split('\n')) {
          final line = raw.trim();
          if (line.isEmpty) continue;
          Map<String, dynamic> cmd;
          try {
            final parsed = jsonDecode(line);
            if (parsed is! Map) continue;
            cmd = parsed.cast<String, dynamic>();
          } catch (_) {
            continue;
          }

          if ((cmd['type'] ?? '').toString() != 'send_prompt') continue;

          final commandId = (cmd['id'] ?? '').toString();
          final prompt = (cmd['prompt'] ?? '').toString().trim();
          if (prompt.isEmpty) continue;
          if (commandId.isNotEmpty && commandId == _lastGatekeeperCommandId) continue;

          _lastGatekeeperCommandId = commandId.isEmpty ? null : commandId;
          _gatekeeperLogger.logEvent(
            'autopilot_prompt_received',
            sessionId: _room?.name,
            source: 'gatekeeper_autopilot',
            status: 'sending',
            content: prompt,
            extra: {'command_id': commandId},
          );
          await sendUserMessage(prompt);
          _gatekeeperLogger.logEvent(
            'autopilot_prompt_sent',
            sessionId: _room?.name,
            source: 'gatekeeper_autopilot',
            status: 'sent',
            content: prompt,
            extra: {'command_id': commandId},
          );
        }
      } finally {
        await raf.close();
      }
    } catch (e) {
      _gatekeeperLogger.logEvent(
        'ui_error',
        sessionId: _room?.name,
        source: 'gatekeeper_autopilot',
        status: 'poll_failed',
        extra: {'error': e.toString()},
      );
    } finally {
      _gatekeeperPolling = false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _stopGatekeeperAutopilot();
    _stopBackendLivenessWatchdog();
    unawaited(_deepLinkSubscription?.cancel());
    if (_bootstrapAckCompleter != null && !_bootstrapAckCompleter!.isCompleted) {
      _bootstrapAckCompleter!.complete(false);
    }
    if (_roomEventListener != null) {
      unawaited(_roomEventListener!.dispose());
    }
    _roomEventListener = null;
    unawaited(_agentEventsController.close());
    unawaited(disconnect());
    super.dispose();
  }
}
