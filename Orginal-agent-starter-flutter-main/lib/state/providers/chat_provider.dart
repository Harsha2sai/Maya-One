import 'dart:async';
import 'package:livekit_client/livekit_client.dart' as lk;
import '../controllers/overlay_controller.dart';
import '../models/overlay_models.dart';
import '../base_provider.dart';
import '../../core/services/assistant_content_normalizer.dart';
import '../../core/services/gatekeeper_event_logger.dart';
import '../../core/services/search_cue_service.dart';
import '../models/conversation_models.dart';

enum AgentState { idle, listening, thinking, callingTools, searchingWeb, writingResponse }

class Source {
  final String title;
  final String url;
  final String domain;
  final String? snippet;
  final String? provider;

  const Source({
    required this.title,
    required this.url,
    this.domain = '',
    this.snippet,
    this.provider,
  });

  factory Source.fromJson(Map<String, dynamic> json) {
    return Source(
      title: json['title']?.toString() ?? 'Source',
      url: json['url']?.toString() ?? '',
      domain: json['domain']?.toString() ?? '',
      snippet: json['snippet']?.toString(),
      provider: json['provider']?.toString(),
    );
  }
}

/// Source of a chat message - used for deduplication and priority handling
enum MessageSource {
  transcription, // From LiveKit TranscriptionEvent
  structured, // From chat_events data channel
  local, // Locally created (user input)
}

class ChatMessage {
  final String id;
  final String content;
  final DateTime timestamp;
  final bool isUser;
  final bool isAgent;
  final List<String> attachmentUrls;
  final List<Source> sources;
  final MessageSource source;
  final String? turnId; // Canonical turn identifier for deduplication
  final bool isLive; // True for streaming/in-progress messages
  final String? eventType;
  final Map<String, dynamic> payload;
  final String originSessionId;

  ChatMessage({
    required this.id,
    required this.content,
    required this.timestamp,
    required this.isUser,
    required this.isAgent,
    this.attachmentUrls = const [],
    this.sources = const [],
    this.source = MessageSource.local,
    this.turnId,
    this.isLive = false,
    this.eventType,
    this.payload = const {},
    this.originSessionId = '',
  });

  @override
  String toString() =>
      'ChatMessage(id: $id, turnId: $turnId, source: $source, isLive: $isLive, content: ${content.length > 30 ? "${content.substring(0, 30)}..." : content})';
}

class ChatProvider extends BaseProvider {
  static const String _assistantLiveMessageId = 'trans_assistant_live';
  static const String _safeErrorText = 'I ran into an issue while processing that. Please try again.';
  final List<ChatMessage> _messages = [];
  final Map<String, StringBuffer> _assistantDeltaBuffers = {};

  // Unified duplicate tracking - track content hashes regardless of turnId
  final Map<String, String> _assistantContentByTurn = {};
  final Map<String, DateTime> _assistantContentTimestamps = {};
  String _lastAssistantText = '';
  DateTime? _lastAssistantTextAt;
  final Map<String, DateTime> _structuredSuppressionByTurn = {};
  static const Duration _structuredSuppressionWindow = Duration(seconds: 8);
  DateTime Function() _now = DateTime.now;

  static const int _contentHashExpirySeconds = 10;

  bool _isTyping = false;
  AgentState _agentState = AgentState.idle;
  String? _currentTool;
  bool _spotifyConnected = false;
  String? _spotifyDisplayName;
  Timer? _thinkingResetTimer;
  final Map<String, Map<String, dynamic>> _activeToolExecutions = {};
  final List<ConversationToolResultSummary> _recentToolResults = [];
  final GatekeeperEventLogger _gatekeeperLogger = GatekeeperEventLogger.instance;
  OverlayController? _overlayController;
  SearchCueService? _searchCueService;
  bool _soundEffectsEnabled;

  ChatProvider({
    SearchCueService? searchCueService,
    bool soundEffectsEnabled = true,
  })  : _searchCueService = searchCueService,
        _soundEffectsEnabled = soundEffectsEnabled,
        super('ChatProvider');

  void bindOverlayController(OverlayController overlay) {
    _overlayController = overlay;
  }

  void bindSearchCueService(SearchCueService service) {
    _searchCueService = service;
  }

  void bindSoundEffectsPreference(bool enabled) {
    _soundEffectsEnabled = enabled;
  }

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  bool get isTyping => _isTyping;
  AgentState get agentState => _agentState;
  String? get currentTool => _currentTool;
  bool get spotifyConnected => _spotifyConnected;
  String? get spotifyDisplayName => _spotifyDisplayName;
  List<ConversationToolResultSummary> get recentToolResults => List.unmodifiable(_recentToolResults);
  bool get hasMessages => _messages.isNotEmpty;
  bool get isAgentThinking => _agentState != AgentState.idle && _agentState != AgentState.listening;
  bool get hasAnyLiveAssistantMessage => _messages.any((m) => m.isAgent && m.isLive);
  bool get hasActiveLiveTranscriptionMessage =>
      _messages.any((m) => m.isAgent && m.isLive && m.id == _assistantLiveMessageId);
  bool get hasActiveToolExecution => _activeToolExecutions.isNotEmpty;

  void _cancelThinkingReset() {
    _thinkingResetTimer?.cancel();
    _thinkingResetTimer = null;
  }

  void _scheduleThinkingReset({Duration timeout = const Duration(seconds: 20)}) {
    _cancelThinkingReset();
    _thinkingResetTimer = Timer(timeout, () {
      _agentState = AgentState.idle;
      _currentTool = null;
      _isTyping = false;
      notifyListeners();
    });
  }

