import 'package:flutter/material.dart';
import 'dart:async';
import 'composer_bar.dart';
import 'conversation_header.dart';
import 'conversation_list.dart';
import 'live_status_row.dart';
import 'conversation_switch_blocker.dart';

class ChatOverlay extends StatefulWidget {
  final VoidCallback onClose;
  const ChatOverlay({super.key, required this.onClose});

  @override
  State<ChatOverlay> createState() => _ChatOverlayState();
}

class _ChatOverlayState extends State<ChatOverlay> with SingleTickerProviderStateMixin {
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

    unawaited(_entryController.forward());
  }

  @override
  void dispose() {
    _entryController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
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
                        ConversationHeader(
                          title: 'Chat',
                          onClose: widget.onClose,
                        ),
                        const ConversationList(),
                      ],
                    ),
                  ),

                  const Positioned(
                    bottom: 104,
                    left: 0,
                    right: 0,
                    child: Center(
                      child: LiveStatusRow(),
                    ),
                  ),
                  const ComposerBar(),

                  const Positioned.fill(
                    child: ConversationSwitchBlocker(),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
