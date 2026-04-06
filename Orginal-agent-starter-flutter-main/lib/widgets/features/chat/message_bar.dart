import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import '../../../ui/theme/app_theme.dart';
import 'attachment_preview.dart';

class MessageBarButton extends StatelessWidget {
  final GestureTapCallback? onTap;
  final bool isEnabled;
  final FaIconData icon;
  final Color? color;
  final Color? iconColor;

  const MessageBarButton({
    super.key,
    required this.icon,
    this.isEnabled = true,
    this.onTap,
    this.color,
    this.iconColor,
  });

  @override
  Widget build(BuildContext ctx) => ClipOval(
        child: Material(
          color: isEnabled ? (color ?? ZoyaTheme.accent) : const Color(0xFF1E1E2E),
          child: InkWell(
            onTap: isEnabled ? onTap : null,
            child: Container(
              padding: const EdgeInsets.all(10),
              width: 40,
              height: 40,
              alignment: Alignment.center,
              child: FaIcon(
                icon,
                color: iconColor ?? (isEnabled ? Colors.black : Colors.white24),
                size: 16,
              ),
            ),
          ),
        ),
      );
}

class MessageBar extends StatefulWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final GestureTapCallback? onSendTap;
  final bool isSendEnabled;
  final List<File> attachments;
  final Function(File)? onAttachmentAdded;
  final Function(File)? onAttachmentRemoved;
  final bool isUploading;

  const MessageBar({
    super.key,
    required this.controller,
    required this.focusNode,
    this.isSendEnabled = true,
    this.onSendTap,
    this.attachments = const [],
    this.onAttachmentAdded,
    this.onAttachmentRemoved,
    this.isUploading = false,
  });

  @override
  State<MessageBar> createState() => _MessageBarState();
}

class _MessageBarState extends State<MessageBar> {
  void _handleSend() {
    if (widget.isSendEnabled && widget.onSendTap != null) {
      widget.onSendTap!();
    }
    // Keep the composer focused after send so users can continue typing.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (!widget.focusNode.hasFocus) {
        widget.focusNode.requestFocus();
      }
    });
  }

  Future<void> _pickFiles(FileType type) async {
    try {
      final result = await FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: type,
      );
      if (result != null && widget.onAttachmentAdded != null) {
        for (var path in result.paths) {
          if (path != null) {
            widget.onAttachmentAdded!(File(path));
          }
        }
      }
    } catch (e) {
      debugPrint('Error picking files: $e');
    }
  }

  void _showAddMenu(BuildContext context) {
    final RenderBox button = context.findRenderObject() as RenderBox;
    final RenderBox overlay = Navigator.of(context).overlay!.context.findRenderObject() as RenderBox;
    final RelativeRect position = RelativeRect.fromRect(
      Rect.fromPoints(
        button.localToGlobal(Offset.zero, ancestor: overlay),
        button.localToGlobal(button.size.bottomRight(Offset.zero), ancestor: overlay),
      ),
      Offset.zero & overlay.size,
    );

    unawaited(showMenu<String>(
      context: context,
      position: position,
      color: const Color(0xFF1E1E2E), // Match dark theme
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      items: [
        PopupMenuItem(
          value: 'images',
          child: Row(
            children: [
              FaIcon(FontAwesomeIcons.image, size: 16, color: ZoyaTheme.accent),
              const SizedBox(width: 12),
              const Text('Images', style: TextStyle(color: Colors.white, fontSize: 13)),
            ],
          ),
        ),
        PopupMenuItem(
          value: 'files',
          child: Row(
            children: [
              FaIcon(FontAwesomeIcons.fileLines, size: 16, color: ZoyaTheme.accent),
              const SizedBox(width: 12),
              const Text('Files', style: TextStyle(color: Colors.white, fontSize: 13)),
            ],
          ),
        ),
        PopupMenuItem(
          value: 'drive',
          child: Row(
            children: [
              FaIcon(FontAwesomeIcons.googleDrive, size: 16, color: ZoyaTheme.accent),
              const SizedBox(width: 12),
              const Text('Cloud Drive', style: TextStyle(color: Colors.white, fontSize: 13)),
            ],
          ),
        ),
      ],
    ).then((value) {
      if (value == 'images') unawaited(_pickFiles(FileType.image));
      if (value == 'files') unawaited(_pickFiles(FileType.any));
      if (value == 'drive') {
        // Drive integration usually needs a specific SDK,
        // using generic picker as placeholder for now
        unawaited(_pickFiles(FileType.any));
      }
    }));
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(25),
      ),
      padding: const EdgeInsets.symmetric(
        vertical: 7,
        horizontal: 10,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (widget.attachments.isNotEmpty)
            Container(
              height: 90,
              padding: const EdgeInsets.only(bottom: 8, left: 4),
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: widget.attachments.length + (widget.isUploading ? 1 : 0),
                itemBuilder: (context, index) {
                  if (widget.isUploading && index == widget.attachments.length) {
                    return const Padding(
                      padding: EdgeInsets.all(16.0),
                      child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
                    );
                  }
                  return AttachmentPreview(
                    file: widget.attachments[index],
                    onRemove: () => widget.onAttachmentRemoved?.call(widget.attachments[index]),
                  );
                },
              ),
            ),
          Row(
            children: [
              // File Picker Button (+) with Menu
              Builder(
                builder: (ctx) => MessageBarButton(
                  icon: FontAwesomeIcons.plus,
                  isEnabled: widget.isSendEnabled,
                  color: Colors.white.withValues(alpha: 0.1),
                  iconColor: Colors.white,
                  onTap: () => _showAddMenu(ctx),
                ),
              ),
              const SizedBox(width: 8),

              Expanded(
                child: TextField(
                  enabled: widget.isSendEnabled,
                  focusNode: widget.focusNode,
                  controller: widget.controller,
                  style: const TextStyle(color: Colors.white, fontSize: 15),
                  decoration: const InputDecoration.collapsed(
                    hintText: 'Message...',
                    hintStyle: TextStyle(color: Colors.white54),
                  ),
                  minLines: 1,
                  maxLines: 4,
                  textInputAction: TextInputAction.send,
                  keyboardType: TextInputType.multiline,
                  onSubmitted: (_) => _handleSend(),
                ),
              ),

              const SizedBox(width: 8),

              // Send Button
              MessageBarButton(
                icon: FontAwesomeIcons.arrowUp,
                isEnabled: widget.isSendEnabled,
                onTap: _handleSend,
              )
            ],
          ),
        ],
      ),
    );
  }
}