  void _upsertMessage(ChatMessage message, {bool preferEnd = false}) {
    final idx = _messages.indexWhere((m) => m.id == message.id);
    if (idx != -1) {
      // Update existing message, preserve original timestamp
      final existing = _messages[idx];
      _messages[idx] = ChatMessage(
        id: message.id,
        content: message.content,
        timestamp: existing.timestamp,
        isUser: message.isUser,
        isAgent: message.isAgent,
        attachmentUrls: message.attachmentUrls,
        sources: message.sources.isNotEmpty ? message.sources : existing.sources,
        source: message.source,
        turnId: message.turnId,
        isLive: message.isLive,
        eventType: message.eventType ?? existing.eventType,
        payload: message.payload.isNotEmpty ? message.payload : existing.payload,
        originSessionId: message.originSessionId.isNotEmpty ? message.originSessionId : existing.originSessionId,
      );
    } else {
      // Insert new messages
      // Live messages always go at the end (newest position)
      // Final messages are inserted in chronological order but after any live messages
      if (preferEnd || message.isLive) {
        _messages.add(message);
      } else {
        // Find correct position: after all live messages, in timestamp order
        int insertAt = _messages.length;
        for (int i = _messages.length - 1; i >= 0; i--) {
          if (_messages[i].isLive) {
            // Live messages should be after final messages
            insertAt = i + 1;
            break;
          }
          if (_messages[i].timestamp.isAfter(message.timestamp)) {
            insertAt = i;
          }
        }
        if (insertAt == _messages.length) {
          _messages.add(message);
        } else {
          _messages.insert(insertAt, message);
        }
      }
    }
    log('Message upserted: $message');
  }

  void _removeMessageById(String id) {
    _messages.removeWhere((m) => m.id == id);
  }

  String _originSessionId(Map<String, dynamic> event) {
    return (event['origin_session_id'] ?? '').toString();
  }

  ConversationSourceChannel _sourceChannelForMessage(ChatMessage message) {
    switch (message.source) {
      case MessageSource.transcription:
        return ConversationSourceChannel.voice;
      case MessageSource.structured:
        return ConversationSourceChannel.structured;
      case MessageSource.local:
        return ConversationSourceChannel.typed;
    }
  }

  MessageSource _messageSourceFromSnapshot(ConversationMessageSnapshot snapshot) {
    switch (snapshot.sourceChannel) {
      case ConversationSourceChannel.voice:
        return MessageSource.transcription;
      case ConversationSourceChannel.structured:
        return MessageSource.structured;
      case ConversationSourceChannel.typed:
        return MessageSource.local;
    }
  }

  ConversationMessageType _messageTypeForChatMessage(ChatMessage message) {
    switch (message.eventType) {
      case 'research_result':
        return ConversationMessageType.researchResult;
      case 'confirmation_required':
        return ConversationMessageType.confirmationRequired;
      case 'system_result':
        return ConversationMessageType.systemResult;
      case 'media_result':
        return ConversationMessageType.mediaResult;
      case 'error':
        return ConversationMessageType.error;
      case 'status':
        return ConversationMessageType.status;
      default:
        return ConversationMessageType.text;
    }
  }

  ConversationMessageRole _messageRoleForChatMessage(ChatMessage message) {
    if (message.isUser) {
      return ConversationMessageRole.user;
    }
    if (message.eventType == 'system_result' ||
        message.eventType == 'media_result' ||
        message.eventType == 'confirmation_required') {
      return ConversationMessageRole.system;
    }
    return ConversationMessageRole.assistant;
  }

  List<ConversationSourceItem> _snapshotSources(List<Source> sources) {
    return sources
        .map(
          (source) => ConversationSourceItem(
            title: source.title,
            url: source.url,
            domain: source.domain,
            snippet: source.snippet ?? '',
            provider: source.provider ?? '',
          ),
        )
        .toList();
  }

  List<Source> _hydrateSources(List<ConversationSourceItem> sources) {
    return sources
        .map(
          (source) => Source(
            title: source.title,
            url: source.url,
            domain: source.domain,
            snippet: source.snippet,
            provider: source.provider,
          ),
        )
        .toList();
  }

  String _normalizePersistedMessageContent(ChatMessage message) {
    if (message.isAgent || message.eventType == 'research_result') {
      return normalizeAssistantContent(message.content);
    }
    return message.content;
  }

  ConversationMessageSnapshot _postProcessSnapshot(ConversationMessageSnapshot snapshot) {
    if (snapshot.role == ConversationMessageRole.assistant && snapshot.messageType == ConversationMessageType.text) {
      return snapshot.copyWith(content: normalizeAssistantContent(snapshot.content));
    }
    if (snapshot.messageType == ConversationMessageType.researchResult) {
      return snapshot.copyWith(content: normalizeAssistantContent(snapshot.content));
    }
    return snapshot;
  }

  void _recordToolResultSummary({
    required String toolName,
    required String summary,
    required DateTime timestamp,
    String? taskId,
  }) {
    final trimmedTool = toolName.trim();
    final trimmedSummary = summary.trim();
    if (trimmedTool.isEmpty || trimmedSummary.isEmpty) {
      return;
    }
    _recentToolResults.insert(
      0,
      ConversationToolResultSummary(
        toolName: trimmedTool,
        summary: trimmedSummary,
        timestamp: timestamp,
        taskId: taskId,
      ),
    );
    if (_recentToolResults.length > 10) {
      _recentToolResults.removeRange(10, _recentToolResults.length);
    }
  }

