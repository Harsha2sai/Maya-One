import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../../core/services/assistant_content_normalizer.dart';
import '../../core/services/storage_service.dart';
import '../base_provider.dart';
import '../models/conversation_models.dart';
import 'chat_provider.dart';
import 'session_provider.dart';

class ConversationHistoryProvider extends BaseProvider {
  static const _uuid = Uuid();
  static const _defaultConversationTitle = 'New chat';
  static const _migrationPlaceholderPreview = 'Imported from legacy chat history';

  StorageService _storage;
  ChatProvider _chatProvider;
  SessionProvider _sessionProvider;
  final List<ConversationRecord> _conversations = [];
  final List<ProjectRecord> _projects = [];
  bool _initialized = false;
  bool _isSwitchingConversation = false;
  String _switchStatus = '';
  String _activeConversationId = '';
  bool _suspendAutoPersist = false;
  bool _pendingInitialBootstrap = false;
  Timer? _persistDebounce;
  String _lastPersistedSignature = '';
  String? _lastObservedSessionId;

  ConversationHistoryProvider(
    this._storage,
    this._chatProvider,
    this._sessionProvider,
  ) : super('ConversationHistoryProvider') {
    _chatProvider.addListener(_onChatChanged);
    _sessionProvider.addListener(_onSessionChanged);
    unawaited(_initialize());
  }

