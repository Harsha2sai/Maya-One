import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/services/ide_actions_service.dart';
import '../../core/services/ide_agentic_service.dart';
import '../../core/services/ide_files_service.dart';
import '../../core/services/ide_terminal_service.dart';
import '../../state/controllers/ide_workspace_controller.dart';
import '../../state/controllers/workspace_controller.dart';
import '../../state/providers/auth_provider.dart';
import '../../ui/theme/app_theme.dart';
import '../../widgets/features/ide/buddy_monitor.dart';

class IDEWorkspaceScreen extends StatefulWidget {
  const IDEWorkspaceScreen({super.key});

  @override
  State<IDEWorkspaceScreen> createState() => _IDEWorkspaceScreenState();
}

class _ToggleModeIntent extends Intent {
  const _ToggleModeIntent();
}

class _ToggleTerminalIntent extends Intent {
  const _ToggleTerminalIntent();
}

class _FocusExplorerIntent extends Intent {
  const _FocusExplorerIntent();
}

class _QuickOpenIntent extends Intent {
  const _QuickOpenIntent();
}

class _IDEWorkspaceScreenState extends State<IDEWorkspaceScreen> {
  final IdeFilesService _filesService = IdeFilesService();
  final IdeTerminalService _terminalService = IdeTerminalService();
  final IdeAgenticService _agenticService = IdeAgenticService();
  final IdeActionsService _actionsService = IdeActionsService();

  final TextEditingController _editorController = TextEditingController();
  final TextEditingController _terminalInputController = TextEditingController();
  final TextEditingController _spawnTaskController = TextEditingController();
  final ScrollController _terminalScrollController = ScrollController();

  StreamSubscription<String>? _terminalOutputSub;
  StreamSubscription<IdeTerminalStatus>? _terminalStatusSub;
  StreamSubscription<IdeAgenticEvent>? _agenticEventSub;
  StreamSubscription<IdeAgenticConnectionState>? _agenticStateSub;

  List<IdeFilesEntry> _entries = <IdeFilesEntry>[];
  String _currentDirectory = '';
  bool _loadingFiles = false;
  bool _savingFile = false;
  String? _errorMessage;
  String? _infoMessage;
  String _originalContent = '';
  DateTime? _lastSavedAt;
  String _terminalOutput = '';
  IdeTerminalStatus _terminalStatus = IdeTerminalStatus.idle;
  final List<IdeAgenticEvent> _agentEvents = <IdeAgenticEvent>[];
  final Set<int> _seenSeq = <int>{};
  final List<int> _recentEventMs = <int>[];
  IdeAgenticConnectionState _agenticState = IdeAgenticConnectionState.idle;
  List<IdePendingAction> _pendingActions = <IdePendingAction>[];
  List<IdeActionAuditEvent> _auditEvents = <IdeActionAuditEvent>[];
  String _spawnAgentType = 'coder';
  bool _spawnUseWorktree = false;
  bool _requestingSpawn = false;

  bool get _isDirty => _workspace.selectedFilePath != null && _editorController.text != _originalContent;

  IDEWorkspaceController get _workspace => context.read<IDEWorkspaceController>();

  String get _userId {
    try {
      return context.read<AuthProvider>().user?.id ?? 'guest-local';
    } catch (_) {
      return 'guest-local';
    }
  }

  String get _workspacePath {
    final configured = _workspace.workspacePath;
    if (configured.trim().isNotEmpty && configured.trim() != '.') {
      return configured;
    }
    try {
      return Directory.current.path;
    } catch (_) {
      return '.';
    }
  }