  String _toolExecutionKey({
    required String turnId,
    required String toolName,
    String? taskId,
  }) {
    if (taskId != null && taskId.trim().isNotEmpty) {
      return 'task:${taskId.trim()}';
    }
    return '$turnId:$toolName';
  }

  List<ConversationMessageSnapshot> snapshotMessages({required String originSessionId}) {
    return _messages.where((message) => !message.isLive).map((message) {
      return ConversationMessageSnapshot(
        id: message.id,
        role: _messageRoleForChatMessage(message),
        messageType: _messageTypeForChatMessage(message),
        content: _normalizePersistedMessageContent(message),
        timestamp: message.timestamp,
        attachmentUrls: List<String>.from(message.attachmentUrls),
        sources: _snapshotSources(message.sources),
        turnId: message.turnId,
        payload: Map<String, dynamic>.from(message.payload),
        sourceChannel: _sourceChannelForMessage(message),
        originSessionId: message.originSessionId.isNotEmpty ? message.originSessionId : originSessionId,
      );
    }).toList();
  }

  void replaceMessages(List<ChatMessage> messages) {
    _messages
      ..clear()
      ..addAll(messages);
    notifyListeners();
  }

  void resetEphemeralState() {
    _assistantDeltaBuffers.clear();
    _structuredSuppressionByTurn.clear();
    _overlayController?.reset();
    _activeToolExecutions.clear();
    _recentToolResults.clear();
    _agentState = AgentState.idle;
    _currentTool = null;
    _isTyping = false;
    _cancelThinkingReset();
    _searchCueService?.reset();
  }

  void _playSearchCueForTurn(String turnId) {
    _playCueForTurn(
      turnId,
      state: CueState.searching,
      eventLabel: 'searching',
    );
  }

  void _playCueForTurn(
    String turnId, {
    required CueState state,
    required String eventLabel,
  }) {
    final cueService = _searchCueService;
    if (cueService == null) {
      return;
    }
    final cueLatency = Stopwatch()..start();
    unawaited(() async {
      try {
        final played = await cueService.playStateCue(
          turnId,
          state: state,
          soundEnabled: _soundEffectsEnabled,
        );
        final latencyMs = cueLatency.elapsedMilliseconds;
        if (played) {
          log(
            'cue_played turn_id=$turnId cue_state=$eventLabel cue_latency_ms=$latencyMs',
          );
          return;
        }
        if (!_soundEffectsEnabled) {
          log(
            'cue_skipped_disabled turn_id=$turnId cue_state=$eventLabel cue_latency_ms=$latencyMs',
          );
          return;
        }
        log(
          'cue_skipped_duplicate turn_id=$turnId cue_state=$eventLabel cue_latency_ms=$latencyMs',
        );
      } catch (error) {
        log('cue_error turn_id=$turnId cue_state=$eventLabel error=$error');
      }
    }());
  }

  void hydrateFromSnapshots(List<ConversationMessageSnapshot> snapshots) {
    resetEphemeralState();
    _messages.clear();
    for (final rawSnapshot in snapshots) {
      final snapshot = _postProcessSnapshot(rawSnapshot);
      final eventType = switch (snapshot.messageType) {
        ConversationMessageType.researchResult => 'research_result',
        ConversationMessageType.confirmationRequired => 'confirmation_required',
        ConversationMessageType.systemResult => 'system_result',
        ConversationMessageType.mediaResult => 'media_result',
        ConversationMessageType.error => 'error',
        ConversationMessageType.status => 'status',
        ConversationMessageType.text => snapshot.role == ConversationMessageRole.assistant ? 'assistant_final' : null,
      };
      final message = ChatMessage(
        id: snapshot.id,
        content: snapshot.content,
        timestamp: snapshot.timestamp,
        isUser: snapshot.role == ConversationMessageRole.user,
        isAgent: snapshot.role == ConversationMessageRole.assistant,
        attachmentUrls: List<String>.from(snapshot.attachmentUrls),
        sources: _hydrateSources(snapshot.sources),
        source: _messageSourceFromSnapshot(snapshot),
        turnId: snapshot.turnId,
        isLive: false,
        eventType: eventType,
        payload: Map<String, dynamic>.from(snapshot.payload),
        originSessionId: snapshot.originSessionId,
      );
      _messages.add(message);
      if (snapshot.messageType == ConversationMessageType.confirmationRequired) {
        final timeoutSeconds = snapshot.payload['timeoutSeconds'] is int
            ? snapshot.payload['timeoutSeconds'] as int
            : int.tryParse(snapshot.payload['timeoutSeconds']?.toString() ?? '') ?? 30;
        final traceId = (snapshot.payload['traceId'] ?? snapshot.turnId ?? '').toString();
        if (traceId.isNotEmpty) {
          _overlayController?.showConfirmationPrompt(ConfirmationPromptData(
            actionType: (snapshot.payload['actionType'] ?? '').toString(),
            description: snapshot.content,
            destructive: snapshot.payload['destructive'] == true,
            timeoutSeconds: timeoutSeconds,
            traceId: traceId,
          ));
        }
      }
    }
    notifyListeners();
  }

  List<Source> _parseSources(dynamic raw) {
    if (raw is List) {
      return raw
          .whereType<Map>()
          .map((item) => Source.fromJson(item.cast<String, dynamic>()))
          .where((s) => s.url.isNotEmpty)
          .toList();
    }
    return [];
  }

