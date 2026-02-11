import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:chat_bubbles/chat_bubbles.dart';
import '../../state/providers/chat_provider.dart';
import '../../state/providers/session_provider.dart';
import '../../ui/zoya_theme.dart';
import '../message_bar.dart' as widgets;

class ChatOverlay extends StatefulWidget {
  final VoidCallback onClose;
  const ChatOverlay({super.key, required this.onClose});

  @override
  State<ChatOverlay> createState() => _ChatOverlayState();
}

class _ChatOverlayState extends State<ChatOverlay> with SingleTickerProviderStateMixin {
  final ScrollController _scrollController = ScrollController();
  final TextEditingController _textController = TextEditingController();
  late AnimationController _entryController;
  late Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _entryController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    );
    _slideAnim = Tween<Offset>(
      begin: const Offset(0, 0.1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _entryController, curve: Curves.easeOutCubic));
    
    _entryController.forward();
  }

  @override
  void dispose() {
    _entryController.dispose();
    _scrollController.dispose();
    _textController.dispose();
    super.dispose();
  }

  Future<void> _handleSend() async {
    final text = _textController.text.trim();
    if (text.isNotEmpty) {
      try {
        debugPrint('Sending message: $text');
        
        // Add to local chat immediately for UI responsiveness
        context.read<ChatProvider>().addMessage(
          ChatMessage(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            content: text,
            timestamp: DateTime.now(),
            isUser: true,
            isAgent: false,
          )
        );
        _textController.clear();

        // Send to LiveKit session (for agent to hear)
        await context.read<SessionProvider>().sendUserMessage(text);
        debugPrint('✅ Message sent to backend confirmed');
      } catch (e) {
        debugPrint('❌ Failed to send message: $e');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final chat = context.watch<ChatProvider>();
    
    // Auto scroll on new messages
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());

    return SlideTransition(
      position: _slideAnim,
      child: FadeTransition(
        opacity: _entryController,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 100), // Equal padding for true center
          child: Center(
            child: Container(
              constraints: const BoxConstraints(maxWidth: 875), // 25% wider (700 * 1.25)
              child: Stack(
                children: [
              // 1. Messages Layer (Integrated with page background)
              Positioned.fill(
                child: Column(
                  children: [
                    // Minimal Header (Optional, maybe just a close button or title)
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Chat',
                            style: ZoyaTheme.fontDisplay.copyWith(
                              fontSize: 18,
                              color: Colors.white,
                              letterSpacing: 0.5,
                            ),
                          ),
                          IconButton(
                            onPressed: widget.onClose,
                            icon: const Icon(Icons.close, color: Colors.white70),
                            tooltip: 'Close Chat',
                          ),
                        ],
                      ),
                    ),

                    // Message List
                    Expanded(
                      child: ListView.builder(
                        controller: _scrollController,
                        padding: const EdgeInsets.fromLTRB(24, 0, 24, 100), // Bottom padding for floating bar
                        itemCount: chat.messages.length,
                        itemBuilder: (context, index) {
                          final msg = chat.messages[index];
                          return _AnimatedMessage(
                            key: ValueKey(msg.id),
                            child: Align(
                              alignment: msg.isUser ? Alignment.centerRight : Alignment.centerLeft,
                              child: Container(
                                constraints: const BoxConstraints(maxWidth: 600),
                                margin: const EdgeInsets.only(bottom: 16),
                                child: BubbleSpecialThree(
                                  text: msg.content,
                                  color: msg.isUser 
                                      ? ZoyaTheme.accent.withValues(alpha: 0.2) 
                                      : const Color(0xFF1E1E2E), // Darker bubble for agent
                                  tail: true,
                                  isSender: msg.isUser,
                                  textStyle: ZoyaTheme.fontBody.copyWith(
                                    color: Colors.white,
                                    fontSize: 15,
                                    height: 1.4,
                                  ),
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),

              // 2. Typing Indicator (Floating above list, below input)
              if (chat.isTyping)
                Positioned(
                  bottom: 90,
                  left: 32,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: Colors.black45,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Text('Agent is thinking...', 
                      style: TextStyle(color: Colors.white70, fontSize: 12, fontStyle: FontStyle.italic)
                    ),
                  ),
                ),

              // 3. Floating Input Bar Layer - positioned at very bottom
              Align(
                alignment: Alignment.bottomCenter,
                child: Padding(
                  padding: const EdgeInsets.only(left: 20, right: 20, bottom: 20),
                  child: Container(
                    constraints: const BoxConstraints(maxWidth: 800),
                    decoration: BoxDecoration(
                      color: const Color(0xFF222222).withValues(alpha: 0.9),
                      borderRadius: BorderRadius.circular(30),
                      border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.5),
                          blurRadius: 20,
                          offset: const Offset(0, 5),
                        ),
                      ],
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    child: widgets.MessageBar(
                      controller: _textController,
                      onSendTap: _handleSend,
                    ),
                  ),
                ),
              ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _scrollToBottom() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }
  }
}

class _AnimatedMessage extends StatefulWidget {
  final Widget child;
  const _AnimatedMessage({super.key, required this.child});

  @override
  State<_AnimatedMessage> createState() => _AnimatedMessageState();
}

class _AnimatedMessageState extends State<_AnimatedMessage> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scale;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 300));
    _scale = CurvedAnimation(parent: _controller, curve: Curves.easeOutBack);
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(scale: _scale, child: Padding(padding: const EdgeInsets.only(bottom: 16), child: widget.child));
  }
}
