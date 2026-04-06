import 'package:flutter/foundation.dart';

import '../models/conversation_models.dart';
import '../models/workspace_models.dart';
import '../providers/chat_provider.dart';
import '../providers/conversation_history_provider.dart';

class ConversationController extends ChangeNotifier {
  ChatProvider? _chatProvider;
  ConversationHistoryProvider? _historyProvider;
  String? _selectedResearchArtifactId;

  String? get selectedResearchArtifactId => _selectedResearchArtifactId;

  void bind(
    ChatProvider chatProvider,
    ConversationHistoryProvider historyProvider,
  ) {
    final chatChanged = !identical(_chatProvider, chatProvider);
    final historyChanged = !identical(_historyProvider, historyProvider);
    if (!chatChanged && !historyChanged) {
      return;
    }

    if (chatChanged) {
      _chatProvider?.removeListener(_notifyProxyChange);
      _chatProvider = chatProvider;
      _chatProvider?.addListener(_notifyProxyChange);
    }
    if (historyChanged) {
      _historyProvider?.removeListener(_notifyProxyChange);
      _historyProvider = historyProvider;
      _historyProvider?.addListener(_notifyProxyChange);
    }
    notifyListeners();
  }

  List<ChatMessage> get messages => List.unmodifiable(_chatProvider?.messages ?? const <ChatMessage>[]);
  bool get hasMessages => _chatProvider?.hasMessages ?? false;
  bool get isSwitchingConversation => _historyProvider?.isSwitchingConversation ?? false;
  String get activeConversationId => _historyProvider?.activeConversationId ?? '';
  ConversationRecord? get activeConversation => _historyProvider?.activeConversation;
  String get activeConversationTitle => activeConversation?.title ?? 'New chat';
  String get activeConversationPreview => activeConversation?.preview ?? '';
  List<ConversationRecord> get conversations =>
      List.unmodifiable(_historyProvider?.conversations ?? const <ConversationRecord>[]);
  List<ConversationRecord> get archivedConversations =>
      List.unmodifiable(_historyProvider?.archivedConversations ?? const <ConversationRecord>[]);
  List<ProjectRecord> get projects => List.unmodifiable(_historyProvider?.projects ?? const <ProjectRecord>[]);
  List<ConversationToolResultSummary> get recentToolResults =>
      List.unmodifiable(_chatProvider?.recentToolResults ?? const <ConversationToolResultSummary>[]);

  List<ResearchArtifactModel> get researchArtifacts {
    final conversation = activeConversation;
    if (conversation == null) {
      return const <ResearchArtifactModel>[];
    }

    return conversation.messages
        .where((message) => message.messageType == ConversationMessageType.researchResult)
        .map(
          (message) => ResearchArtifactModel(
            traceId: (message.payload['traceId'] ?? message.turnId ?? message.id).toString(),
            taskId: message.payload['taskId']?.toString() ?? '',
            query: message.payload['query']?.toString() ?? '',
            voiceSummary: message.content,
            displaySummary: message.content,
            citations: message.sources,
            sources: message.sources,
            confidence: message.payload['confidence'] is num
                ? (message.payload['confidence'] as num).toDouble()
                : double.tryParse(message.payload['confidence']?.toString() ?? '') ?? 0,
            generatedAt: message.timestamp,
          ),
        )
        .toList(growable: false);
  }

  ResearchArtifactModel? get selectedResearchArtifact {
    final artifacts = researchArtifacts;
    if (_selectedResearchArtifactId == null || artifacts.isEmpty) return null;
    try {
      return artifacts.firstWhere((a) => a.traceId == _selectedResearchArtifactId);
    } catch (_) {
      return null;
    }
  }

  void selectResearchArtifact(String? traceId) {
    if (_selectedResearchArtifactId != traceId) {
      _selectedResearchArtifactId = traceId;
      notifyListeners();
    }
  }

  List<ConversationMessageSnapshot> taskRelatedMessages(String? taskId) {
    final normalizedTaskId = taskId?.trim() ?? '';
    if (normalizedTaskId.isEmpty) {
      return const <ConversationMessageSnapshot>[];
    }
    final conversation = activeConversation;
    if (conversation == null) {
      return const <ConversationMessageSnapshot>[];
    }

    return conversation.messages
        .where((message) => message.payload['taskId']?.toString() == normalizedTaskId)
        .toList(growable: false);
  }

  Future<bool> createConversation({bool allowTaskInterruption = false}) {
    final history = _historyProvider;
    if (history == null) {
      return Future<bool>.value(false);
    }
    return history.createConversation(allowTaskInterruption: allowTaskInterruption);
  }

  Future<bool> activateConversation(String conversationId, {bool allowTaskInterruption = false}) {
    final history = _historyProvider;
    if (history == null) {
      return Future<bool>.value(false);
    }
    return history.activateConversation(
      conversationId,
      allowTaskInterruption: allowTaskInterruption,
    );
  }

  void _notifyProxyChange() {
    notifyListeners();
  }

  @override
  void dispose() {
    _chatProvider?.removeListener(_notifyProxyChange);
    _historyProvider?.removeListener(_notifyProxyChange);
    super.dispose();
  }
}