  bool _hasRecentStructuredAssistant() {
    _cleanupStructuredSuppressionWindows();
    if (_structuredSuppressionByTurn.isEmpty) {
      return false;
    }
    final now = _now();
    return _structuredSuppressionByTurn.values.any(
      (startedAt) => now.difference(startedAt).inMilliseconds < _structuredSuppressionWindow.inMilliseconds,
    );
  }

  void _markStructuredAssistantForTurn(String turnId) {
    final normalizedTurnId = turnId.trim();
    if (normalizedTurnId.isEmpty || normalizedTurnId == 'default') {
      return;
    }
    _cleanupStructuredSuppressionWindows();
    _structuredSuppressionByTurn.putIfAbsent(normalizedTurnId, _now);
  }

  bool _isStructuredSuppressedForTurn(String turnId) {
    final normalizedTurnId = turnId.trim();
    if (normalizedTurnId.isEmpty || normalizedTurnId == 'default') {
      return false;
    }
    _cleanupStructuredSuppressionWindows();
    final startedAt = _structuredSuppressionByTurn[normalizedTurnId];
    if (startedAt == null) {
      return false;
    }
    return _now().difference(startedAt).inMilliseconds < _structuredSuppressionWindow.inMilliseconds;
  }

  void _cleanupStructuredSuppressionWindows() {
    final now = _now();
    _structuredSuppressionByTurn.removeWhere(
      (_, startedAt) => now.difference(startedAt).inMilliseconds >= _structuredSuppressionWindow.inMilliseconds,
    );
  }

  void setNowProviderForTesting(DateTime Function() provider) {
    _now = provider;
  }

  DateTime _eventTimestamp(Map<String, dynamic> event) {
    final raw = event['timestamp'];
    if (raw is int) {
      return DateTime.fromMillisecondsSinceEpoch(raw);
    }
    if (raw is String) {
      final parsed = int.tryParse(raw);
      if (parsed != null) {
        return DateTime.fromMillisecondsSinceEpoch(parsed);
      }
    }
    return DateTime.now();
  }

  bool _isRecentDuplicateUserMessage(String text, {Duration window = const Duration(seconds: 4)}) {
    final normalized = text.trim().toLowerCase();
    if (normalized.isEmpty) return true;
    final cutoff = DateTime.now().subtract(window);
    for (int i = _messages.length - 1; i >= 0; i--) {
      final msg = _messages[i];
      if (msg.timestamp.isBefore(cutoff)) break;
      if (msg.isUser && msg.content.trim().toLowerCase() == normalized) {
        return true;
      }
    }
    return false;
  }

  /// Unified duplicate detection for assistant messages across all channels.
  /// Checks by turn_id first (most reliable), then by content hash, then by content similarity.
  bool _isDuplicateAssistantContent(String text, String? turnId) {
    final normalized = text.trim().toLowerCase();
    if (normalized.isEmpty) return true;

    // Clean up expired hashes first
    _cleanupExpiredContentHashes();

    // Check by content hash first (catches duplicates from different channels with different turnIds)
    final contentHash = normalized.length > 50 ? normalized.substring(0, 50) : normalized;
    if (_assistantContentTimestamps.containsKey(contentHash)) {
      log('Duplicate detected by content hash: $contentHash');
      return true;
    }

    // Check by turn_id (most reliable - same turn = duplicate)
    if (turnId != null && turnId != 'default' && _assistantContentByTurn.containsKey(turnId)) {
      log('Duplicate detected by turn_id: $turnId');
      return true;
    }

    // Check recent assistant messages in the list (including live messages)
    final cutoff = DateTime.now().subtract(const Duration(seconds: 6));
    for (int i = _messages.length - 1; i >= 0; i--) {
      final msg = _messages[i];
      if (msg.timestamp.isBefore(cutoff)) break;
      if (msg.isAgent) {
        final existingNormalized = msg.content.trim().toLowerCase();
        if (existingNormalized.isEmpty) continue;

        // Exact match
        if (existingNormalized == normalized) {
          log('Duplicate detected by exact match in message list');
          return true;
        }
        // Substring match for partial-vs-final variants (lenient threshold)
        if (normalized.length > 5 && existingNormalized.length > 5) {
          if (existingNormalized.contains(normalized) || normalized.contains(existingNormalized)) {
            log('Duplicate detected by substring match in message list');
            return true;
          }
        }
      }
    }

    // Check tracked assistant content from recent events
    if (_lastAssistantTextAt != null && DateTime.now().difference(_lastAssistantTextAt!).inSeconds < 6) {
      final recent = _lastAssistantText.trim().toLowerCase();
      if (recent.isNotEmpty) {
        if (normalized == recent) {
          log('Duplicate detected by tracked content match');
          return true;
        }
        // Lenient substring matching
        if (normalized.length > 5 && recent.length > 5) {
          if (recent.contains(normalized) || normalized.contains(recent)) {
            log('Duplicate detected by tracked substring match');
            return true;
          }
        }
      }
    }

    return false;
  }

  /// Record assistant content for duplicate detection.
  void _recordAssistantContent(String text, String? turnId) {
    final normalized = text.trim().toLowerCase();
    if (normalized.isEmpty) return;

    _lastAssistantText = normalized;
    _lastAssistantTextAt = DateTime.now();

    // Track by content hash (first 50 chars) for cross-channel deduplication
    final contentHash = normalized.length > 50 ? normalized.substring(0, 50) : normalized;
    _assistantContentTimestamps[contentHash] = DateTime.now();

    if (turnId != null && turnId != 'default') {
      _assistantContentByTurn[turnId] = normalized;
      // Clean up old turn IDs (keep last 10)
      if (_assistantContentByTurn.length > 10) {
        final keysToRemove = _assistantContentByTurn.keys.take(_assistantContentByTurn.length - 10).toList();
        for (final key in keysToRemove) {
          _assistantContentByTurn.remove(key);
        }
      }
    }

    // Clean up expired content hashes
    _cleanupExpiredContentHashes();
  }

