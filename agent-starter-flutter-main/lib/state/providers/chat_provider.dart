import 'package:livekit_client/livekit_client.dart' as lk;
import '../base_provider.dart';

class ChatMessage {
  final String id;
  final String content;
  final DateTime timestamp;
  final bool isUser;
  final bool isAgent;

  ChatMessage({
    required this.id,
    required this.content,
    required this.timestamp,
    required this.isUser,
    required this.isAgent,
  });
}

class ChatProvider extends BaseProvider {
  final List<ChatMessage> _messages = [];
  bool _isTyping = false;

  ChatProvider() : super('ChatProvider');

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  bool get isTyping => _isTyping;
  bool get hasMessages => _messages.isNotEmpty;

  /// Add a message to the chat
  void addMessage(ChatMessage message) {
    _messages.add(message);
    log('Message added: ${message.content.substring(0, message.content.length > 50 ? 50 : message.content.length)}...');
    notifyListeners();
  }

  /// Add a message from a LiveKit transcription event
  void addTranscription(lk.TranscriptionEvent event) {
    if (event.segments.isEmpty) return;
    
    final participant = event.participant;
    final isAgent = participant.kind == lk.ParticipantKind.AGENT;
    final isUser = !isAgent && participant is lk.LocalParticipant;
    
    final text = event.segments.map((s) => s.text).join(' ');
    // 'isFinal' or 'final' property check
    final isFinal = event.segments.every((s) => s.isFinal);
    
    final msgId = 'trans_${event.segments.first.id}'; // Use segment ID if available or generate one
    
    final existingIdx = _messages.indexWhere((m) => m.id == msgId);
    
    if (existingIdx != -1) {
      _messages[existingIdx] = ChatMessage(
        id: msgId,
        content: text,
        timestamp: _messages[existingIdx].timestamp,
        isUser: isUser,
        isAgent: isAgent,
      );
    } else {
      _messages.add(ChatMessage(
        id: msgId,
        content: text,
        timestamp: DateTime.now(),
        isUser: isUser,
        isAgent: isAgent,
      ));
    }
    
    // Auto-clear typing indicator if we got content
    if (isAgent) _isTyping = !isFinal;

    notifyListeners();
  }

  /// Set typing indicator
  void setTyping(bool value) {
    if (_isTyping != value) {
      _isTyping = value;
      log('Typing: $value');
      notifyListeners();
    }
  }

  /// Clear all messages
  void clearMessages() {
    _messages.clear();
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
    super.dispose();
  }
}
