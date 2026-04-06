import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/models/conversation_models.dart';
import '../../state/controllers/workspace_controller.dart';
import '../../state/providers/conversation_history_provider.dart';
import '../theme/app_theme.dart';

class ProjectsScreen extends StatefulWidget {
  const ProjectsScreen({super.key});

  @override
  State<ProjectsScreen> createState() => _ProjectsScreenState();
}

class _ProjectsScreenState extends State<ProjectsScreen> {
  String? _selectedProjectId;

  @override
  Widget build(BuildContext context) {
    final history = context.watch<ConversationHistoryProvider>();
    final projects = history.projects;

    if (projects.isNotEmpty &&
        (_selectedProjectId == null || projects.every((project) => project.id != _selectedProjectId))) {
      _selectedProjectId = projects.first.id;
    }

    return Container(
      decoration: BoxDecoration(
        color: ZoyaTheme.mainBg,
        gradient: ZoyaTheme.bgGradient,
      ),
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 280,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Projects',
                          style: ZoyaTheme.fontDisplay.copyWith(
                            fontSize: 28,
                            color: Colors.white,
                          ),
                        ),
                      ),
                      FilledButton(
                        onPressed: () => _showCreateProjectDialog(context),
                        child: const Text('Create'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 18),
                  Expanded(
                    child: projects.isEmpty
                        ? _EmptyState(
                            title: 'No projects yet',
                            description: 'Create a project to group conversations.',
                          )
                        : ListView.separated(
                            itemCount: projects.length,
                            separatorBuilder: (_, __) => const SizedBox(height: 10),
                            itemBuilder: (context, index) {
                              final project = projects[index];
                              final isSelected = project.id == _selectedProjectId;
                              final chats = history.conversationsForProject(project.id);
                              return InkWell(
                                onTap: () => setState(() => _selectedProjectId = project.id),
                                borderRadius: BorderRadius.circular(16),
                                child: Container(
                                  padding: const EdgeInsets.all(16),
                                  decoration: BoxDecoration(
                                    color: isSelected
                                        ? ZoyaTheme.accent.withValues(alpha: 0.14)
                                        : Colors.white.withValues(alpha: 0.03),
                                    borderRadius: BorderRadius.circular(16),
                                    border: Border.all(
                                      color: isSelected
                                          ? ZoyaTheme.accent.withValues(alpha: 0.5)
                                          : ZoyaTheme.glassBorder,
                                    ),
                                  ),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        project.name,
                                        style: ZoyaTheme.fontBody.copyWith(
                                          color: Colors.white,
                                          fontSize: 15,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                      if (project.description.trim().isNotEmpty) ...[
                                        const SizedBox(height: 6),
                                        Text(
                                          project.description,
                                          style: ZoyaTheme.fontBody.copyWith(
                                            color: Colors.white70,
                                            fontSize: 12,
                                          ),
                                        ),
                                      ],
                                      const SizedBox(height: 10),
                                      Text(
                                        '${chats.length} chats',
                                        style: ZoyaTheme.fontBody.copyWith(
                                          color: ZoyaTheme.textMuted,
                                          fontSize: 11,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 24),
            Expanded(
              child: _ProjectChatsPane(
                projectId: _selectedProjectId,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showCreateProjectDialog(BuildContext context) async {
    final history = context.read<ConversationHistoryProvider>();
    final nameController = TextEditingController();
    final descriptionController = TextEditingController();
    final created = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: ZoyaTheme.sidebarBg,
          title: const Text('Create project'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nameController,
                decoration: const InputDecoration(labelText: 'Project name'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: descriptionController,
                decoration: const InputDecoration(labelText: 'Description'),
                minLines: 2,
                maxLines: 3,
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Create'),
            ),
          ],
        );
      },
    );
    if (created == true && nameController.text.trim().isNotEmpty) {
      final project = await history.createProject(
        nameController.text,
        description: descriptionController.text,
      );
      if (mounted) {
        setState(() => _selectedProjectId = project.id);
      }
    }
  }
}

class _ProjectChatsPane extends StatelessWidget {
  final String? projectId;

  const _ProjectChatsPane({required this.projectId});

  @override
  Widget build(BuildContext context) {
    final history = context.watch<ConversationHistoryProvider>();
    if (projectId == null) {
      return const _EmptyState(
        title: 'Select a project',
        description: 'Pick a project to view its conversations.',
      );
    }
    final project = history.projects.where((item) => item.id == projectId).firstOrNull;
    final chats = history.conversationsForProject(projectId!);
    if (project == null) {
      return const _EmptyState(
        title: 'Project unavailable',
        description: 'This project no longer exists.',
      );
    }

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: ZoyaTheme.glassBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            project.name,
            style: ZoyaTheme.fontDisplay.copyWith(
              fontSize: 24,
              color: Colors.white,
            ),
          ),
          if (project.description.trim().isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              project.description,
              style: ZoyaTheme.fontBody.copyWith(
                color: Colors.white70,
                fontSize: 14,
              ),
            ),
          ],
          const SizedBox(height: 18),
          Expanded(
            child: chats.isEmpty
                ? const _EmptyState(
                    title: 'No chats assigned',
                    description: 'Move a conversation into this project from the chat sidebar.',
                  )
                : ListView.separated(
                    itemCount: chats.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (context, index) {
                      final chat = chats[index];
                      return InkWell(
                        onTap: () async {
                          final success = await context.read<ConversationHistoryProvider>().activateConversation(
                                chat.id,
                              );
                          if (success && context.mounted) {
                            context.read<WorkspaceController>().setCurrentPage('home');
                          }
                        },
                        borderRadius: BorderRadius.circular(16),
                        child: Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: chat.id == history.activeConversationId
                                ? ZoyaTheme.accent.withValues(alpha: 0.12)
                                : Colors.white.withValues(alpha: 0.02),
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(
                              color: chat.id == history.activeConversationId
                                  ? ZoyaTheme.accent.withValues(alpha: 0.4)
                                  : ZoyaTheme.glassBorder,
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                chat.title,
                                style: ZoyaTheme.fontBody.copyWith(
                                  color: Colors.white,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              if (chat.preview.trim().isNotEmpty) ...[
                                const SizedBox(height: 6),
                                Text(
                                  chat.preview,
                                  style: ZoyaTheme.fontBody.copyWith(
                                    color: Colors.white70,
                                    fontSize: 12,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final String title;
  final String description;

  const _EmptyState({
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            title,
            style: ZoyaTheme.fontBody.copyWith(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            description,
            style: ZoyaTheme.fontBody.copyWith(
              color: Colors.white60,
              fontSize: 13,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

extension on Iterable<ProjectRecord> {
  ProjectRecord? get firstOrNull {
    if (isEmpty) {
      return null;
    }
    return first;
  }
}