  @override
  void initState() {
    super.initState();
    _editorController.addListener(_onEditorChanged);
    _workspace.configureBuddy(_userId);

    _terminalOutputSub = _terminalService.outputStream.listen(_onTerminalOutput);
    _terminalStatusSub = _terminalService.statusStream.listen((status) {
      if (!mounted) return;
      setState(() => _terminalStatus = status);
    });
    _agenticEventSub = _agenticService.events.listen(_onAgenticEvent);
    _agenticStateSub = _agenticService.stateStream.listen((state) {
      if (!mounted) return;
      setState(() => _agenticState = state);
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_bootstrap());
    });
  }

  @override
  void dispose() {
    _editorController.removeListener(_onEditorChanged);
    _editorController.dispose();
    _terminalInputController.dispose();
    _spawnTaskController.dispose();
    _terminalScrollController.dispose();
    unawaited(_terminalOutputSub?.cancel());
    unawaited(_terminalStatusSub?.cancel());
    unawaited(_agenticEventSub?.cancel());
    unawaited(_agenticStateSub?.cancel());
    unawaited(_cleanupServices());
    super.dispose();
  }

  Future<void> _cleanupServices() async {
    final sessionId = _workspace.ideSessionId;
    if (sessionId != null && sessionId.isNotEmpty) {
      await _filesService.closeIdeSession(sessionId: sessionId);
    }
    await _terminalService.dispose();
    await _agenticService.dispose();
    await _actionsService.dispose();
    await _filesService.dispose();
  }

  Future<void> _bootstrap() async {
    setState(() {
      _loadingFiles = true;
      _errorMessage = null;
    });
    try {
      _workspace.setWorkspacePath(_workspacePath);
      final sessionId = await _filesService.openIdeSession(
        userId: _userId,
        workspacePath: _workspacePath,
      );
      _workspace.setIdeSessionId(sessionId);
      await _loadDirectory(path: '', resetEditor: true);
      await _terminalService.start(
        userId: _userId,
        workspacePath: _workspacePath,
      );
      await _agenticService.start(sessionId: sessionId);
      await _refreshApprovals();
    } catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = 'IDE workspace bootstrap failed: $e');
    } finally {
      if (mounted) {
        setState(() => _loadingFiles = false);
      }
    }
  }

  void _onEditorChanged() {
    if (!mounted) return;
    setState(() {});
  }

  void _onTerminalOutput(String chunk) {
    if (!mounted || chunk.isEmpty) return;
    setState(() {
      _terminalOutput += chunk;
      if (_terminalOutput.length > 200000) {
        _terminalOutput = _terminalOutput.substring(
          _terminalOutput.length - 200000,
        );
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_terminalScrollController.hasClients) return;
      _terminalScrollController.jumpTo(
        _terminalScrollController.position.maxScrollExtent,
      );
    });
  }

  void _onAgenticEvent(IdeAgenticEvent event) {
    if (!mounted) return;
    if (!_seenSeq.add(event.seq)) return;
    final now = DateTime.now().millisecondsSinceEpoch;
    _recentEventMs.add(now);
    _recentEventMs.removeWhere((ms) => now - ms > 1000);
    final isBurst = _recentEventMs.length > 60;
    _workspace.setCatchingUp(isBurst);
    _workspace.setSelectedTaskId(event.taskId);

    final eventType = event.eventType.toLowerCase();
    if (eventType.contains('error') || eventType.contains('failed') || (event.status ?? '').toLowerCase() == 'failed') {
      _workspace.setBuddyState(BuddyState.error);
    } else if (eventType.contains('started') || eventType.contains('executing') || eventType.contains('requested')) {
      _workspace.setBuddyState(BuddyState.working);
    } else if (eventType.contains('finished') || eventType.contains('completed') || eventType.contains('executed')) {
      _workspace.setBuddyState(BuddyState.complete);
      Future<void>.delayed(const Duration(milliseconds: 800), () {
        if (!mounted) return;
        _workspace.setBuddyState(BuddyState.idle);
      });
    }

    setState(() {
      _agentEvents.insert(0, event);
      if (_agentEvents.length > 300) {
        _agentEvents.removeRange(300, _agentEvents.length);
      }
    });
  }

  Future<void> _loadDirectory({
    required String path,
    required bool resetEditor,
  }) async {
    final sessionId = _workspace.ideSessionId;
    if (sessionId == null || sessionId.isEmpty) {
      setState(() => _errorMessage = 'IDE session unavailable');
      return;
    }
    setState(() {
      _loadingFiles = true;
      _errorMessage = null;
    });
    try {
      final snapshot = await _filesService.listDirectory(
        sessionId: sessionId,
        relativePath: path,
      );
      if (!mounted) return;
      _workspace.setIdeSessionId(snapshot.sessionId);
      setState(() {
        _currentDirectory = snapshot.path;
        _entries = snapshot.entries;
        if (resetEditor) {
          _workspace.setSelectedFilePath(null);
          _originalContent = '';
          _editorController.text = '';
        }
      });
    } on IdeFilesError catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'Directory load failed: $e');
    } finally {
      if (mounted) {
        setState(() => _loadingFiles = false);
      }
    }
  }

  Future<void> _openFile(String path) async {
    final sessionId = _workspace.ideSessionId;
    if (sessionId == null || sessionId.isEmpty) return;
    setState(() {
      _loadingFiles = true;
      _errorMessage = null;
    });
    try {
      final doc = await _filesService.readFile(
        sessionId: sessionId,
        relativePath: path,
      );
      if (!mounted) return;
      _workspace.setIdeSessionId(doc.sessionId);
      _workspace.setSelectedFilePath(doc.path);
      setState(() {
        _originalContent = doc.originalContent;
        _editorController.text = doc.draftContent;
        _lastSavedAt = doc.lastSavedAt;
      });
    } on IdeFilesError catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'File read failed: $e');
    } finally {
      if (mounted) {
        setState(() => _loadingFiles = false);
      }
    }
  }

  Future<void> _saveFile() async {
    final sessionId = _workspace.ideSessionId;
    final filePath = _workspace.selectedFilePath;
    if (sessionId == null || filePath == null) return;
    setState(() {
      _savingFile = true;
      _errorMessage = null;
    });
    try {
      final result = await _filesService.writeFile(
        sessionId: sessionId,
        relativePath: filePath,
        content: _editorController.text,
      );
      if (!mounted) return;
      _workspace.setIdeSessionId(result.sessionId);
      setState(() {
        _originalContent = _editorController.text;
        _lastSavedAt = result.lastSavedAt;
        _infoMessage = 'Saved ${result.path}';
      });
    } on IdeFilesError catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'File save failed: $e');
    } finally {
      if (mounted) {
        setState(() => _savingFile = false);
      }
    }
  }

  Future<bool> _confirmUnsavedChanges() async {
    if (!_isDirty) return true;
    final decision = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Unsaved changes'),
        content: const Text('Save changes before navigating?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop('cancel'),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop('discard'),
            child: const Text('Discard'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop('save'),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (decision == 'discard') return true;
    if (decision == 'save') {
      await _saveFile();
      return !_isDirty;
    }
    return false;
  }

  Future<void> _handleEntryTap(IdeFilesEntry entry) async {
    final proceed = await _confirmUnsavedChanges();
    if (!proceed) return;
    if (entry.isDir) {
      await _loadDirectory(path: entry.path, resetEditor: true);
    } else {
      await _openFile(entry.path);
    }
  }

  Future<void> _submitTerminalInput() async {
    final text = _terminalInputController.text.trim();
    if (text.isEmpty) return;
    _terminalInputController.clear();
    await _terminalService.sendInput('$text\n');
  }

  Future<void> _refreshApprovals() async {
    try {
      final pending = await _actionsService.listPending(userId: _userId);
      final audit = await _actionsService.listAudit(
        userId: _userId,
        sessionId: _workspace.ideSessionId,
        limit: 100,
      );
      if (!mounted) return;
      setState(() {
        _pendingActions = pending;
        _auditEvents = audit;
      });
    } catch (_) {
      // Keep UI usable if approval center backend is temporarily unavailable.
    }
  }

  Future<void> _requestSpawn() async {
    final task = _spawnTaskController.text.trim();
    if (task.isEmpty) {
      setState(() => _errorMessage = 'Spawn task is required.');
      return;
    }
    final sessionId = _workspace.ideSessionId ?? 'ide-workspace';
    setState(() {
      _requestingSpawn = true;
      _errorMessage = null;
      _infoMessage = null;
    });
    try {
      final result = await _actionsService.requestAction(
        userId: _userId,
        sessionId: sessionId,
        taskId: _workspace.selectedTaskId,
        action: IdeActionEnvelope(
          target: 'agent',
          operation: 'spawn',
          arguments: <String, dynamic>{
            'agent_type': _spawnAgentType,
            'task': task,
            'use_worktree': _spawnUseWorktree,
            if ((_workspace.selectedTaskId ?? '').isNotEmpty) 'task_id': _workspace.selectedTaskId,
          },
          reason: 'spawn requested from IDE workspace',
        ),
      );
      await _refreshApprovals();
      if (!mounted) return;
      setState(() {
        _infoMessage = result.status == 'pending' ? 'Spawn request queued for approval.' : 'Spawn executed.';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = 'Spawn request failed: $e');
    } finally {
      if (mounted) {
        setState(() => _requestingSpawn = false);
      }
    }
  }

  Future<void> _quickOpen() async {
    final files = _entries.where((e) => !e.isDir).toList(growable: false);
    if (files.isEmpty) return;
    final selected = await showDialog<IdeFilesEntry>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('Quick Open'),
        children: files
            .take(30)
            .map(
              (entry) => SimpleDialogOption(
                onPressed: () => Navigator.of(context).pop(entry),
                child: Text(entry.path),
              ),
            )
            .toList(growable: false),
      ),
    );
    if (selected != null) {
      await _openFile(selected.path);
    }
  }

  Map<ShortcutActivator, Intent> _shortcutMap() {
    return <ShortcutActivator, Intent>{
      const SingleActivator(
        LogicalKeyboardKey.keyE,
        control: true,
      ): const _ToggleModeIntent(),
      const SingleActivator(
        LogicalKeyboardKey.keyE,
        meta: true,
      ): const _ToggleModeIntent(),
      const SingleActivator(
        LogicalKeyboardKey.keyJ,
        control: true,
      ): const _ToggleTerminalIntent(),
      const SingleActivator(
        LogicalKeyboardKey.keyJ,
        meta: true,
      ): const _ToggleTerminalIntent(),
      const SingleActivator(
        LogicalKeyboardKey.keyE,
        control: true,
        shift: true,
      ): const _FocusExplorerIntent(),
      const SingleActivator(
        LogicalKeyboardKey.keyE,
        meta: true,
        shift: true,
      ): const _FocusExplorerIntent(),
      const SingleActivator(
        LogicalKeyboardKey.keyP,
        control: true,
      ): const _QuickOpenIntent(),
      const SingleActivator(
        LogicalKeyboardKey.keyP,
        meta: true,
      ): const _QuickOpenIntent(),
    };
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<IDEWorkspaceController>(
      builder: (context, workspace, _) {
        return Shortcuts(
          shortcuts: _shortcutMap(),
          child: Actions(
            actions: <Type, Action<Intent>>{
              _ToggleModeIntent: CallbackAction<_ToggleModeIntent>(
                onInvoke: (intent) {
                  final nextMode = workspace.mode == IdeWorkspaceMode.editor
                      ? IdeWorkspaceMode.missionControl
                      : IdeWorkspaceMode.editor;
                  workspace.setMode(nextMode);
                  return null;
                },
              ),
              _ToggleTerminalIntent: CallbackAction<_ToggleTerminalIntent>(
                onInvoke: (intent) {
                  workspace.setTerminalVisible(!workspace.terminalVisible);
                  return null;
                },
              ),
              _FocusExplorerIntent: CallbackAction<_FocusExplorerIntent>(
                onInvoke: (intent) {
                  workspace
                    ..setLeftPanelVisible(true)
                    ..setActiveSection(IdeActivitySection.explorer);
                  return null;
                },
              ),
              _QuickOpenIntent: CallbackAction<_QuickOpenIntent>(
                onInvoke: (intent) {
                  unawaited(_quickOpen());
                  return null;
                },
              ),
            },
            child: Focus(
              autofocus: true,
              child: Scaffold(
                backgroundColor: const Color(0xFF070C14),
                body: SafeArea(
                  child: Column(
                    children: [
                      _buildHeader(workspace),
                      if (_errorMessage != null) _buildBanner(_errorMessage!, ZoyaTheme.danger),
                      if (_infoMessage != null) _buildBanner(_infoMessage!, Colors.green),
                      Expanded(
                        child: workspace.mode == IdeWorkspaceMode.missionControl
                            ? _buildMissionControlPlaceholder()
                            : _buildEditorSurface(workspace),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildHeader(IDEWorkspaceController workspace) {
    final statusLabel = workspace.catchingUp ? 'Catching up' : 'Live';
    return Container(
      key: const Key('ide-workspace-header'),
      height: 56,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF0A1220),
        border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
      ),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Back to Maya',
            onPressed: () => context.read<WorkspaceController>().setCurrentPage('home'),
            icon: const Icon(Icons.arrow_back, color: ZoyaTheme.textMain),
          ),
          const SizedBox(width: 8),
          Text(
            'MAYA-ONE IDE',
            style: ZoyaTheme.fontDisplay.copyWith(
              color: ZoyaTheme.accent,
              fontSize: 16,
            ),
          ),
          const SizedBox(width: 14),
          Flexible(
            child: Text(
              workspace.workspacePath,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: ZoyaTheme.textMuted, fontSize: 12),
            ),
          ),
          const SizedBox(width: 12),
          _StatusChip(label: statusLabel),
          const SizedBox(width: 8),
          OutlinedButton(
            onPressed: () {
              final nextMode =
                  workspace.mode == IdeWorkspaceMode.editor ? IdeWorkspaceMode.missionControl : IdeWorkspaceMode.editor;
              workspace.setMode(nextMode);
            },
            child: Text(
              workspace.mode == IdeWorkspaceMode.editor ? 'Open Mission Control' : 'Back to Editor',
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBanner(String text, Color color) {
    return Container(
      width: double.infinity,
      color: color.withValues(alpha: 0.16),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Text(
        text,
        style: TextStyle(color: color, fontSize: 12),
      ),
    );
  }

  Widget _buildMissionControlPlaceholder() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.hub, color: ZoyaTheme.accent, size: 44),
          const SizedBox(height: 12),
          Text(
            'Mission Control ships in P14.2',
            style: ZoyaTheme.fontBody.copyWith(
              color: ZoyaTheme.textMain,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Inbox / Workspaces / Playground will land with router migration.',
            style: TextStyle(color: ZoyaTheme.textMuted),
          ),
        ],
      ),
    );
  }

  Widget _buildEditorSurface(IDEWorkspaceController workspace) {
    return Column(
      children: [
        Expanded(
          child: Row(
            children: [
              _buildActivityRail(workspace),
              if (workspace.leftPanelVisible) _buildExplorerPane(workspace),
              _buildCenterEditorPane(),
              if (workspace.rightPanelVisible) _buildRightAgentPanel(workspace),
            ],
          ),
        ),
        if (workspace.terminalVisible) _buildTerminalPane(workspace),
      ],
    );
  }

  Widget _buildActivityRail(IDEWorkspaceController workspace) {
    Widget button({
      required IconData icon,
      required IdeActivitySection section,
      required String tooltip,
    }) {
      final active = workspace.activeSection == section;
      return IconButton(
        tooltip: tooltip,
        onPressed: () => workspace.setActiveSection(section),
        icon: Icon(
          icon,
          color: active ? ZoyaTheme.accent : ZoyaTheme.textMuted,
        ),
      );
    }

    return Container(
      width: 56,
      decoration: BoxDecoration(
        color: const Color(0xFF0B1322),
        border: Border(right: BorderSide(color: ZoyaTheme.glassBorder)),
      ),
      child: Column(
        children: [
          const SizedBox(height: 8),
          button(
            icon: Icons.folder_outlined,
            section: IdeActivitySection.explorer,
            tooltip: 'Explorer',
          ),
          button(
            icon: Icons.search,
            section: IdeActivitySection.search,
            tooltip: 'Search',
          ),
          button(
            icon: Icons.account_tree_outlined,
            section: IdeActivitySection.scm,
            tooltip: 'SCM',
          ),
          button(
            icon: Icons.terminal_outlined,
            section: IdeActivitySection.terminal,
            tooltip: 'Terminal',
          ),
          button(
            icon: Icons.smart_toy_outlined,
            section: IdeActivitySection.agentic,
            tooltip: 'Agentic',
          ),
          const Spacer(),
          IconButton(
            tooltip: 'Toggle left panel',
            onPressed: () => workspace.setLeftPanelVisible(!workspace.leftPanelVisible),
            icon: const Icon(Icons.chevron_left, color: ZoyaTheme.textMuted),
          ),
        ],
      ),
    );
  }

  Widget _buildExplorerPane(IDEWorkspaceController workspace) {
    return SizedBox(
      width: workspace.leftPanelWidth,
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF0D1626),
          border: Border(right: BorderSide(color: ZoyaTheme.glassBorder)),
        ),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
              ),
              child: Row(
                children: [
                  const Expanded(
                    child: Text(
                      'Explorer',
                      style: TextStyle(
                        color: ZoyaTheme.textMain,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: _loadingFiles
                        ? null
                        : () => _loadDirectory(
                              path: _currentDirectory,
                              resetEditor: false,
                            ),
                    icon: const Icon(Icons.refresh, size: 18),
                    color: ZoyaTheme.textMuted,
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  _currentDirectory.isEmpty ? 'root' : _currentDirectory,
                  style: TextStyle(
                    color: ZoyaTheme.textMuted.withValues(alpha: 0.9),
                    fontSize: 11,
                  ),
                ),
              ),
            ),
            Expanded(
              child: _loadingFiles && _entries.isEmpty
                  ? const Center(
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : ListView.builder(
                      itemCount: _entries.length,
                      itemBuilder: (context, index) {
                        final entry = _entries[index];
                        final selected = _workspace.selectedFilePath == entry.path;
                        return ListTile(
                          dense: true,
                          selected: selected,
                          onTap: () => _handleEntryTap(entry),
                          leading: Icon(
                            entry.isDir ? Icons.folder : Icons.insert_drive_file_outlined,
                            size: 16,
                            color: entry.isDir ? Colors.amberAccent : ZoyaTheme.textMuted,
                          ),
                          title: Text(
                            entry.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: selected ? ZoyaTheme.accent : ZoyaTheme.textMain,
                              fontSize: 12,
                            ),
                          ),
                        );
                      },
                    ),
            ),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onHorizontalDragUpdate: (details) {
                workspace.setLeftPanelWidth(
                  workspace.leftPanelWidth + details.delta.dx,
                );
              },
              child: const SizedBox(
                width: double.infinity,
                height: 6,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCenterEditorPane() {
    return Expanded(
      child: Column(
        children: [
          Container(
            height: 34,
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              color: const Color(0xFF0D1422),
              border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _workspace.selectedFilePath ?? 'No file selected',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: ZoyaTheme.textMain,
                      fontSize: 12,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  _isDirty ? 'Unsaved' : (_lastSavedAt == null ? 'Ready' : 'Saved'),
                  style: TextStyle(
                    color: _isDirty ? Colors.orangeAccent : Colors.greenAccent,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Container(
              color: const Color(0xFF0B1220),
              padding: const EdgeInsets.all(12),
              child: TextField(
                key: const Key('ide-workspace-editor'),
                controller: _editorController,
                expands: true,
                maxLines: null,
                minLines: null,
                style: const TextStyle(
                  color: Color(0xFFBFDBFE),
                  fontFamily: 'monospace',
                  fontSize: 12,
                ),
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  hintText: 'Select a file to edit...',
                ),
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: ZoyaTheme.glassBorder)),
              color: const Color(0xFF0D1422),
            ),
            child: Row(
              children: [
                OutlinedButton(
                  onPressed: _savingFile
                      ? null
                      : () {
                          _editorController.text = _originalContent;
                          setState(() => _errorMessage = null);
                        },
                  child: const Text('Discard'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: (_savingFile || !_isDirty) ? null : _saveFile,
                  style: FilledButton.styleFrom(
                    backgroundColor: ZoyaTheme.accent,
                    foregroundColor: Colors.black,
                  ),
                  child: Text(_savingFile ? 'Saving…' : 'Save'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRightAgentPanel(IDEWorkspaceController workspace) {
    return SizedBox(
      width: workspace.rightPanelWidth,
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF0D1626),
          border: Border(left: BorderSide(color: ZoyaTheme.glassBorder)),
        ),
        child: Column(
          children: [
            Container(
              height: 40,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
              ),
              child: Row(
                children: [
                  const Expanded(
                    child: Text(
                      'Agent Panel',
                      style: TextStyle(
                        color: ZoyaTheme.textMain,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: _refreshApprovals,
                    icon: const Icon(Icons.refresh, size: 18),
                    color: ZoyaTheme.textMuted,
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(10),
              child: BuddyMonitor(
                species: workspace.buddyConfig.species,
                state: workspace.buddyState,
                isShiny: workspace.buddyConfig.isShiny,
                catchingUp: workspace.catchingUp,
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              child: _buildSpawnControls(),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 8, 10, 4),
              child: Row(
                children: [
                  _SmallBadge(
                    label: '${_pendingActions.length} pending',
                    color: Colors.orangeAccent,
                  ),
                  const SizedBox(width: 8),
                  _SmallBadge(
                    label: '${_auditEvents.length} audit',
                    color: Colors.greenAccent,
                  ),
                  const SizedBox(width: 8),
                  _SmallBadge(
                    label: _agenticState.name,
                    color:
                        _agenticState == IdeAgenticConnectionState.connected ? Colors.greenAccent : ZoyaTheme.textMuted,
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                key: const Key('ide-workspace-agent-events'),
                itemCount: _agentEvents.length,
                itemBuilder: (context, index) {
                  final event = _agentEvents[index];
                  return ListTile(
                    dense: true,
                    title: Text(
                      event.eventType,
                      style: const TextStyle(
                        color: ZoyaTheme.textMain,
                        fontSize: 12,
                      ),
                    ),
                    subtitle: Text(
                      'task=${event.taskId ?? '-'} · seq=${event.seq}',
                      style: TextStyle(
                        color: ZoyaTheme.textMuted.withValues(alpha: 0.85),
                        fontSize: 11,
                      ),
                    ),
                  );
                },
              ),
            ),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onHorizontalDragUpdate: (details) {
                workspace.setRightPanelWidth(
                  workspace.rightPanelWidth - details.delta.dx,
                );
              },
              child: const SizedBox(height: 6, width: double.infinity),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSpawnControls() {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF111A2B),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: ZoyaTheme.glassBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Spawn Agent',
            style: ZoyaTheme.fontBody.copyWith(
              color: ZoyaTheme.textMain,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            value: _spawnAgentType,
            isExpanded: true,
            decoration: const InputDecoration(
              isDense: true,
              contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            ),
            items: const [
              DropdownMenuItem(value: 'coder', child: Text('coder')),
              DropdownMenuItem(value: 'reviewer', child: Text('reviewer')),
              DropdownMenuItem(value: 'researcher', child: Text('researcher')),
              DropdownMenuItem(value: 'architect', child: Text('architect')),
              DropdownMenuItem(value: 'tester', child: Text('tester')),
            ],
            onChanged: (value) {
              if (value == null) return;
              setState(() => _spawnAgentType = value);
            },
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _spawnTaskController,
            minLines: 2,
            maxLines: 3,
            style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 12),
            decoration: InputDecoration(
              hintText: 'Task prompt for spawned agent...',
              hintStyle: TextStyle(
                color: ZoyaTheme.textMuted.withValues(alpha: 0.8),
              ),
              isDense: true,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Switch(
                value: _spawnUseWorktree,
                onChanged: (value) => setState(() => _spawnUseWorktree = value),
              ),
              const SizedBox(width: 6),
              Text(
                'Use worktree',
                style: TextStyle(
                  color: ZoyaTheme.textMuted.withValues(alpha: 0.9),
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              key: const Key('ide-workspace-spawn-request'),
              onPressed: _requestingSpawn ? null : _requestSpawn,
              child: Text(_requestingSpawn ? 'Requesting…' : 'Request Spawn'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTerminalPane(IDEWorkspaceController workspace) {
    Color statusColor;
    switch (_terminalStatus) {
      case IdeTerminalStatus.connected:
        statusColor = Colors.greenAccent;
        break;
      case IdeTerminalStatus.error:
        statusColor = ZoyaTheme.danger;
        break;
      case IdeTerminalStatus.connecting:
      case IdeTerminalStatus.reconnecting:
      case IdeTerminalStatus.opening:
        statusColor = Colors.orangeAccent;
        break;
      default:
        statusColor = ZoyaTheme.textMuted;
    }

    return SizedBox(
      height: workspace.terminalHeight,
      child: Column(
        children: [
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onVerticalDragUpdate: (details) {
              workspace.setTerminalHeight(
                workspace.terminalHeight - details.delta.dy,
              );
            },
            child: Container(
              height: 8,
              color: Colors.transparent,
              alignment: Alignment.center,
              child: Container(
                width: 84,
                height: 2,
                color: ZoyaTheme.glassBorder,
              ),
            ),
          ),
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF0A1220),
                border: Border(top: BorderSide(color: ZoyaTheme.glassBorder)),
              ),
              child: Column(
                children: [
                  Container(
                    height: 32,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    child: Row(
                      children: [
                        Icon(Icons.circle, size: 10, color: statusColor),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _terminalStatus.name,
                            style: const TextStyle(
                              color: ZoyaTheme.textMuted,
                              fontSize: 12,
                            ),
                          ),
                        ),
                        IconButton(
                          onPressed: () => _terminalService.sendInput('\u0003'),
                          icon: const Icon(Icons.cancel, size: 16),
                          color: ZoyaTheme.textMuted,
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: Container(
                      width: double.infinity,
                      color: const Color(0xFF0B1220),
                      padding: const EdgeInsets.all(10),
                      child: SingleChildScrollView(
                        controller: _terminalScrollController,
                        child: SelectableText(
                          _terminalOutput.isEmpty ? 'Terminal ready.\n' : _terminalOutput,
                          style: const TextStyle(
                            color: Color(0xFFBFDBFE),
                            fontFamily: 'monospace',
                            fontSize: 12,
                            height: 1.32,
                          ),
                        ),
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    child: Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _terminalInputController,
                            onSubmitted: (_) => _submitTerminalInput(),
                            style: const TextStyle(
                              color: ZoyaTheme.textMain,
                              fontFamily: 'monospace',
                              fontSize: 12,
                            ),
                            decoration: const InputDecoration(
                              hintText: 'Run command...',
                              isDense: true,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        FilledButton(
                          onPressed: _submitTerminalInput,
                          child: const Text('Send'),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final live = label == 'Live';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: (live ? Colors.green : Colors.orange).withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: (live ? Colors.green : Colors.orange).withValues(alpha: 0.35),
        ),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: live ? Colors.greenAccent : Colors.orangeAccent,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _SmallBadge extends StatelessWidget {
  const _SmallBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        color: color.withValues(alpha: 0.12),
        border: Border.all(color: color.withValues(alpha: 0.34)),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w700),
      ),
    );
  }
}