  void _cleanupExpiredContentHashes() {
    final now = DateTime.now();
    _assistantContentTimestamps.removeWhere((_, timestamp) {
      return now.difference(timestamp).inSeconds > _contentHashExpirySeconds;
    });
  }

  bool _matchesRecentStructuredAssistantVisible(String text) {
    final normalized = text.trim().toLowerCase();
    if (normalized.isEmpty) return false;

    final cutoff = DateTime.now().subtract(const Duration(seconds: 8));
    for (int i = _messages.length - 1; i >= 0; i--) {
      final msg = _messages[i];
      if (msg.timestamp.isBefore(cutoff)) break;
      if (!msg.isAgent || msg.source != MessageSource.structured) continue;

      final existing = msg.content.trim().toLowerCase();
      if (existing.isEmpty) continue;
      if (existing == normalized) return true;
      if (existing.length > 5 && normalized.length > 5) {
        if (existing.contains(normalized) || normalized.contains(existing)) {
          return true;
        }
      }
    }
    return false;
  }

  /// Add a message to the chat
  void addMessage(ChatMessage message) {
    _upsertMessage(message);
    log('Message added: ${message.content.substring(0, message.content.length > 50 ? 50 : message.content.length)}...');
    notifyListeners();
  }

  /// Add a message from a LiveKit transcription event
  void addTranscription(lk.TranscriptionEvent event) {
    if (event.segments.isEmpty) return;

    final participant = event.participant;
    final participantId = participant.identity.toLowerCase();
    final isAgent = participant.kind == lk.ParticipantKind.AGENT ||
        participantId.startsWith('agent-') ||
        participant is lk.RemoteParticipant;
    final isUser = participant is lk.LocalParticipant;

    final isFinal = event.segments.every((s) => s.isFinal);
    final liveText = event.segments.map((s) => s.text.trim()).where((t) => t.isNotEmpty).join(' ').trim();

    if (isAgent) {
      final hasRecentStructured = _hasRecentStructuredAssistant();
      if (hasRecentStructured) {
        _removeMessageById(_assistantLiveMessageId);
        _gatekeeperLogger.logEvent(
          'transcription_agent_suppressed',
          sessionId: null,
          source: 'transcription',
          content: liveText,
          status: 'suppressed_by_structured',
          extra: {'participant': participant.identity},
        );
        notifyListeners();
        return;
      }

      if (isFinal) {
        _gatekeeperLogger.logEvent(
          'transcription_agent_final',
          sessionId: null,
          source: 'transcription',
          content: liveText,
          extra: {'participant': participant.identity},
        );
        // Final transcription: check for duplicates, remove live message
        if (liveText.isNotEmpty && !_isDuplicateAssistantContent(liveText, null)) {
          _removeMessageById(_assistantLiveMessageId);
          _upsertMessage(
            ChatMessage(
              id: 'trans_assistant_${DateTime.now().microsecondsSinceEpoch}',
              content: normalizeAssistantContent(liveText),
              timestamp: DateTime.now(),
              isUser: false,
              isAgent: true,
              source: MessageSource.transcription,
              isLive: false,
            ),
            preferEnd: true,
          );
          _recordAssistantContent(liveText, null);
        } else {
          // Duplicate detected, just remove the live message
          _removeMessageById(_assistantLiveMessageId);
        }
        _isTyping = false;
        _agentState = AgentState.idle;
        _currentTool = null;
        _cancelThinkingReset();
      } else {
        _gatekeeperLogger.logEvent(
          'transcription_agent_partial',
          sessionId: null,
          source: 'transcription',
          content: liveText,
          extra: {'participant': participant.identity},
        );
        if (liveText.isNotEmpty && _matchesRecentStructuredAssistantVisible(liveText)) {
          _removeMessageById(_assistantLiveMessageId);
          _gatekeeperLogger.logEvent(
            'transcription_agent_partial',
            sessionId: null,
            source: 'transcription',
            content: liveText,
            status: 'suppressed_by_structured_visible',
            extra: {'participant': participant.identity},
          );
          notifyListeners();
          return;
        }
        // Live transcription: update/create live message (always at end)
        if (liveText.isNotEmpty) {
          _upsertMessage(
            ChatMessage(
              id: _assistantLiveMessageId,
              content: normalizeAssistantContent(liveText),
              timestamp: DateTime.now(),
              isUser: false,
              isAgent: true,
              source: MessageSource.transcription,
              isLive: true,
            ),
            preferEnd: true,
          );
        }
        _isTyping = true;
        _agentState = AgentState.writingResponse;
        _scheduleThinkingReset(timeout: const Duration(seconds: 20));
      }
      notifyListeners();
      return;
    }

    if (!isUser) return;

    // User transcription handling
    for (final segment in event.segments) {
      if (!segment.isFinal) continue;
      final text = segment.text.trim();
      if (text.isEmpty || _isRecentDuplicateUserMessage(text)) continue;

      final segmentId = segment.id.isNotEmpty ? segment.id : DateTime.now().microsecondsSinceEpoch.toString();

      _upsertMessage(
        ChatMessage(
          id: 'trans_user_$segmentId',
          content: text,
          timestamp: DateTime.now(),
          isUser: true,
          isAgent: false,
          source: MessageSource.transcription,
        ),
        preferEnd: true,
      );
    }

    notifyListeners();
  }

