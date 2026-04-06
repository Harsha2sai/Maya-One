import 'package:flutter/material.dart';

import '../../ui/theme/app_theme.dart';

enum ConversationOverflowAction {
  rename,
  export,
  moveToProject,
  archive,
  delete,
}

class ConversationOverflowMenu extends StatelessWidget {
  final ValueChanged<ConversationOverflowAction> onSelected;
  final bool visible;
  final Key? buttonKey;

  const ConversationOverflowMenu({
    super.key,
    required this.onSelected,
    required this.visible,
    this.buttonKey,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 120),
      curve: Curves.easeOut,
      opacity: visible ? 1 : 0,
        child: IgnorePointer(
          ignoring: !visible,
          child: PopupMenuButton<ConversationOverflowAction>(
          key: buttonKey,
          tooltip: 'Chat options',
          elevation: 6,
          color: ZoyaTheme.sidebarBg,
          constraints: const BoxConstraints.tightFor(width: 210),
          position: PopupMenuPosition.under,
          padding: EdgeInsets.zero,
          splashRadius: 16,
          menuPadding: const EdgeInsets.symmetric(vertical: 4),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: BorderSide(color: ZoyaTheme.glassBorder),
          ),
          onSelected: onSelected,
          child: const SizedBox(
            width: 28,
            height: 28,
            child: Center(
              child: Icon(
                Icons.more_horiz,
                size: 16,
                color: Colors.white70,
              ),
            ),
          ),
          itemBuilder: (context) {
            final errorColor = Theme.of(context).colorScheme.error;
            return [
              _menuItem(
                value: ConversationOverflowAction.rename,
                icon: Icons.edit_outlined,
                label: 'Rename',
              ),
              _menuItem(
                value: ConversationOverflowAction.export,
                icon: Icons.download_outlined,
                label: 'Export chat',
              ),
              _menuItem(
                value: ConversationOverflowAction.moveToProject,
                icon: Icons.folder_outlined,
                label: 'Move to project',
              ),
              _menuItem(
                value: ConversationOverflowAction.archive,
                icon: Icons.archive_outlined,
                label: 'Archive',
              ),
              const PopupMenuDivider(height: 10),
              _menuItem(
                value: ConversationOverflowAction.delete,
                icon: Icons.delete_outline,
                label: 'Delete',
                textColor: errorColor,
                iconColor: errorColor,
              ),
            ];
          },
        ),
      ),
    );
  }

  PopupMenuEntry<ConversationOverflowAction> _menuItem({
    required ConversationOverflowAction value,
    required IconData icon,
    required String label,
    Color? textColor,
    Color? iconColor,
  }) {
    final resolvedText = textColor ?? ZoyaTheme.textMain;
    final resolvedIcon = iconColor ?? ZoyaTheme.textMuted;

    return PopupMenuItem<ConversationOverflowAction>(
      value: value,
      height: 34,
      padding: EdgeInsets.zero,
      child: _OverflowMenuRow(
        icon: icon,
        label: label,
        textColor: resolvedText,
        iconColor: resolvedIcon,
      ),
    );
  }
}

class _OverflowMenuRow extends StatefulWidget {
  final IconData icon;
  final String label;
  final Color iconColor;
  final Color textColor;

  const _OverflowMenuRow({
    required this.icon,
    required this.label,
    required this.iconColor,
    required this.textColor,
  });

  @override
  State<_OverflowMenuRow> createState() => _OverflowMenuRowState();
}

class _OverflowMenuRowState extends State<_OverflowMenuRow> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          curve: Curves.easeOut,
          height: 34,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: _hover ? Colors.white.withValues(alpha: 0.06) : Colors.transparent,
            borderRadius: BorderRadius.circular(6),
          ),
          child: Row(
            children: [
              Icon(widget.icon, size: 16, color: widget.iconColor),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: ZoyaTheme.fontBody.copyWith(
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    color: widget.textColor,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