  bool get initialized => _initialized;
  bool get isSwitchingConversation => _isSwitchingConversation;
  String get switchStatus => _switchStatus;
  String get activeConversationId => _activeConversationId;
  ConversationRecord? get activeConversation => _findConversation(_activeConversationId);
  List<ConversationRecord> get conversations => List.unmodifiable(
        _conversations.where((conversation) => !conversation.archived).toList()
          ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt)),
      );
  List<ConversationRecord> get archivedConversations => List.unmodifiable(
        _conversations.where((conversation) => conversation.archived).toList()
          ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt)),
      );
  List<ProjectRecord> get projects =>
      List.unmodifiable(_projects.toList()..sort((a, b) => b.updatedAt.compareTo(a.updatedAt)));
  bool get hasRunningTask => _chatProvider.hasActiveToolExecution;

  void updateDependencies(
    StorageService storage,
    ChatProvider chatProvider,
    SessionProvider sessionProvider,
  ) {
    if (!identical(_chatProvider, chatProvider)) {
      _chatProvider.removeListener(_onChatChanged);
      _chatProvider = chatProvider;
      _chatProvider.addListener(_onChatChanged);
    }
    if (!identical(_sessionProvider, sessionProvider)) {
      _sessionProvider.removeListener(_onSessionChanged);
      _sessionProvider = sessionProvider;
      _sessionProvider.addListener(_onSessionChanged);
    }
    _storage = storage;
  }

  ConversationRecord? _findConversation(String id) {
    for (final conversation in _conversations) {
      if (conversation.id == id) {
        return conversation;
      }
    }
    return null;
  }

  Future<void> _initialize() async {
    final store = await _storage.loadConversationStore();
    if (store != null && store.conversations.isNotEmpty) {
      _conversations
        ..clear()
        ..addAll(store.conversations);
      _projects
        ..clear()
        ..addAll(store.projects);
      _activeConversationId = store.activeConversationId;
      if (_findConversation(_activeConversationId) == null) {
        _activeConversationId = _conversations.first.id;
      }
    } else {
      await _migrateLegacyStoreIfNeeded();
      if (_conversations.isEmpty) {
        final blank = _createBlankConversation();
        _conversations.add(blank);
        _activeConversationId = blank.id;
      }
      await _persistStore();
    }

    _initialized = true;
    _applyActiveConversationToChat();
    _pendingInitialBootstrap = activeConversation?.messages.isNotEmpty == true;
    notifyListeners();
    _onSessionChanged();
  }

  Future<void> _migrateLegacyStoreIfNeeded() async {
    final hasNewStore = await _storage.hasConversationStore();
    if (hasNewStore) {
      return;
    }
    final migrationComplete = await _storage.isConversationMigrationComplete();
    if (migrationComplete) {
      return;
    }

    try {
      final history = await _storage.getConversationHistory();
      if (history.isNotEmpty) {
        final now = DateTime.now();
        for (final title in history) {
          final trimmed = title.trim();
          if (trimmed.isEmpty) {
            continue;
          }
          final conversation = ConversationRecord(
            id: _uuid.v4(),
            title: trimmed,
            preview: _migrationPlaceholderPreview,
            createdAt: now,
            updatedAt: now,
            archived: false,
            messages: const [],
            resumeContext: ConversationResumeContext(updatedAt: now),
          );
          _conversations.add(conversation);
        }
      }
    } finally {
      await _storage.setConversationMigrationComplete(true);
    }
  }

  ConversationRecord _createBlankConversation() {
    final now = DateTime.now();
    return ConversationRecord(
      id: _uuid.v4(),
      title: _defaultConversationTitle,
      preview: '',
      createdAt: now,
      updatedAt: now,
      archived: false,
      messages: const [],
      resumeContext: ConversationResumeContext(updatedAt: now),
    );
  }

  void _applyActiveConversationToChat() {
    final conversation = activeConversation;
    if (conversation == null) {
      _chatProvider.clearMessages();
      return;
    }
    _suspendAutoPersist = true;
    _chatProvider.hydrateFromSnapshots(conversation.messages);
    _suspendAutoPersist = false;
  }

  void _onChatChanged() {
    if (!_initialized || _suspendAutoPersist || _isSwitchingConversation) {
      return;
    }
    _persistDebounce?.cancel();
    _persistDebounce = Timer(const Duration(milliseconds: 200), () {
      unawaited(_persistActiveConversationFromChat());
    });
  }

  void _onSessionChanged() {
    if (!_initialized || !_sessionProvider.isConnected) {
      return;
    }
    final sessionId = _sessionProvider.currentSessionId;
    if (sessionId == null || sessionId == _lastObservedSessionId) {
      return;
    }
    _lastObservedSessionId = sessionId;
    if (_pendingInitialBootstrap && activeConversation != null) {
      _pendingInitialBootstrap = false;
      unawaited(
        _sessionProvider.sendBootstrapContext(
          payload: _buildBootstrapPayload(activeConversation!),
          conversationId: activeConversation!.id,
          bootstrapVersion: 1,
          waitForAck: false,
        ),
      );
    }
  }

  Future<void> _persistStore() async {
    final snapshot = ConversationStoreSnapshot(
      activeConversationId: _activeConversationId,
      conversations: _conversations,
      projects: _projects,
    );
    final signature = snapshot.toJsonString();
    if (signature == _lastPersistedSignature) {
      return;
    }
    await _storage.saveConversationStore(snapshot);
    _lastPersistedSignature = signature;
  }

  ConversationResumeContext _buildResumeContext(
    ConversationRecord current,
    List<ConversationMessageSnapshot> snapshots,
    DateTime now,
  ) {
    final lastMeaningfulUser = snapshots.firstWhere(
      (snapshot) =>
          snapshot.role == ConversationMessageRole.user &&
          _hasMeaningfulAutoTitleCandidate(snapshot.content),
      orElse: () => ConversationMessageSnapshot(
        id: '',
        role: ConversationMessageRole.user,
        messageType: ConversationMessageType.text,
        content: '',
        timestamp: now,
      ),
    );
    var topicSummary = current.title.trim();
    if (topicSummary.isEmpty || topicSummary == _defaultConversationTitle) {
      topicSummary = lastMeaningfulUser.content.trim();
    }
    topicSummary = _truncateOneLine(topicSummary, 240);

    final recentEvents = snapshots
        .where(
          (snapshot) =>
              snapshot.messageType == ConversationMessageType.text ||
              snapshot.messageType == ConversationMessageType.researchResult ||
              snapshot.messageType == ConversationMessageType.confirmationRequired ||
              snapshot.messageType == ConversationMessageType.systemResult ||
              snapshot.messageType == ConversationMessageType.mediaResult,
        )
        .toList()
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));

    final resumeEvents = recentEvents.reversed.take(6).toList().reversed.map((snapshot) {
      return ConversationResumeEvent(
        role: snapshot.role,
        messageType: snapshot.messageType,
        content: _truncateOneLine(normalizeAssistantContent(snapshot.content), 180),
        timestamp: snapshot.timestamp,
      );
    }).toList();

    final liveToolResults = _chatProvider.recentToolResults.isNotEmpty
        ? _chatProvider.recentToolResults
        : current.resumeContext.lastToolResults;
    final derivedToolResults = <ConversationToolResultSummary>[...liveToolResults];
    for (final snapshot in recentEvents.reversed) {
      if (snapshot.messageType == ConversationMessageType.researchResult) {
        derivedToolResults.add(
          ConversationToolResultSummary(
            toolName: 'research',
            summary: _truncateOneLine(snapshot.content, 180),
            timestamp: snapshot.timestamp,
            taskId: snapshot.payload['taskId']?.toString(),
          ),
        );
      } else if (snapshot.messageType == ConversationMessageType.mediaResult) {
        derivedToolResults.add(
          ConversationToolResultSummary(
            toolName: snapshot.payload['provider']?.toString() ?? 'media',
            summary: _truncateOneLine(snapshot.content, 180),
            timestamp: snapshot.timestamp,
            taskId: snapshot.payload['taskId']?.toString(),
          ),
        );
      } else if (snapshot.messageType == ConversationMessageType.systemResult) {
        derivedToolResults.add(
          ConversationToolResultSummary(
            toolName: snapshot.payload['actionType']?.toString() ?? 'system',
            summary: _truncateOneLine(snapshot.content, 180),
            timestamp: snapshot.timestamp,
            taskId: snapshot.payload['taskId']?.toString(),
          ),
        );
      }
    }

    final uniqueToolResults = <ConversationToolResultSummary>[];
    final seen = <String>{};
    for (final result in derivedToolResults) {
      final key = '${result.toolName}:${result.taskId ?? ''}:${result.summary}';
      if (!seen.add(key)) {
        continue;
      }
      uniqueToolResults.add(result);
      if (uniqueToolResults.length >= 3) {
        break;
      }
    }

    return ConversationResumeContext(
      topicSummary: topicSummary,
      recentEvents: resumeEvents,
      lastToolResults: uniqueToolResults,
      updatedAt: now,
    );
  }

  String _derivePreview(List<ConversationMessageSnapshot> snapshots) {
    if (snapshots.isEmpty) {
      return '';
    }
    final latest = snapshots.last;
    return _truncateOneLine(normalizeAssistantContent(latest.content), 100);
  }

  bool _hasMeaningfulAutoTitleCandidate(String raw) {
    final tokens = RegExp(r'[A-Za-z]+')
        .allMatches(raw)
        .map((match) => match.group(0))
        .whereType<String>()
        .where((token) => token.trim().isNotEmpty)
        .toList();
    return tokens.length >= 3;
  }

  String _deriveAutoTitle(ConversationRecord current, List<ConversationMessageSnapshot> snapshots) {
    if (current.autoTitleLocked) {
      return current.title;
    }
    if (current.title.trim().isNotEmpty && current.title.trim() != _defaultConversationTitle) {
      return current.title;
    }
    for (final snapshot in snapshots) {
      if (snapshot.role != ConversationMessageRole.user) {
        continue;
      }
      if (!_hasMeaningfulAutoTitleCandidate(snapshot.content)) {
        continue;
      }
      return _truncateOneLine(snapshot.content, 60);
    }
    return current.title;
  }

  String _truncateOneLine(String raw, int maxLength) {
    final singleLine = raw.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (singleLine.length <= maxLength) {
      return singleLine;
    }
    return '${singleLine.substring(0, maxLength - 1).trim()}…';
  }

  Future<void> _persistActiveConversationFromChat() async {
    final current = activeConversation;
    if (current == null) {
      return;
    }
    final snapshots = _chatProvider.snapshotMessages(
      originSessionId: _sessionProvider.currentSessionId ?? current.resumeContext.updatedAt.toIso8601String(),
    );
    final now = DateTime.now();
    final updated = current.copyWith(
      title: _deriveAutoTitle(current, snapshots),
      preview: _derivePreview(snapshots),
      updatedAt: now,
      messages: snapshots,
      resumeContext: _buildResumeContext(current, snapshots, now),
    );
    final index = _conversations.indexWhere((conversation) => conversation.id == current.id);
    if (index == -1) {
      return;
    }
    _conversations[index] = updated;
    await _persistStore();
    notifyListeners();
  }

  Map<String, dynamic> _buildBootstrapPayload(ConversationRecord conversation) {
    final resumeContext = conversation.resumeContext;
    return {
      'kind': 'conversation_resume',
      'conversation_id': conversation.id,
      'project_id': conversation.projectId,
      'resume_mode': 'summary_v1',
      'bootstrap_version': 1,
      'topic_summary': resumeContext.topicSummary,
      'recent_events': resumeContext.recentEvents
          .map(
            (event) => {
              'role': event.role.name,
              'message_type': event.messageType.name,
              'content': event.content,
              'timestamp': event.timestamp.toIso8601String(),
            },
          )
          .toList(),
      'last_tool_results': resumeContext.lastToolResults
          .map(
            (result) => {
              'tool_name': result.toolName,
              'summary': result.summary,
              'timestamp': result.timestamp.toIso8601String(),
              'task_id': result.taskId,
            },
          )
          .toList(),
    };
  }

  Map<String, dynamic> _buildSessionMetadata(ConversationRecord conversation) {
    return {
      'conversation_id': conversation.id,
      'conversation_title': conversation.title,
      'project_id': conversation.projectId,
      'resume_mode': 'summary_v1',
      'bootstrap_version': 1,
    };
  }

  Future<void> _appendInterruptionMarkerToCurrentConversation() async {
    final current = activeConversation;
    if (current == null) {
      return;
    }
    final snapshots = _chatProvider.snapshotMessages(
      originSessionId: _sessionProvider.currentSessionId ?? '',
    );
    final now = DateTime.now();
    final interruption = ConversationMessageSnapshot(
      id: 'system_interrupt_${now.microsecondsSinceEpoch}',
      role: ConversationMessageRole.system,
      messageType: ConversationMessageType.systemResult,
      content: 'An in-flight task was interrupted by conversation switch.',
      timestamp: now,
      payload: {
        'actionType': 'CONVERSATION_SWITCH',
        'detail': 'User switched threads while work was still in progress.',
        'success': false,
        'rollbackAvailable': false,
        'traceId': 'conversation-switch-${now.millisecondsSinceEpoch}',
      },
      sourceChannel: ConversationSourceChannel.structured,
      originSessionId: _sessionProvider.currentSessionId ?? '',
    );
    final updatedSnapshots = [...snapshots, interruption];
    final updatedConversation = current.copyWith(
      preview: _derivePreview(updatedSnapshots),
      updatedAt: now,
      messages: updatedSnapshots,
      resumeContext: _buildResumeContext(current, updatedSnapshots, now),
    );
    final index = _conversations.indexWhere((conversation) => conversation.id == current.id);
    if (index != -1) {
      _conversations[index] = updatedConversation;
      await _persistStore();
    }
  }

  Future<bool> activateConversation(
    String conversationId, {
    bool allowTaskInterruption = false,
  }) async {
    if (!_initialized || _isSwitchingConversation) {
      return false;
    }
    final target = _findConversation(conversationId);
    if (target == null) {
      return false;
    }
    if (target.id == _activeConversationId) {
      return true;
    }
    if (hasRunningTask && !allowTaskInterruption) {
      return false;
    }

    await _persistActiveConversationFromChat();
    if (hasRunningTask && allowTaskInterruption) {
      await _appendInterruptionMarkerToCurrentConversation();
    }

    final currentVisibleConversationId = _activeConversationId;
    _isSwitchingConversation = true;
    _switchStatus = 'Switching conversation…';
    notifyListeners();

    final connected = await _sessionProvider.reconnectWithMetadata(
      userId: _sessionProvider.currentUserId,
      clientConfig: _buildSessionMetadata(target),
    );
    if (!connected) {
      _isSwitchingConversation = false;
      _switchStatus = '';
      _activeConversationId = currentVisibleConversationId;
      notifyListeners();
      return false;
    }

    _suspendAutoPersist = true;
    _activeConversationId = target.id;
    _chatProvider.hydrateFromSnapshots(target.messages);
    _suspendAutoPersist = false;
    await _persistStore();
    _pendingInitialBootstrap = false;
    await _sessionProvider.sendBootstrapContext(
      payload: _buildBootstrapPayload(target),
      conversationId: target.id,
      bootstrapVersion: 1,
      waitForAck: true,
    );

    _isSwitchingConversation = false;
    _switchStatus = '';
    notifyListeners();
    return true;
  }

  Future<bool> createConversation({
    bool allowTaskInterruption = false,
  }) async {
    final conversation = _createBlankConversation();
    _conversations.insert(0, conversation);
    await _persistStore();
    return await activateConversation(
      conversation.id,
      allowTaskInterruption: allowTaskInterruption,
    );
  }

  Future<void> renameConversation(String conversationId, String title) async {
    final trimmed = title.trim();
    if (trimmed.isEmpty) {
      return;
    }
    final index = _conversations.indexWhere((conversation) => conversation.id == conversationId);
    if (index == -1) {
      return;
    }
    final updated = _conversations[index].copyWith(
      title: _truncateOneLine(trimmed, 80),
      updatedAt: DateTime.now(),
      autoTitleLocked: true,
    );
    _conversations[index] = updated;
    await _persistStore();
    notifyListeners();
  }

  Future<void> archiveConversation(String conversationId) async {
    final index = _conversations.indexWhere((conversation) => conversation.id == conversationId);
    if (index == -1) {
      return;
    }
    _conversations[index] = _conversations[index].copyWith(
      archived: true,
      updatedAt: DateTime.now(),
    );
    await _persistStore();
    if (_activeConversationId == conversationId) {
      final fallback = conversations.where((conversation) => conversation.id != conversationId).firstOrNull;
      if (fallback != null) {
        await activateConversation(
          fallback.id,
          allowTaskInterruption: hasRunningTask,
        );
      } else {
        await createConversation(
          allowTaskInterruption: hasRunningTask,
        );
      }
    }
    notifyListeners();
  }

  Future<void> restoreConversation(String conversationId) async {
    final index = _conversations.indexWhere((conversation) => conversation.id == conversationId);
    if (index == -1) {
      return;
    }
    _conversations[index] = _conversations[index].copyWith(
      archived: false,
      updatedAt: DateTime.now(),
    );
    await _persistStore();
    notifyListeners();
  }

  Future<void> deleteConversation(String conversationId) async {
    final wasActive = _activeConversationId == conversationId;
    _conversations.removeWhere((conversation) => conversation.id == conversationId);
    if (_conversations.isEmpty) {
      final blank = _createBlankConversation();
      _conversations.add(blank);
      _activeConversationId = blank.id;
      _applyActiveConversationToChat();
      await _sessionProvider.reconnectWithMetadata(
        userId: _sessionProvider.currentUserId,
        clientConfig: _buildSessionMetadata(blank),
      );
      await _sessionProvider.sendBootstrapContext(
        payload: _buildBootstrapPayload(blank),
        conversationId: blank.id,
        bootstrapVersion: 1,
        waitForAck: true,
      );
    } else if (wasActive) {
      final fallback = conversations.first;
      _activeConversationId = fallback.id;
      _applyActiveConversationToChat();
      await _sessionProvider.reconnectWithMetadata(
        userId: _sessionProvider.currentUserId,
        clientConfig: _buildSessionMetadata(fallback),
      );
      await _sessionProvider.sendBootstrapContext(
        payload: _buildBootstrapPayload(fallback),
        conversationId: fallback.id,
        bootstrapVersion: 1,
        waitForAck: true,
      );
    }
    await _persistStore();
    notifyListeners();
  }

  Future<ProjectRecord> createProject(
    String name, {
    String description = '',
  }) async {
    final now = DateTime.now();
    final project = ProjectRecord(
      id: _uuid.v4(),
      name: _truncateOneLine(name.trim(), 80),
      description: description.trim(),
      createdAt: now,
      updatedAt: now,
    );
    _projects.add(project);
    await _persistStore();
    notifyListeners();
    return project;
  }

  Future<void> moveConversationToProject(String conversationId, String? projectId) async {
    final index = _conversations.indexWhere((conversation) => conversation.id == conversationId);
    if (index == -1) {
      return;
    }
    _conversations[index] = _conversations[index].copyWith(
      projectId: projectId,
      clearProjectId: projectId == null,
      updatedAt: DateTime.now(),
    );
    await _persistStore();
    notifyListeners();
  }

  List<ConversationRecord> conversationsForProject(String projectId) {
    return _conversations
        .where((conversation) => !conversation.archived && conversation.projectId == projectId)
        .toList()
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
  }

  Future<String?> exportConversation(String conversationId) async {
    final isDesktop = switch (defaultTargetPlatform) {
      TargetPlatform.linux || TargetPlatform.macOS || TargetPlatform.windows => true,
      _ => false,
    };
    if (kIsWeb || !isDesktop) {
      return null;
    }
    final conversation = _findConversation(conversationId);
    if (conversation == null) {
      return null;
    }
    final savePath = await FilePicker.platform.saveFile(
      dialogTitle: 'Export Maya chat',
      fileName: '${conversation.title.replaceAll(RegExp(r"[^A-Za-z0-9_-]+"), "_")}.md',
      type: FileType.custom,
      allowedExtensions: const ['md'],
    );
    if (savePath == null || savePath.trim().isEmpty) {
      return null;
    }

    final projectName = _projects
        .where((project) => project.id == conversation.projectId)
        .map((project) => project.name)
        .firstOrNull;

    final buffer = StringBuffer()
      ..writeln('# Maya Chat Transcript')
      ..writeln('Title: ${conversation.title}')
      ..writeln('Project: ${projectName ?? 'Unassigned'}')
      ..writeln('Created: ${conversation.createdAt.toIso8601String()}')
      ..writeln('Exported: ${DateTime.now().toIso8601String()}')
      ..writeln('Conversation ID: ${conversation.id}')
      ..writeln();

    for (final message in conversation.messages) {
      final speaker = switch (message.role) {
        ConversationMessageRole.user => 'USER',
        ConversationMessageRole.assistant => 'ASSISTANT',
        ConversationMessageRole.system => 'SYSTEM',
      };
      buffer
        ..writeln('**$speaker** (${message.timestamp.toIso8601String()})')
        ..writeln()
        ..writeln(normalizeAssistantContent(message.content));

      if (message.sources.isNotEmpty) {
        buffer.writeln();
        buffer.writeln('Sources:');
        for (final source in message.sources) {
          buffer.writeln('- [${source.title}](${source.url})');
        }
      }

      if (message.messageType == ConversationMessageType.mediaResult) {
        final provider = message.payload['provider']?.toString() ?? '';
        final trackName = message.payload['trackName']?.toString() ?? '';
        if (provider.isNotEmpty || trackName.isNotEmpty) {
          buffer
            ..writeln()
            ..writeln('Media: $provider ${trackName.isNotEmpty ? '• $trackName' : ''}'.trim());
        }
      }

      if (message.messageType == ConversationMessageType.systemResult) {
        final detail = message.payload['detail']?.toString() ?? '';
        if (detail.isNotEmpty) {
          buffer
            ..writeln()
            ..writeln('Detail: $detail');
        }
      }

      buffer
        ..writeln()
        ..writeln('---')
        ..writeln();
    }

    await File(savePath).writeAsString(buffer.toString());
    return savePath;
  }

  @override
  void dispose() {
    _persistDebounce?.cancel();
    _chatProvider.removeListener(_onChatChanged);
    _sessionProvider.removeListener(_onSessionChanged);
    super.dispose();
  }
}
