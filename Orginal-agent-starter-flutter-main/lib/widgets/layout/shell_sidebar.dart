import 'dart:async';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import '../../state/models/conversation_models.dart';
import '../../state/providers/auth_provider.dart';
import '../../state/providers/conversation_history_provider.dart';
import '../../state/controllers/workspace_controller.dart';
import '../../ui/theme/app_theme.dart';
import '../sidebar/conversation_overflow_menu.dart';
import '../settings/settings_dialog.dart';
import 'system_menu.dart';

class ShellSidebar extends StatefulWidget {
  final String activePage;
  final Function(String) onNavigate;
  final double width;

  const ShellSidebar({
    super.key,
    required this.activePage,
    required this.onNavigate,
    this.width = 280,
  });

  @override
  State<ShellSidebar> createState() => _ShellSidebarState();
}

class _ShellSidebarState extends State<ShellSidebar> {
  Future<bool> _confirmTaskInterruption() async {
    final history = context.read<ConversationHistoryProvider>();
    if (!history.hasRunningTask) {
      return true;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: ZoyaTheme.sidebarBg,
          title: const Text('Task in progress'),
          content: const Text(
            'A task is still running in this conversation. Switching now will interrupt it and mark the thread accordingly.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Stay'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Switch anyway'),
            ),
          ],
        );
      },
    );
    return confirmed == true;
  }

  Future<void> _handleNewChat() async {
    final history = context.read<ConversationHistoryProvider>();
    final workspace = context.read<WorkspaceController>();
    final allowInterruption = await _confirmTaskInterruption();
    if (!allowInterruption) {
      return;
    }

    final success = await history.createConversation(
      allowTaskInterruption: history.hasRunningTask,
    );
    if (!mounted || !success) {
      return;
    }

    workspace.setCurrentPage('home');
  }

  Future<void> _handleConversationTap(ConversationRecord conversation) async {
    final history = context.read<ConversationHistoryProvider>();
    final workspace = context.read<WorkspaceController>();
    if (conversation.id == history.activeConversationId) {
      workspace.setCurrentPage('home');
      return;
    }

    final allowInterruption = await _confirmTaskInterruption();
    if (!allowInterruption) {
      return;
    }

    final success = await history.activateConversation(
      conversation.id,
      allowTaskInterruption: history.hasRunningTask,
    );
    if (!mounted || !success) {
      return;
    }

    workspace.setCurrentPage('home');
  }

  Future<void> _showRenameDialog(ConversationRecord conversation) async {
    final controller = TextEditingController(text: conversation.title);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: ZoyaTheme.sidebarBg,
          title: const Text('Rename chat'),
          content: TextField(
            controller: controller,
            maxLength: 80,
            decoration: const InputDecoration(
              hintText: 'Enter a title',
            ),
            autofocus: true,
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Save'),
            ),
          ],
        );
      },
    );

    if (confirmed == true) {
      await context.read<ConversationHistoryProvider>().renameConversation(
            conversation.id,
            controller.text,
          );
    }
  }

  Future<void> _showMoveToProjectDialog(ConversationRecord conversation) async {
    final history = context.read<ConversationHistoryProvider>();
    String? selectedProjectId = conversation.projectId;
    final nameController = TextEditingController();
    final descriptionController = TextEditingController();

    final apply = await showDialog<bool>(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            final projects = history.projects;
            return AlertDialog(
              backgroundColor: ZoyaTheme.sidebarBg,
              title: const Text('Move to project'),
              content: SizedBox(
                width: 420,
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _ProjectSelectionTile(
                        key: const Key('move_project_option_unassigned'),
                        title: 'Unassigned',
                        selected: selectedProjectId == null,
                        onTap: () => setModalState(() => selectedProjectId = null),
                      ),
                      for (final project in projects)
                        _ProjectSelectionTile(
                          key: Key('move_project_option_${project.id}'),
                          title: project.name,
                          subtitle: project.description.trim().isEmpty ? null : project.description,
                          selected: selectedProjectId == project.id,
                          onTap: () => setModalState(() => selectedProjectId = project.id),
                        ),
                      const Divider(height: 28),
                      Text(
                        'Create project',
                        style: ZoyaTheme.fontBody.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: nameController,
                        decoration: const InputDecoration(
                          labelText: 'Project name',
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: descriptionController,
                        minLines: 2,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Description',
                        ),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: () async {
                          final trimmedName = nameController.text.trim();
                          if (trimmedName.isEmpty) {
                            return;
                          }
                          final project = await history.createProject(
                            trimmedName,
                            description: descriptionController.text,
                          );
                          setModalState(() {
                            selectedProjectId = project.id;
                            nameController.clear();
                            descriptionController.clear();
                          });
                        },
                        icon: const Icon(Icons.add),
                        label: const Text('Create and select'),
                      ),
                    ],
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(false),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(context).pop(true),
                  child: const Text('Apply'),
                ),
              ],
            );
          },
        );
      },
    );

    if (apply == true) {
      await history.moveConversationToProject(conversation.id, selectedProjectId);
    }
  }

  Future<void> _archiveConversation(ConversationRecord conversation) async {
    final history = context.read<ConversationHistoryProvider>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: ZoyaTheme.sidebarBg,
          title: const Text('Archive chat'),
          content: Text('Move "${conversation.title}" out of Your Chats?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Archive'),
            ),
          ],
        );
      },
    );
    if (confirmed == true) {
      await history.archiveConversation(conversation.id);
    }
  }

  Future<void> _deleteConversation(ConversationRecord conversation) async {
    final history = context.read<ConversationHistoryProvider>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: ZoyaTheme.sidebarBg,
          title: const Text('Delete chat'),
          content: Text('Permanently delete "${conversation.title}"?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Colors.redAccent),
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Delete'),
            ),
          ],
        );
      },
    );
    if (confirmed == true) {
      await history.deleteConversation(conversation.id);
      if (mounted) {
        context.read<WorkspaceController>().setCurrentPage('home');
      }
    }
  }

  Future<void> _exportConversation(ConversationRecord conversation) async {
    final path = await context.read<ConversationHistoryProvider>().exportConversation(conversation.id);
    if (!mounted) {
      return;
    }

    final messenger = ScaffoldMessenger.of(context);
    if (path == null) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Export canceled or unavailable on this platform.')),
      );
      return;
    }

    messenger.showSnackBar(
      SnackBar(content: Text('Chat exported to $path')),
    );
  }

  Future<void> _handleMenuAction(
    ConversationOverflowAction action,
    ConversationRecord conversation,
  ) async {
    switch (action) {
      case ConversationOverflowAction.rename:
        await _showRenameDialog(conversation);
        return;
      case ConversationOverflowAction.export:
        await _exportConversation(conversation);
        return;
      case ConversationOverflowAction.moveToProject:
        await _showMoveToProjectDialog(conversation);
        return;
      case ConversationOverflowAction.archive:
        await _archiveConversation(conversation);
        return;
      case ConversationOverflowAction.delete:
        await _deleteConversation(conversation);
        return;
    }
  }

  @override
  Widget build(BuildContext context) {
    final history = context.watch<ConversationHistoryProvider>();
    final isCompact = MediaQuery.of(context).size.width < 900;
    final conversations = history.conversations;

    return Container(
      width: widget.width,
      decoration: BoxDecoration(
        color: ZoyaTheme.sidebarBg,
        border: Border(
          right: BorderSide(color: ZoyaTheme.glassBorder),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.5),
            blurRadius: 30,
            offset: const Offset(4, 0),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.fromLTRB(18, 16, 14, 16),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Text(
                      'MAYA',
                      style: ZoyaTheme.fontDisplay.copyWith(
                        fontSize: 22,
                        fontWeight: FontWeight.bold,
                        color: ZoyaTheme.accent,
                        letterSpacing: 1.6,
                        shadows: [
                          Shadow(color: ZoyaTheme.accentGlow, blurRadius: 10),
                        ],
                      ),
                    ),
                    const SystemMenu(),
                  ],
                ),
                _SidebarIconButton(
                  icon: FontAwesomeIcons.chevronLeft,
                  onTap: () => context.read<WorkspaceController>().toggleSidebar(),
                  tooltip: 'Close Sidebar',
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(10, 10, 10, 6),
            child: _NewChatButton(
              key: const Key('sidebar_new_chat_button'),
              onTap: _handleNewChat,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(10, 10, 10, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SidebarSectionTitle(label: 'WORKSPACE'),
                _NavItem(
                  icon: FontAwesomeIcons.solidImage,
                  label: 'Images',
                  isActive: widget.activePage == 'images',
                  badge: 'NEW',
                  onTap: () => widget.onNavigate('images'),
                ),
                const SizedBox(height: 8),
                _NavItem(
                  icon: FontAwesomeIcons.tableCellsLarge,
                  label: 'Apps',
                  isActive: widget.activePage == 'apps',
                  onTap: () => widget.onNavigate('apps'),
                ),
                const SizedBox(height: 8),
                _NavItem(
                  icon: FontAwesomeIcons.folder,
                  label: 'Projects',
                  isActive: widget.activePage == 'projects',
                  onTap: () => widget.onNavigate('projects'),
                ),
              ],
            ),
          ),
          Container(
            height: 1,
            color: ZoyaTheme.glassBorder,
            margin: const EdgeInsets.symmetric(vertical: 10),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _SidebarSectionTitle(label: 'YOUR CHATS'),
                  Expanded(
                    child: conversations.isEmpty
                        ? Center(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 18),
                              child: Text(
                                'Start a new chat to save conversation history here.',
                                textAlign: TextAlign.center,
                                style: ZoyaTheme.fontBody.copyWith(
                                  color: ZoyaTheme.textMuted,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                          )
                        : ListView.builder(
                            itemCount: conversations.length,
                            itemBuilder: (context, index) {
                              final conversation = conversations[index];
                              return _ConversationListItem(
                                key: Key('sidebar_chat_row_${conversation.id}'),
                                conversation: conversation,
                                isCompact: isCompact,
                                isActive:
                                    conversation.id == history.activeConversationId && widget.activePage != 'projects',
                                onTap: () => _handleConversationTap(conversation),
                                onMenuAction: (action) => _handleMenuAction(action, conversation),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.fromLTRB(10, 14, 10, 18),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SidebarSectionTitle(label: 'SETTINGS'),
                _NavItem(
                  icon: FontAwesomeIcons.gear,
                  label: 'Settings',
                  isActive: widget.activePage == 'settings',
                  onTap: () {
                    unawaited(showDialog(
                      context: context,
                      builder: (context) => const SettingsDialog(),
                    ));
                  },
                ),
                const SizedBox(height: 12),
                const _UserProfile(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SidebarIconButton extends StatelessWidget {
  final FaIconData icon;
  final VoidCallback onTap;
  final String tooltip;

  const _SidebarIconButton({
    required this.icon,
    required this.onTap,
    required this.tooltip,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: FaIcon(icon, size: 16, color: ZoyaTheme.textMuted),
        ),
      ),
    );
  }
}

class _NewChatButton extends StatefulWidget {
  final VoidCallback onTap;

  const _NewChatButton({super.key, required this.onTap});

  @override
  State<_NewChatButton> createState() => _NewChatButtonState();
}

class _NewChatButtonState extends State<_NewChatButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          curve: Curves.easeOut,
          height: 42,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: _hover ? _sidebarHoverColor : Colors.transparent,
            border: Border.all(color: ZoyaTheme.glassBorder),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Row(
            children: [
              FaIcon(
                FontAwesomeIcons.penToSquare,
                size: 16,
                color: _hover ? ZoyaTheme.accent : ZoyaTheme.textMain,
              ),
              const SizedBox(width: 10),
              Text(
                'New chat',
                style: ZoyaTheme.fontBody.copyWith(
                  color: _hover ? ZoyaTheme.accent : ZoyaTheme.textMain,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatefulWidget {
  final FaIconData icon;
  final String label;
  final bool isActive;
  final String? badge;
  final VoidCallback onTap;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.isActive,
    this.badge,
    required this.onTap,
  });

  @override
  State<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends State<_NavItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final active = widget.isActive || _hover;

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          curve: Curves.easeOut,
          height: 42,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: _sidebarRowBackground(isActive: widget.isActive, hovered: _hover),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Row(
            children: [
              SizedBox(
                width: 16,
                child: FaIcon(
                  widget.icon,
                  size: 16,
                  color: active ? ZoyaTheme.accent : const Color(0xFFB0B8C4),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.label,
                  style: ZoyaTheme.fontBody.copyWith(
                    color: active ? ZoyaTheme.accent : const Color(0xFFB0B8C4),
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
              if (widget.badge != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: ZoyaTheme.accent,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    widget.badge!,
                    style: ZoyaTheme.fontDisplay.copyWith(
                      color: Colors.black,
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
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

class _ConversationListItem extends StatefulWidget {
  final ConversationRecord conversation;
  final bool isActive;
  final bool isCompact;
  final VoidCallback onTap;
  final ValueChanged<ConversationOverflowAction> onMenuAction;

  const _ConversationListItem({
    super.key,
    required this.conversation,
    required this.isActive,
    required this.isCompact,
    required this.onTap,
    required this.onMenuAction,
  });

  @override
  State<_ConversationListItem> createState() => _ConversationListItemState();
}

class _ConversationListItemState extends State<_ConversationListItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final showMenu = widget.isCompact || _hover || widget.isActive;
    final preview = widget.conversation.preview.trim();

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          curve: Curves.easeOut,
          height: 42,
          margin: const EdgeInsets.only(bottom: 4),
          decoration: BoxDecoration(
            color: _sidebarRowBackground(isActive: widget.isActive, hovered: _hover),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Row(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 120),
                curve: Curves.easeOut,
                width: 2,
                margin: const EdgeInsets.symmetric(vertical: 2),
                decoration: BoxDecoration(
                  color: widget.isActive ? Theme.of(context).colorScheme.primary : Colors.transparent,
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
              const SizedBox(width: 10),
              FaIcon(
                FontAwesomeIcons.commentDots,
                size: 16,
                color: widget.isActive
                    ? ZoyaTheme.accent
                    : _hover
                        ? ZoyaTheme.textMain
                        : ZoyaTheme.textMuted.withValues(alpha: 0.7),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.conversation.title,
                      style: ZoyaTheme.fontBody.copyWith(
                        color: widget.isActive ? ZoyaTheme.textMain : const Color(0xFFB0B8C4),
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (preview.isNotEmpty)
                      Text(
                        preview,
                        style: ZoyaTheme.fontBody.copyWith(
                          color: ZoyaTheme.textMuted.withValues(alpha: 0.65),
                          fontSize: 12,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              ConversationOverflowMenu(
                buttonKey: Key('sidebar_chat_menu_${widget.conversation.id}'),
                visible: showMenu,
                onSelected: widget.onMenuAction,
              ),
              const SizedBox(width: 6),
            ],
          ),
        ),
      ),
    );
  }
}

class _ProjectSelectionTile extends StatelessWidget {
  final String title;
  final String? subtitle;
  final bool selected;
  final VoidCallback onTap;

  const _ProjectSelectionTile({
    super.key,
    required this.title,
    this.subtitle,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        margin: const EdgeInsets.only(bottom: 6),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: selected ? ZoyaTheme.accent.withValues(alpha: 0.10) : Colors.white.withValues(alpha: 0.02),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: selected ? ZoyaTheme.accent.withValues(alpha: 0.45) : Colors.white.withValues(alpha: 0.08),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title),
                  if (subtitle != null && subtitle!.trim().isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      subtitle!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ZoyaTheme.fontBody.copyWith(
                        color: Colors.white70,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            Icon(
              selected ? Icons.check_circle : Icons.radio_button_unchecked,
              size: 18,
              color: selected ? ZoyaTheme.accent : Colors.white38,
            ),
          ],
        ),
      ),
    );
  }
}

const Color _sidebarHoverColor = Color(0x141B2430);
const Color _sidebarActiveColor = Color(0x1F162635);

Color _sidebarRowBackground({required bool isActive, required bool hovered}) {
  if (isActive) {
    return _sidebarActiveColor;
  }
  if (hovered) {
    return _sidebarHoverColor;
  }
  return Colors.transparent;
}

class _SidebarSectionTitle extends StatelessWidget {
  final String label;

  const _SidebarSectionTitle({required this.label});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 16, 12, 6),
      child: Text(
        label,
        style: ZoyaTheme.fontBody.copyWith(
          fontSize: 11,
          letterSpacing: 0.8,
          fontWeight: FontWeight.w600,
          color: ZoyaTheme.textMuted.withValues(alpha: 0.55),
        ),
      ),
    );
  }
}

class _UserProfile extends StatefulWidget {
  const _UserProfile();

  @override
  State<_UserProfile> createState() => _UserProfileState();
}

class _UserProfileState extends State<_UserProfile> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider?>();
    final isAuthenticated = auth?.isAuthenticated == true;
    final user = auth?.user;
    final userName = user?.email?.split('@')[0] ?? 'Guest User';
    final initials = userName.substring(0, 2).toUpperCase();

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: ZoyaTheme.accent.withValues(alpha: 0.05),
          border: Border.all(
            color: _hover ? ZoyaTheme.accent : ZoyaTheme.accent.withValues(alpha: 0.1),
          ),
          borderRadius: BorderRadius.circular(10),
          boxShadow: _hover ? [const BoxShadow(color: Color.fromRGBO(0, 243, 255, 0.1), blurRadius: 15)] : [],
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(
                  colors: [ZoyaTheme.accent, ZoyaTheme.secondaryAccent],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                boxShadow: [
                  BoxShadow(color: ZoyaTheme.accentGlow, blurRadius: 15),
                ],
              ),
              child: Center(
                child: Text(
                  initials,
                  style: ZoyaTheme.fontDisplay.copyWith(
                    color: Colors.black,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    userName,
                    style: ZoyaTheme.fontBody.copyWith(
                      color: ZoyaTheme.textMain,
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    isAuthenticated ? 'Online' : 'Guest',
                    style: ZoyaTheme.fontBody.copyWith(
                      color: isAuthenticated ? ZoyaTheme.success : ZoyaTheme.textMuted,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