  /// Set typing indicator
  void setTyping(bool value) {
    if (_isTyping != value) {
      _isTyping = value;
      if (!value) {
        _agentState = AgentState.idle;
        _cancelThinkingReset();
      } else {
        _scheduleThinkingReset();
      }
      log('Typing: $value');
      notifyListeners();
    }
  }

  /// Update agent thinking state
  void updateAgentState(AgentState state, {String? tool}) {
    _agentState = state;
    _currentTool = tool;
    _isTyping = (state != AgentState.idle);
    if (state == AgentState.idle) {
      _cancelThinkingReset();
    } else {
      _scheduleThinkingReset();
    }
    notifyListeners();
  }

  void updateSpotifyStatus({required bool connected, String? displayName}) {
    _spotifyConnected = connected;
    _spotifyDisplayName = displayName;
    notifyListeners();
  }

  void resolveConfirmationLocally(String traceId, {required bool confirmed}) {
    final normalizedTraceId = traceId.trim();
    if (normalizedTraceId.isEmpty) return;
    _removeMessageById('confirmation_$normalizedTraceId');
    _overlayController?.clearConfirmationPrompt();
    notifyListeners();
  }

  /// Handle structured chat events from data channel
  void handleChatEvent(Map<String, dynamic> event) {
    final type = event['type'];
    final turnId = (event['turn_id'] ?? event['turnId'] ?? 'default').toString();

    switch (type) {
      case 'user_message':
        final text = (event['content'] ?? '').toString().trim();
        if (text.isEmpty || _isRecentDuplicateUserMessage(text)) break;
        _upsertMessage(
          ChatMessage(
            id: 'user_$turnId',
            content: text,
            timestamp: _eventTimestamp(event),
            isUser: true,
            isAgent: false,
            source: MessageSource.structured,
            turnId: turnId,
            originSessionId: _originSessionId(event),
          ),
        );
        break;

      case 'agent_thinking':
        final stateStr = event['state'] as String?;
        AgentState state = AgentState.thinking;
        if (stateStr == 'searching') {
          state = AgentState.searchingWeb;
          _playSearchCueForTurn(turnId);
        }
        if (stateStr == 'writing') state = AgentState.writingResponse;
        updateAgentState(state);
        break;

      case 'tool_execution':
        final status = event['status'];
        final tool = (event['tool_name'] ?? event['tool'] ?? '').toString();
        final taskId = event['task_id']?.toString();
        _gatekeeperLogger.logEvent(
          status == 'started'
              ? 'tool_execution_started'
              : (status == 'failed' ? 'tool_execution_failed' : 'tool_execution_finished'),
          turnId: turnId,
          traceId: event['trace_id']?.toString(),
          source: 'chat_events',
          toolName: tool,
          status: status?.toString(),
          content: event['message']?.toString(),
          extra: {
            'raw_event_type': 'tool_execution',
          },
        );
        if (status == 'started') {
          _activeToolExecutions[_toolExecutionKey(turnId: turnId, toolName: tool, taskId: taskId)] = {
            'turnId': turnId,
            'toolName': tool,
            'taskId': taskId,
            'conversationId': event['conversation_id']?.toString(),
            'startedAt': _eventTimestamp(event).toIso8601String(),
          };
          _playCueForTurn(
            turnId,
            state: CueState.toolCalling,
            eventLabel: 'tool_calling',
          );
          updateAgentState(AgentState.callingTools, tool: tool);
        } else {
          _activeToolExecutions.remove(
            _toolExecutionKey(turnId: turnId, toolName: tool, taskId: taskId),
          );
          final toolSummary = (event['message'] ?? '$tool ${status?.toString() ?? 'finished'}').toString();
          _recordToolResultSummary(
            toolName: tool,
            summary: toolSummary,
            timestamp: _eventTimestamp(event),
            taskId: taskId,
          );
          updateAgentState(AgentState.writingResponse);
          _scheduleThinkingReset(timeout: const Duration(seconds: 8));
        }
        break;

      case 'agent_speaking':
        final status = (event['status'] ?? '').toString().trim().toLowerCase();
        if (status == 'started') {
          updateAgentState(AgentState.writingResponse);
        } else if (status == 'finished') {
          updateAgentState(AgentState.idle);
        }
        break;

      case 'turn_complete':
        _playCueForTurn(
          turnId,
          state: CueState.completed,
          eventLabel: 'turn_complete',
        );
        _searchCueService?.onTurnComplete(turnId);
        updateAgentState(AgentState.idle);
        break;

      case 'error':
        _upsertMessage(
          ChatMessage(
            id: 'assistant_error_$turnId',
            content: _safeErrorText,
            timestamp: _eventTimestamp(event),
            isUser: false,
            isAgent: true,
            source: MessageSource.structured,
            turnId: turnId,
            isLive: false,
            eventType: 'error',
            payload: {
              'code': event['code']?.toString(),
              'message': (event['message'] ?? '').toString(),
            },
            originSessionId: _originSessionId(event),
          ),
          preferEnd: true,
        );
        updateAgentState(AgentState.idle);
        break;

      case 'assistant_delta':
        final delta = (event['content'] ?? '').toString();
        if (delta.isEmpty) break;

        final buffer = _assistantDeltaBuffers.putIfAbsent(turnId, () => StringBuffer());
        buffer.write(delta);
        final fullText = buffer.toString();

        // Remove transcription live message - structured events take priority
        _removeMessageById(_assistantLiveMessageId);

        _upsertMessage(
          ChatMessage(
            id: 'assistant_$turnId',
            content: normalizeAssistantContent(fullText),
            timestamp: _eventTimestamp(event),
            isUser: false,
            isAgent: true,
            source: MessageSource.structured,
            turnId: turnId,
            isLive: true, // Still streaming
            payload: {
              'seq': event['seq'],
            },
            originSessionId: _originSessionId(event),
          ),
          preferEnd: true,
        );
        _gatekeeperLogger.logEvent(
          'assistant_delta',
          turnId: turnId,
          traceId: event['trace_id']?.toString(),
          source: 'chat_events',
          content: fullText,
          status: 'rendered',
        );
        updateAgentState(AgentState.writingResponse);
        break;

      case 'assistant_final':
        final finalText = (event['content'] ?? '').toString();
        final buffer = _assistantDeltaBuffers.remove(turnId);
        final resolvedText = finalText.isNotEmpty ? finalText : (buffer?.toString() ?? '');
        final sources = _parseSources(event['sources']);

        if (resolvedText.isEmpty) break;

        if (_isStructuredSuppressedForTurn(turnId)) {
          _gatekeeperLogger.logEvent(
            'assistant_final',
            turnId: turnId,
            traceId: event['trace_id']?.toString(),
            source: 'chat_events',
            content: resolvedText,
            status: 'suppressed_by_structured_turn',
          );
          updateAgentState(AgentState.idle);
          break;
        }

        // Remove transcription live message if present
        _removeMessageById(_assistantLiveMessageId);

        // Check for duplicates using unified detection
        if (!_isDuplicateAssistantContent(resolvedText, turnId)) {
          _upsertMessage(
            ChatMessage(
              id: 'assistant_$turnId',
              content: normalizeAssistantContent(resolvedText),
              timestamp: _eventTimestamp(event),
              isUser: false,
              isAgent: true,
              source: MessageSource.structured,
              turnId: turnId,
              isLive: false,
              sources: sources,
              eventType: 'assistant_final',
              payload: {
                'voiceText': (event['voice_text'] ?? '').toString(),
                'mode': (event['mode'] ?? 'normal').toString(),
                'toolInvocations': event['tool_invocations'] is List ? List.from(event['tool_invocations']) : const [],
                'structuredData':
                    event['structured_data'] is Map ? Map<String, dynamic>.from(event['structured_data']) : const {},
              },
              originSessionId: _originSessionId(event),
            ),
            preferEnd: true,
          );
          _recordAssistantContent(resolvedText, turnId);
          _gatekeeperLogger.logEvent(
            'assistant_final',
            turnId: turnId,
            traceId: event['trace_id']?.toString(),
            source: 'chat_events',
            content: resolvedText,
            status: 'rendered',
          );
        } else {
          _gatekeeperLogger.logEvent(
            'assistant_final',
            turnId: turnId,
            traceId: event['trace_id']?.toString(),
            source: 'chat_events',
            content: resolvedText,
            status: 'suppressed_duplicate',
          );
        }
        updateAgentState(AgentState.idle);
        break;

      case 'research_result':
        final summary = (event['summary'] ?? '').toString().trim();
        final query = (event['query'] ?? '').toString().trim();
        final sources = _parseSources(event['sources']);
        if (summary.isEmpty) break;

        _removeMessageById(_assistantLiveMessageId);
        _upsertMessage(
          ChatMessage(
            id: 'assistant_$turnId',
            content: normalizeAssistantContent(summary),
            timestamp: _eventTimestamp(event),
            isUser: false,
            isAgent: true,
            source: MessageSource.structured,
            turnId: turnId,
            isLive: false,
            sources: sources,
            eventType: 'research_result',
            payload: {
              'query': query,
              'taskId': event['task_id']?.toString(),
              'conversationId': event['conversation_id']?.toString(),
            },
            originSessionId: _originSessionId(event),
          ),
          preferEnd: true,
        );
        _recordToolResultSummary(
          toolName: 'research',
          summary: query.isNotEmpty ? 'Research complete: $query' : summary,
          timestamp: _eventTimestamp(event),
          taskId: event['task_id']?.toString(),
        );
        _markStructuredAssistantForTurn(turnId);
        _gatekeeperLogger.logEvent(
          'research_result',
          turnId: turnId,
          traceId: event['trace_id']?.toString(),
          source: 'chat_events',
          content: summary,
          status: 'rendered',
          extra: {
            'query': query,
            'source_count': sources.length,
          },
        );
        updateAgentState(AgentState.idle);
        break;

      case 'media_result':
        final action = (event['action'] ?? '').toString().trim();
        final provider = (event['provider'] ?? '').toString().trim();
        final trackName = (event['track_name'] ?? '').toString().trim();
        final artist = (event['artist'] ?? '').toString().trim();
        final albumArt = (event['album_art_url'] ?? '').toString().trim();
        final summary = _buildMediaSummary(
          action: action,
          provider: provider,
          trackName: trackName,
          artist: artist,
        );
        _upsertMessage(
          ChatMessage(
            id: 'media_$turnId',
            content: summary,
            timestamp: _eventTimestamp(event),
            isUser: false,
            isAgent: false,
            source: MessageSource.structured,
            turnId: turnId,
            isLive: false,
            eventType: 'media_result',
            payload: {
              'action': action,
              'provider': provider,
              'trackName': trackName,
              'artist': artist,
              'albumArtUrl': albumArt,
              'trackUrl': (event['track_url'] ?? '').toString().trim(),
              'taskId': event['task_id']?.toString(),
              'conversationId': event['conversation_id']?.toString(),
            },
            originSessionId: _originSessionId(event),
          ),
          preferEnd: true,
        );
        _overlayController?.showMediaResultToast(MediaResultToastData(
          trackName: trackName,
          provider: provider,
          statusText: summary,
          artist: artist,
          albumArtUrl: albumArt,
          eventId: turnId,
        ));
        _recordToolResultSummary(
          toolName: provider.isEmpty ? 'media' : provider,
          summary: summary,
          timestamp: _eventTimestamp(event),
          taskId: event['task_id']?.toString(),
        );
        _markStructuredAssistantForTurn(turnId);
        updateAgentState(AgentState.idle);
        break;

      case 'system_result':
        final actionType = (event['action_type'] ?? '').toString().trim();
        final message = (event['message'] ?? '').toString().trim();
        if (actionType.isEmpty || message.isEmpty) break;
        final systemTraceId = (event['trace_id'] ?? turnId).toString();
        _upsertMessage(
          ChatMessage(
            id: 'system_$systemTraceId',
            content: message,
            timestamp: _eventTimestamp(event),
            isUser: false,
            isAgent: false,
            source: MessageSource.structured,
            turnId: turnId == 'default' ? null : turnId,
            isLive: false,
            eventType: 'system_result',
            payload: {
              'actionType': actionType,
              'detail': (event['detail'] ?? '').toString().trim(),
              'success': event['success'] == true,
              'rollbackAvailable': event['rollback_available'] == true,
              'traceId': systemTraceId,
              'taskId': event['task_id']?.toString(),
              'conversationId': event['conversation_id']?.toString(),
            },
            originSessionId: _originSessionId(event),
          ),
          preferEnd: true,
        );
        _overlayController?.showSystemActionToast(SystemActionToastData(
          actionType: actionType,
          message: message,
          detail: (event['detail'] ?? '').toString().trim(),
          success: event['success'] == true,
          rollbackAvailable: event['rollback_available'] == true,
          traceId: systemTraceId,
        ));
        _recordToolResultSummary(
          toolName: actionType.toLowerCase(),
          summary: message,
          timestamp: _eventTimestamp(event),
          taskId: event['task_id']?.toString(),
        );
        _markStructuredAssistantForTurn(turnId == 'default' ? systemTraceId : turnId);
        updateAgentState(AgentState.idle);
        break;

      case 'confirmation_required':
        final actionType = (event['action_type'] ?? '').toString().trim();
        final description = (event['description'] ?? '').toString().trim();
        final traceId = (event['trace_id'] ?? '').toString().trim();
        if (actionType.isEmpty || description.isEmpty || traceId.isEmpty) break;
        final timeoutSecs = event['timeout_seconds'] is int
            ? event['timeout_seconds'] as int
            : int.tryParse((event['timeout_seconds'] ?? '').toString()) ?? 30;
        _overlayController?.showConfirmationPrompt(ConfirmationPromptData(
          actionType: actionType,
          description: description,
          destructive: event['destructive'] == true,
          timeoutSeconds: timeoutSecs,
          traceId: traceId,
        ));
        _upsertMessage(
          ChatMessage(
            id: 'confirmation_$traceId',
            content: description,
            timestamp: _eventTimestamp(event),
            isUser: false,
            isAgent: true,
            source: MessageSource.structured,
            turnId: traceId,
            isLive: false,
            eventType: 'confirmation_required',
            payload: {
              'actionType': actionType,
              'destructive': event['destructive'] == true,
              'timeoutSeconds': timeoutSecs,
              'traceId': traceId,
            },
            originSessionId: _originSessionId(event),
          ),
          preferEnd: true,
        );
        _markStructuredAssistantForTurn(turnId == 'default' ? traceId : turnId);
        updateAgentState(AgentState.idle);
        break;

      case 'confirmation_response':
        final traceId = (event['trace_id'] ?? '').toString().trim();
        if (traceId.isEmpty) break;
        resolveConfirmationLocally(traceId, confirmed: event['confirmed'] == true);
        break;
    }
    notifyListeners();
  }

  String _buildMediaSummary({
    required String action,
    required String provider,
    required String trackName,
    required String artist,
  }) {
    final providerLabel = provider.isEmpty ? 'media' : provider;
    final actionLabel = _capitalize(action);
    if (trackName.isNotEmpty && artist.isNotEmpty) {
      return '$actionLabel completed via ${providerLabel.toUpperCase()}.';
    }
    if (trackName.isNotEmpty) {
      return '$actionLabel completed via ${providerLabel.toUpperCase()}.';
    }
    return '${_capitalize(action)} completed via ${providerLabel.toUpperCase()}.';
  }

  String _capitalize(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return 'Media';
    return '${trimmed[0].toUpperCase()}${trimmed.substring(1)}';
  }

  /// Clear all messages
  void clearMessages() {
    _messages.clear();
    resetEphemeralState();
    log('Messages cleared');
    notifyListeners();
  }

  /// Delete a specific message
  void deleteMessage(String id) {
    _messages.removeWhere((msg) => msg.id == id);
    log('Message deleted: $id');
    notifyListeners();
  }

  @override
  void dispose() {
    _messages.clear();
    resetEphemeralState();
    super.dispose();
  }
}
