import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/services/ide_agentic_service.dart';
import '../../../core/services/ide_agentic_analysis.dart';
import '../../../core/services/ide_files_service.dart';
import '../../../core/services/ide_terminal_service.dart';
import '../../../state/providers/auth_provider.dart';
import '../../../ui/theme/app_theme.dart';

class IDETab extends StatefulWidget {
  const IDETab({
    super.key,
    this.filesService,
    this.terminalService,
    this.agenticService,
  });

  final IdeFilesService? filesService;
  final IdeTerminalService? terminalService;
  final IdeAgenticService? agenticService;

  @override
  State<IDETab> createState() => _IDETabState();
}

class _IDETabState extends State<IDETab> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(color: ZoyaTheme.glassBorder),
            ),
          ),
          child: TabBar(
            controller: _tabController,
            indicatorColor: ZoyaTheme.accent,
            labelColor: ZoyaTheme.textMain,
            unselectedLabelColor: ZoyaTheme.textMuted,
            isScrollable: true,
            tabs: const [
              Tab(
                key: Key('ide-subtab-files'),
                text: 'Files',
                icon: Icon(Icons.folder_outlined, size: 18),
              ),
              Tab(
                key: Key('ide-subtab-terminal'),
                text: 'Terminal',
                icon: Icon(Icons.terminal_outlined, size: 18),
              ),
              Tab(
                key: Key('ide-subtab-agentic'),
                text: 'Agentic',
                icon: Icon(Icons.smart_toy_outlined, size: 18),
              ),
            ],
          ),
        ),
        Expanded(
          child: TabBarView(
            controller: _tabController,
            children: [
              _FilesPane(service: widget.filesService),
              _TerminalPane(service: widget.terminalService),
              _AgenticPane(service: widget.agenticService),
            ],
          ),
        ),
      ],
    );
  }
}

class _FilesPane extends StatefulWidget {
  const _FilesPane({this.service});

  final IdeFilesService? service;

  @override
  State<_FilesPane> createState() => _FilesPaneState();
}

class _FilesPaneState extends State<_FilesPane> {
  late final IdeFilesService _service;
  final TextEditingController _editorController = TextEditingController();

  String? _sessionId;
  String _currentPath = '';
  List<IdeFilesEntry> _entries = <IdeFilesEntry>[];
  String? _selectedFilePath;
  String _fileContentOriginal = '';
  bool _isLoading = false;
  bool _isSaving = false;
  DateTime? _lastSavedAt;
  String? _errorBanner;

  bool get _isDirty => _selectedFilePath != null && _editorController.text != _fileContentOriginal;

  @override
  void initState() {
    super.initState();
    _service = widget.service ?? IdeFilesService();
    _editorController.addListener(_onEditorChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_initialize());
    });
  }

  @override
  void dispose() {
    _editorController.removeListener(_onEditorChanged);
    _editorController.dispose();
    final sessionId = _sessionId;
    if (sessionId != null && sessionId.isNotEmpty) {
      unawaited(_service.closeIdeSession(sessionId: sessionId));
    }
    unawaited(_service.dispose());
    super.dispose();
  }

  void _onEditorChanged() {
    if (!mounted) return;
    setState(() {
      // Keep UI in sync with dirty state.
    });
  }

  Future<void> _initialize() async {
    setState(() {
      _isLoading = true;
      _errorBanner = null;
    });

    try {
      final userId = _resolveUserId();
      final workspacePath = _resolveWorkspacePath();
      final sessionId = await _service.openIdeSession(
        userId: userId,
        workspacePath: workspacePath,
      );

      if (!mounted) return;
      _sessionId = sessionId;
      await _loadDirectory(path: '', resetEditor: false);
    } on IdeFilesError catch (e) {
      _setErrorFromIdeError(e);
    } catch (e) {
      _setError('Failed to initialize files pane: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  String _resolveUserId() {
    try {
      final auth = context.read<AuthProvider>();
      return auth.user?.id ?? 'guest-local';
    } catch (_) {
      return 'guest-local';
    }
  }

  String _resolveWorkspacePath() {
    try {
      return Directory.current.path;
    } catch (_) {
      return '.';
    }
  }

  Future<void> _loadDirectory({
    required String path,
    required bool resetEditor,
  }) async {
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      _setError('IDE session unavailable');
      return;
    }

    setState(() {
      _isLoading = true;
      _errorBanner = null;
    });

    try {
      final snapshot = await _service.listDirectory(
        sessionId: sessionId,
        relativePath: path,
      );
      if (!mounted) return;

      setState(() {
        _sessionId = snapshot.sessionId;
        _currentPath = snapshot.path;
        _entries = snapshot.entries;
        if (resetEditor) {
          _selectedFilePath = null;
          _fileContentOriginal = '';
          _editorController.text = '';
          _lastSavedAt = null;
        }
      });
    } on IdeFilesError catch (e) {
      _setErrorFromIdeError(e);
    } catch (e) {
      _setError('Directory load failed: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _openFile(String relativePath) async {
    final sessionId = _sessionId;
    if (sessionId == null || sessionId.isEmpty) {
      _setError('IDE session unavailable');
      return;
    }

    setState(() {
      _isLoading = true;
      _errorBanner = null;
    });

    try {
      final document = await _service.readFile(
        sessionId: sessionId,
        relativePath: relativePath,
      );
      if (!mounted) return;

      setState(() {
        _sessionId = document.sessionId;
        _selectedFilePath = document.path;
        _fileContentOriginal = document.originalContent;
        _editorController.text = document.draftContent;
        _lastSavedAt = document.lastSavedAt;
      });
    } on IdeFilesError catch (e) {
      _setErrorFromIdeError(e);
    } catch (e) {
      _setError('File open failed: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _saveCurrentFile() async {
    final sessionId = _sessionId;
    final selectedFile = _selectedFilePath;
    if (sessionId == null || selectedFile == null || selectedFile.isEmpty) {
      return;
    }

    setState(() {
      _isSaving = true;
      _errorBanner = null;
    });

    try {
      final result = await _service.writeFile(
        sessionId: sessionId,
        relativePath: selectedFile,
        content: _editorController.text,
      );
      if (!mounted) return;

      setState(() {
        _sessionId = result.sessionId;
        _fileContentOriginal = _editorController.text;
        _lastSavedAt = result.lastSavedAt;
      });
    } on IdeFilesError catch (e) {
      _setErrorFromIdeError(e);
    } catch (e) {
      _setError('Save failed: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isSaving = false;
        });
      }
    }
  }

  Future<bool> _confirmUnsavedChanges() async {
    if (!_isDirty) return true;

    final decision = await showDialog<String>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Unsaved changes'),
          content: const Text('You have unsaved changes. Save before navigating?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop('cancel'),
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop('discard'),
              child: const Text('Discard'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop('save'),
              child: const Text('Save'),
            ),
          ],
        );
      },
    );

    if (decision == 'discard') {
      return true;
    }
    if (decision == 'save') {
      await _saveCurrentFile();
      return !_isDirty;
    }
    return false;
  }

  Future<void> _handleEntryTap(IdeFilesEntry entry) async {
    final proceed = await _confirmUnsavedChanges();
    if (!proceed) return;

    if (entry.isDir) {
      await _loadDirectory(path: entry.path, resetEditor: true);
      return;
    }
    await _openFile(entry.path);
  }

  Future<void> _handleBreadcrumbTap(String path) async {
    final proceed = await _confirmUnsavedChanges();
    if (!proceed) return;
    await _loadDirectory(path: path, resetEditor: true);
  }

  void _setError(String message) {
    if (!mounted) return;
    setState(() {
      _errorBanner = message;
    });
  }

  void _setErrorFromIdeError(IdeFilesError error) {
    if (!mounted) return;

    String message;
    switch (error.statusCode) {
      case 400:
        message = error.message;
        break;
      case 403:
        message = 'Blocked by policy'
            '${error.risk == null ? '' : ' (${error.risk})'}'
            ': ${error.policyReason ?? error.message}';
        break;
      case 409:
        message = 'Approval required: ${error.policyReason ?? error.message}';
        break;
      case 500:
        message = 'Backend error: ${error.message}. Try refresh.';
        break;
      default:
        message = error.message;
    }

    setState(() {
      _errorBanner = message;
    });
  }

  List<_BreadcrumbSegment> _buildBreadcrumbSegments() {
    final segments = <_BreadcrumbSegment>[
      const _BreadcrumbSegment(label: 'root', path: ''),
    ];
    if (_currentPath.isEmpty) {
      return segments;
    }

    final parts = _currentPath.split('/').where((part) => part.trim().isNotEmpty).toList();
    for (var i = 0; i < parts.length; i++) {
      final path = parts.sublist(0, i + 1).join('/');
      segments.add(_BreadcrumbSegment(label: parts[i], path: path));
    }
    return segments;
  }

  String _statusText() {
    if (_isSaving) return 'Saving…';
    if (_isLoading) return 'Loading…';
    if (_selectedFilePath == null) return 'No file selected';
    if (_isDirty) return 'Unsaved';
    if (_lastSavedAt != null) return 'Saved';
    return 'Ready';
  }

  @override
  Widget build(BuildContext context) {
    final segments = _buildBreadcrumbSegments();
    return Column(
      key: const Key('ide-pane-files'),
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
          ),
          child: Row(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  key: const Key('ide-files-breadcrumb'),
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      for (var i = 0; i < segments.length; i++) ...[
                        TextButton(
                          key: Key('ide-files-breadcrumb-${segments[i].path.isEmpty ? 'root' : segments[i].path}'),
                          onPressed: _isLoading ? null : () => _handleBreadcrumbTap(segments[i].path),
                          child: Text(segments[i].label),
                        ),
                        if (i < segments.length - 1)
                          Text(
                            '/',
                            style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.7)),
                          ),
                      ],
                    ],
                  ),
                ),
              ),
              IconButton(
                key: const Key('ide-files-refresh'),
                tooltip: 'Refresh',
                onPressed: _isLoading ? null : () => _loadDirectory(path: _currentPath, resetEditor: false),
                icon: const Icon(Icons.refresh, size: 18, color: ZoyaTheme.textMuted),
              ),
            ],
          ),
        ),
        if (_errorBanner != null)
          Container(
            key: const Key('ide-files-error-banner'),
            width: double.infinity,
            color: ZoyaTheme.danger.withValues(alpha: 0.12),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Text(
              _errorBanner!,
              style: const TextStyle(
                color: ZoyaTheme.danger,
                fontSize: 12,
              ),
            ),
          ),
        Expanded(
          child: Row(
            children: [
              Container(
                width: 280,
                decoration: BoxDecoration(
                  border: Border(right: BorderSide(color: ZoyaTheme.glassBorder)),
                ),
                child: _buildEntryList(),
              ),
              Expanded(child: _buildEditorPane()),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildEntryList() {
    if (_isLoading && _entries.isEmpty) {
      return const Center(
        child: CircularProgressIndicator(strokeWidth: 2),
      );
    }

    if (_entries.isEmpty) {
      return Center(
        child: Text(
          'No files found',
          style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.8)),
        ),
      );
    }

    return ListView.builder(
      key: const Key('ide-files-list'),
      itemCount: _entries.length,
      itemBuilder: (context, index) {
        final entry = _entries[index];
        final isSelected = _selectedFilePath == entry.path;

        return ListTile(
          key: Key('ide-entry-${entry.path}'),
          dense: true,
          selected: isSelected,
          leading: Icon(
            entry.isDir ? Icons.folder : Icons.description_outlined,
            size: 18,
            color: entry.isDir ? Colors.amberAccent : ZoyaTheme.textMuted,
          ),
          title: Text(
            entry.name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: isSelected ? ZoyaTheme.accent : ZoyaTheme.textMain,
              fontSize: 13,
            ),
          ),
          subtitle: entry.isDir
              ? null
              : Text(
                  '${entry.size} B',
                  style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.6), fontSize: 11),
                ),
          onTap: () => _handleEntryTap(entry),
        );
      },
    );
  }

  Widget _buildEditorPane() {
    if (_selectedFilePath == null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.edit_note, size: 46, color: ZoyaTheme.textMuted.withValues(alpha: 0.45)),
            const SizedBox(height: 10),
            Text(
              'Select a file to start editing',
              style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.8)),
            ),
          ],
        ),
      );
    }

    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  _selectedFilePath!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 12),
                ),
              ),
              Container(
                key: const Key('ide-files-status'),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: _isDirty ? Colors.orange.withValues(alpha: 0.2) : Colors.green.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  _statusText(),
                  style: TextStyle(
                    color: _isDirty ? Colors.orangeAccent : Colors.greenAccent,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
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
              key: const Key('ide-files-editor'),
              controller: _editorController,
              expands: true,
              maxLines: null,
              minLines: null,
              style: const TextStyle(
                color: Color(0xFFBFDBFE),
                fontFamily: 'monospace',
                fontSize: 12,
                height: 1.35,
              ),
              decoration: const InputDecoration(
                border: InputBorder.none,
                hintText: 'File content',
              ),
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
          decoration: BoxDecoration(
            color: ZoyaTheme.glassBg,
            border: Border(top: BorderSide(color: ZoyaTheme.glassBorder)),
          ),
          child: Row(
            children: [
              OutlinedButton(
                key: const Key('ide-files-discard'),
                onPressed: _isSaving
                    ? null
                    : () {
                        _editorController.text = _fileContentOriginal;
                        setState(() {
                          _errorBanner = null;
                        });
                      },
                child: const Text('Discard'),
              ),
              const SizedBox(width: 10),
              FilledButton(
                key: const Key('ide-files-save'),
                onPressed: (_isSaving || !_isDirty) ? null : _saveCurrentFile,
                style: FilledButton.styleFrom(
                  backgroundColor: ZoyaTheme.accent,
                  foregroundColor: Colors.black,
                ),
                child: Text(_isSaving ? 'Saving…' : 'Save'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _BreadcrumbSegment {
  const _BreadcrumbSegment({required this.label, required this.path});

  final String label;
  final String path;
}

class _TerminalPane extends StatefulWidget {
  const _TerminalPane({this.service});

  final IdeTerminalService? service;

  @override
  State<_TerminalPane> createState() => _TerminalPaneState();
}

class _TerminalPaneState extends State<_TerminalPane> {
  static const int _maxOutputChars = 200000;

  late final IdeTerminalService _service;
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  StreamSubscription<String>? _outputSub;
  StreamSubscription<IdeTerminalStatus>? _statusSub;

  IdeTerminalStatus _status = IdeTerminalStatus.idle;
  String _output = '';
  String _statusMessage = 'Idle';
  int _droppedChars = 0;
  bool _initializing = true;

  @override
  void initState() {
    super.initState();
    _service = widget.service ?? IdeTerminalService(maxOutputChars: _maxOutputChars);
    _outputSub = _service.outputStream.listen(_onTerminalOutput);
    _statusSub = _service.statusStream.listen(_onStatusChanged);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_connect());
    });
  }

  @override
  void dispose() {
    if (_outputSub != null) {
      unawaited(_outputSub!.cancel());
    }
    if (_statusSub != null) {
      unawaited(_statusSub!.cancel());
    }
    _inputController.dispose();
    _scrollController.dispose();
    unawaited(_service.dispose());
    super.dispose();
  }

  Future<void> _connect({bool forceRestart = false}) async {
    if (!mounted) return;

    if (forceRestart) {
      await _service.stop();
    }

    final userId = _resolveUserId();
    final workspacePath = _resolveWorkspacePath();

    setState(() {
      _initializing = true;
      _statusMessage = 'Connecting...';
    });

    try {
      await _service.start(
        userId: userId,
        workspacePath: workspacePath,
      );
    } catch (e) {
      if (mounted) {
        setState(() {
          _statusMessage = 'Connection failed: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _initializing = false;
        });
      }
    }
  }

  void _onStatusChanged(IdeTerminalStatus status) {
    if (!mounted) return;

    setState(() {
      _status = status;
      final lastError = _service.lastError;
      _statusMessage = switch (status) {
        IdeTerminalStatus.idle => 'Idle',
        IdeTerminalStatus.opening => 'Opening IDE session...',
        IdeTerminalStatus.connecting => 'Connecting terminal...',
        IdeTerminalStatus.connected => 'Connected',
        IdeTerminalStatus.reconnecting => 'Reconnecting...',
        IdeTerminalStatus.closed => 'Closed',
        IdeTerminalStatus.error => lastError == null ? 'Connection error' : 'Connection error: $lastError',
      };
    });
  }

  void _onTerminalOutput(String chunk) {
    if (!mounted || chunk.isEmpty) return;

    var next = _output + chunk;
    if (next.length > _maxOutputChars) {
      final trim = next.length - _maxOutputChars;
      _droppedChars += trim;
      next = next.substring(trim);
    }

    setState(() {
      _output = next;
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
    });
  }

  String _resolveUserId() {
    try {
      final auth = context.read<AuthProvider>();
      return auth.user?.id ?? 'guest-local';
    } catch (_) {
      return 'guest-local';
    }
  }

  String _resolveWorkspacePath() {
    try {
      return Directory.current.path;
    } catch (_) {
      return '.';
    }
  }

  Future<void> _submitInput() async {
    final text = _inputController.text;
    if (text.trim().isEmpty) return;

    _inputController.clear();
    await _service.sendInput('$text\n');
  }

  Future<void> _sendCtrlC() async {
    await _service.sendInput('\u0003');
  }

  Color _statusColor() {
    return switch (_status) {
      IdeTerminalStatus.connected => Colors.greenAccent,
      IdeTerminalStatus.connecting ||
      IdeTerminalStatus.opening ||
      IdeTerminalStatus.reconnecting =>
        Colors.orangeAccent,
      IdeTerminalStatus.error => ZoyaTheme.danger,
      _ => ZoyaTheme.textMuted,
    };
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('ide-pane-terminal'),
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
          ),
          child: Row(
            children: [
              Icon(Icons.circle, size: 10, color: _statusColor()),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _statusMessage,
                  style: const TextStyle(
                    color: ZoyaTheme.textMuted,
                    fontSize: 12,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              if (_droppedChars > 0)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Text(
                    'trimmed $_droppedChars chars',
                    style: TextStyle(
                      color: ZoyaTheme.textMuted.withValues(alpha: 0.7),
                      fontSize: 11,
                    ),
                  ),
                ),
              IconButton(
                tooltip: 'Reconnect terminal',
                icon: const Icon(Icons.refresh, color: ZoyaTheme.textMuted, size: 18),
                onPressed: _initializing ? null : () => _connect(forceRestart: true),
              ),
              IconButton(
                tooltip: 'Clear output',
                icon: const Icon(Icons.clear_all, color: ZoyaTheme.textMuted, size: 18),
                onPressed: () {
                  setState(() {
                    _output = '';
                    _droppedChars = 0;
                  });
                },
              ),
            ],
          ),
        ),
        Expanded(
          child: Container(
            color: const Color(0xFF0B1220),
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            child: SingleChildScrollView(
              controller: _scrollController,
              child: SelectableText(
                _output.isEmpty ? 'Terminal ready. Type a command and press Enter.\n' : _output,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 12,
                  height: 1.35,
                  color: Color(0xFFBFDBFE),
                ),
              ),
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
          decoration: BoxDecoration(
            color: ZoyaTheme.glassBg,
            border: Border(top: BorderSide(color: ZoyaTheme.glassBorder)),
          ),
          child: Row(
            children: [
              IconButton(
                tooltip: 'Send Ctrl+C',
                onPressed: _status == IdeTerminalStatus.connected ? _sendCtrlC : null,
                icon: const Icon(Icons.cancel_schedule_send, size: 18),
                color: ZoyaTheme.textMuted,
              ),
              Expanded(
                child: TextField(
                  controller: _inputController,
                  onSubmitted: (_) => _submitInput(),
                  style: const TextStyle(
                    color: ZoyaTheme.textMain,
                    fontFamily: 'monospace',
                    fontSize: 12,
                  ),
                  decoration: InputDecoration(
                    hintText: 'Run command... (press Enter)',
                    hintStyle: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.8)),
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                    enabledBorder: OutlineInputBorder(
                      borderSide: BorderSide(color: ZoyaTheme.glassBorder),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderSide: BorderSide(color: ZoyaTheme.accent.withValues(alpha: 0.8)),
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _status == IdeTerminalStatus.connected ? _submitInput : null,
                style: FilledButton.styleFrom(
                  backgroundColor: ZoyaTheme.accent,
                  foregroundColor: Colors.black,
                ),
                child: const Text('Send'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _AgenticPane extends StatefulWidget {
  const _AgenticPane({this.service});

  final IdeAgenticService? service;

  @override
  State<_AgenticPane> createState() => _AgenticPaneState();
}

class _AgenticPaneState extends State<_AgenticPane> {
  static const int _maxEvents = 400;

  late final IdeAgenticService _service;
  StreamSubscription<IdeAgenticEvent>? _eventSub;
  StreamSubscription<IdeAgenticConnectionState>? _stateSub;
  Timer? _flushTimer;

  final List<IdeAgenticEvent> _events = <IdeAgenticEvent>[];
  final List<IdeAgenticEvent> _pendingEvents = <IdeAgenticEvent>[];
  final Set<int> _seenSeq = <int>{};
  final List<int> _recentEventTimestampsMs = <int>[];

  IdeAgenticConnectionState _connectionState = IdeAgenticConnectionState.idle;
  bool _isCatchingUp = false;
  String? _errorBanner;

  String _selectedEventType = 'All';
  String _selectedStatus = 'All';
  String _selectedTaskId = 'All';
  String _selectedAgentId = 'All';
  String? _focusedTaskId;

  @override
  void initState() {
    super.initState();
    _service = widget.service ?? IdeAgenticService();
    _eventSub = _service.events.listen(_onAgenticEvent);
    _stateSub = _service.stateStream.listen((state) {
      if (!mounted) return;
      setState(() {
        _connectionState = state;
        _errorBanner = state == IdeAgenticConnectionState.error ? _service.lastError ?? 'Connection error' : null;
      });
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_service.start());
    });
  }

  @override
  void dispose() {
    _flushTimer?.cancel();
    if (_eventSub != null) {
      unawaited(_eventSub!.cancel());
    }
    if (_stateSub != null) {
      unawaited(_stateSub!.cancel());
    }
    unawaited(_service.dispose());
    super.dispose();
  }

  void _onAgenticEvent(IdeAgenticEvent event) {
    if (!mounted) return;
    if (_seenSeq.contains(event.seq)) return;
    _seenSeq.add(event.seq);

    final now = DateTime.now().millisecondsSinceEpoch;
    _recentEventTimestampsMs.add(now);
    _recentEventTimestampsMs.removeWhere((ts) => (now - ts) > 1000);
    final shouldCatchUp = _recentEventTimestampsMs.length > 60;

    if (_isCatchingUp != shouldCatchUp) {
      setState(() {
        _isCatchingUp = shouldCatchUp;
      });
    }

    if (shouldCatchUp) {
      _pendingEvents.add(event);
      _flushTimer ??= Timer.periodic(const Duration(milliseconds: 200), (_) {
        if (!mounted) return;
        if (_pendingEvents.isEmpty) return;
        setState(() {
          _events.insertAll(0, _pendingEvents);
          _pendingEvents.clear();
          if (_events.length > _maxEvents) {
            _events.removeRange(_maxEvents, _events.length);
          }
        });
      });
      return;
    }

    if (_flushTimer != null) {
      _flushTimer?.cancel();
      _flushTimer = null;
      if (_pendingEvents.isNotEmpty) {
        _events.insertAll(0, _pendingEvents);
        _pendingEvents.clear();
      }
    }

    setState(() {
      _events.insert(0, event);
      if (_events.length > _maxEvents) {
        _events.removeRange(_maxEvents, _events.length);
      }
    });
  }

  List<IdeAgenticEvent> _filteredEvents() {
    return _events.where((event) {
      if (_selectedEventType != 'All' && event.eventType != _selectedEventType) return false;
      if (_selectedStatus != 'All' && (event.status ?? '-') != _selectedStatus) return false;
      if (_selectedTaskId != 'All' && (event.taskId ?? '-') != _selectedTaskId) return false;
      if (_selectedAgentId != 'All' && (event.agentId ?? '-') != _selectedAgentId) return false;
      return true;
    }).toList(growable: false);
  }

  List<String> _valuesFor(String kind) {
    final values = <String>{};
    for (final event in _events) {
      switch (kind) {
        case 'event_type':
          values.add(event.eventType);
          break;
        case 'status':
          values.add(event.status ?? '-');
          break;
        case 'task_id':
          values.add(event.taskId ?? '-');
          break;
        case 'agent_id':
          values.add(event.agentId ?? '-');
          break;
      }
    }
    final sorted = values.toList()..sort();
    return <String>['All', ...sorted];
  }

  Color _statusColor(IdeAgenticConnectionState state) {
    switch (state) {
      case IdeAgenticConnectionState.connected:
        return Colors.greenAccent;
      case IdeAgenticConnectionState.reconnecting:
      case IdeAgenticConnectionState.connecting:
        return Colors.orangeAccent;
      case IdeAgenticConnectionState.error:
        return ZoyaTheme.danger;
      case IdeAgenticConnectionState.closed:
      case IdeAgenticConnectionState.idle:
        return ZoyaTheme.textMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filteredEvents();
    final analysis = deriveAgenticAnalysis(
      filtered,
      maxGraphNodes: 100,
    );
    final focusedTaskId = _resolveFocusedTaskId(analysis.taskSummaries);
    final selectedTaskSummary = _taskSummaryById(
      analysis.taskSummaries,
      focusedTaskId,
    );
    final selectedTaskEvents = focusedTaskId == null
        ? <IdeAgenticEvent>[]
        : (List<IdeAgenticEvent>.from(analysis.eventsByTask[focusedTaskId] ?? const <IdeAgenticEvent>[])
          ..sort((a, b) => a.seq.compareTo(b.seq)));
    final selectedTrace =
        selectedTaskSummary?.traceId == null ? null : analysis.tracesById[selectedTaskSummary!.traceId!];
    final statusLabel = _isCatchingUp ? 'Catching up' : 'Live';

    return Container(
      key: const Key('ide-pane-agentic'),
      color: const Color(0xFF0A0F1A),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Row(
              children: [
                Container(
                  key: const Key('ide-agentic-connection'),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: _statusColor(_connectionState).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: _statusColor(_connectionState).withValues(alpha: 0.5)),
                  ),
                  child: Text(
                    _connectionState.name,
                    style: TextStyle(color: _statusColor(_connectionState), fontSize: 11, fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: 10),
                Container(
                  key: const Key('ide-agentic-live-state'),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: (_isCatchingUp ? Colors.orange : Colors.green).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    statusLabel,
                    style: TextStyle(
                      color: _isCatchingUp ? Colors.orangeAccent : Colors.greenAccent,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const Spacer(),
                Text(
                  'Seq ${_service.lastSeq}',
                  style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.9), fontSize: 11),
                ),
              ],
            ),
          ),
          _buildFilters(),
          if (_errorBanner != null)
            Container(
              width: double.infinity,
              color: ZoyaTheme.danger.withValues(alpha: 0.12),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Text(
                _errorBanner!,
                style: const TextStyle(color: ZoyaTheme.danger, fontSize: 12),
              ),
            ),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                if (constraints.maxWidth < 1100) {
                  return Column(
                    children: [
                      Expanded(
                        child: _buildTaskListPane(
                          analysis.taskSummaries,
                          focusedTaskId: focusedTaskId,
                        ),
                      ),
                      Divider(height: 1, color: ZoyaTheme.glassBorder),
                      Expanded(
                        child: _buildDrilldownPane(
                          selectedTaskSummary: selectedTaskSummary,
                          selectedTaskEvents: selectedTaskEvents,
                        ),
                      ),
                      Divider(height: 1, color: ZoyaTheme.glassBorder),
                      Expanded(
                        child: _buildTraceAndGraphPane(
                          selectedTaskSummary: selectedTaskSummary,
                          selectedTrace: selectedTrace,
                          graph: analysis.graph,
                        ),
                      ),
                    ],
                  );
                }
                return Row(
                  children: [
                    Expanded(
                      flex: 3,
                      child: _buildTaskListPane(
                        analysis.taskSummaries,
                        focusedTaskId: focusedTaskId,
                      ),
                    ),
                    VerticalDivider(width: 1, color: ZoyaTheme.glassBorder),
                    Expanded(
                      flex: 4,
                      child: _buildDrilldownPane(
                        selectedTaskSummary: selectedTaskSummary,
                        selectedTaskEvents: selectedTaskEvents,
                      ),
                    ),
                    VerticalDivider(width: 1, color: ZoyaTheme.glassBorder),
                    Expanded(
                      flex: 4,
                      child: _buildTraceAndGraphPane(
                        selectedTaskSummary: selectedTaskSummary,
                        selectedTrace: selectedTrace,
                        graph: analysis.graph,
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilters() {
    return Container(
      key: const Key('ide-agentic-filters'),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          _buildFilterDropdown(
            keyName: 'event_type',
            label: 'Type',
            value: _selectedEventType,
            items: _valuesFor('event_type'),
            onChanged: (value) => setState(() => _selectedEventType = value),
          ),
          _buildFilterDropdown(
            keyName: 'status',
            label: 'Status',
            value: _selectedStatus,
            items: _valuesFor('status'),
            onChanged: (value) => setState(() => _selectedStatus = value),
          ),
          _buildFilterDropdown(
            keyName: 'task_id',
            label: 'Task',
            value: _selectedTaskId,
            items: _valuesFor('task_id'),
            onChanged: (value) => setState(() => _selectedTaskId = value),
          ),
          _buildFilterDropdown(
            keyName: 'agent_id',
            label: 'Agent',
            value: _selectedAgentId,
            items: _valuesFor('agent_id'),
            onChanged: (value) => setState(() => _selectedAgentId = value),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterDropdown({
    required String keyName,
    required String label,
    required String value,
    required List<String> items,
    required ValueChanged<String> onChanged,
  }) {
    return SizedBox(
      width: 180,
      child: DropdownButtonFormField<String>(
        key: Key('ide-agentic-filter-$keyName'),
        initialValue: items.contains(value) ? value : 'All',
        isExpanded: true,
        decoration: InputDecoration(
          labelText: label,
          labelStyle: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.85), fontSize: 12),
          isDense: true,
          contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          enabledBorder: OutlineInputBorder(
            borderSide: BorderSide(color: ZoyaTheme.glassBorder),
            borderRadius: BorderRadius.circular(8),
          ),
          focusedBorder: OutlineInputBorder(
            borderSide: BorderSide(color: ZoyaTheme.accent.withValues(alpha: 0.7)),
            borderRadius: BorderRadius.circular(8),
          ),
        ),
        dropdownColor: const Color(0xFF0F172A),
        style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 12),
        items: items
            .map(
              (item) => DropdownMenuItem<String>(
                value: item,
                child: Text(item, overflow: TextOverflow.ellipsis),
              ),
            )
            .toList(growable: false),
        onChanged: (next) {
          if (next == null) return;
          onChanged(next);
        },
      ),
    );
  }

  String? _resolveFocusedTaskId(List<AgenticTaskSummary> taskSummaries) {
    if (taskSummaries.isEmpty) {
      return null;
    }
    final existing = _focusedTaskId;
    if (existing != null && taskSummaries.any((task) => task.taskId == existing)) {
      return existing;
    }
    return taskSummaries.first.taskId;
  }

  AgenticTaskSummary? _taskSummaryById(List<AgenticTaskSummary> taskSummaries, String? taskId) {
    if (taskId == null) return null;
    for (final task in taskSummaries) {
      if (task.taskId == taskId) return task;
    }
    return null;
  }

  Color _taskStatusColor(String status) {
    switch (status.toLowerCase()) {
      case 'completed':
        return Colors.greenAccent;
      case 'failed':
        return ZoyaTheme.danger;
      default:
        return Colors.orangeAccent;
    }
  }

  Widget _buildTaskListPane(
    List<AgenticTaskSummary> tasks, {
    required String? focusedTaskId,
  }) {
    if (tasks.isEmpty) {
      return Center(
        child: Text(
          'Waiting for runtime events…',
          style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.85)),
        ),
      );
    }

    return ListView.separated(
      key: const Key('ide-agentic-task-list'),
      itemCount: tasks.length,
      separatorBuilder: (_, __) => Divider(height: 1, color: ZoyaTheme.glassBorder),
      itemBuilder: (context, index) {
        final task = tasks[index];
        final isSelected = task.taskId == focusedTaskId;
        final statusColor = _taskStatusColor(task.status);
        return ListTile(
          key: Key('ide-agentic-task-row-${task.taskId}'),
          dense: true,
          selected: isSelected,
          selectedTileColor: ZoyaTheme.accent.withValues(alpha: 0.08),
          onTap: () {
            setState(() {
              _focusedTaskId = task.taskId;
            });
          },
          title: Row(
            children: [
              Expanded(
                child: Text(
                  task.taskId,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: ZoyaTheme.textMain, fontWeight: FontWeight.w600, fontSize: 12),
                ),
              ),
              Container(
                key: Key('ide-agentic-task-status-${task.taskId}'),
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  task.status,
                  style: TextStyle(color: statusColor, fontSize: 10, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          subtitle: Text(
            '${task.eventCount} events · seq ${task.firstSeq}-${task.lastSeq}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.8), fontSize: 11),
          ),
          trailing: Text(
            '#${task.lastSeq}',
            style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.75), fontSize: 11),
          ),
        );
      },
    );
  }

  Widget _buildDrilldownPane({
    required AgenticTaskSummary? selectedTaskSummary,
    required List<IdeAgenticEvent> selectedTaskEvents,
  }) {
    if (selectedTaskSummary == null) {
      return Center(
        child: Text(
          'Select a task to inspect execution trace',
          style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.85)),
        ),
      );
    }

    return Container(
      key: const Key('ide-agentic-drilldown'),
      color: const Color(0xFF090F1A),
      child: Column(
        children: [
          Container(
            key: const Key('ide-agentic-drilldown-header'),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    selectedTaskSummary.taskId,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: ZoyaTheme.textMain, fontWeight: FontWeight.w700, fontSize: 12),
                  ),
                ),
                Text(
                  '${selectedTaskSummary.eventCount} events',
                  style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.85), fontSize: 11),
                ),
                const SizedBox(width: 8),
                Text(
                  selectedTaskSummary.status,
                  style: TextStyle(
                    color: _taskStatusColor(selectedTaskSummary.status),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView.separated(
              key: const Key('ide-agentic-drilldown-events'),
              itemCount: selectedTaskEvents.length,
              separatorBuilder: (_, __) => Divider(height: 1, color: ZoyaTheme.glassBorder),
              itemBuilder: (context, index) {
                final event = selectedTaskEvents[index];
                return ListTile(
                  dense: true,
                  leading: Text(
                    '#${event.seq}',
                    style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.7), fontSize: 10),
                  ),
                  title: Text(
                    event.eventType,
                    style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 12),
                  ),
                  subtitle: Text(
                    'status=${event.status ?? '-'} · agent=${event.agentId ?? '-'}',
                    style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.82), fontSize: 11),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTraceAndGraphPane({
    required AgenticTaskSummary? selectedTaskSummary,
    required AgenticTraceGroup? selectedTrace,
    required AgenticGraphSnapshot graph,
  }) {
    return Column(
      key: const Key('ide-agentic-trace-graph'),
      children: [
        Expanded(
          child: _buildTraceCorrelationView(
            selectedTaskSummary: selectedTaskSummary,
            selectedTrace: selectedTrace,
          ),
        ),
        Divider(height: 1, color: ZoyaTheme.glassBorder),
        Expanded(
          child: _buildDependencyGraph(graph),
        ),
      ],
    );
  }

  Widget _buildTraceCorrelationView({
    required AgenticTaskSummary? selectedTaskSummary,
    required AgenticTraceGroup? selectedTrace,
  }) {
    if (selectedTaskSummary == null) {
      return Center(
        child: Text(
          'Select a task to view correlated traces',
          style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.85)),
        ),
      );
    }

    final traceId = selectedTaskSummary.traceId;
    if (traceId == null || selectedTrace == null || selectedTrace.events.isEmpty) {
      return Center(
        child: Text(
          'No trace_id correlation available',
          style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.85)),
        ),
      );
    }

    return Container(
      key: const Key('ide-agentic-trace-view'),
      color: const Color(0xFF09131F),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Row(
              children: [
                const Icon(Icons.hub, size: 14, color: ZoyaTheme.textMuted),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'trace_id: $traceId',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ),
                Text(
                  '${selectedTrace.events.length} events',
                  style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.82), fontSize: 11),
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView.separated(
              key: const Key('ide-agentic-trace-events'),
              itemCount: selectedTrace.events.length,
              separatorBuilder: (_, __) => Divider(height: 1, color: ZoyaTheme.glassBorder),
              itemBuilder: (context, index) {
                final event = selectedTrace.events[index];
                return ListTile(
                  dense: true,
                  title: Text(
                    '${event.eventType} · task=${event.taskId ?? kUnscopedTaskId}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 12),
                  ),
                  trailing: Text(
                    '#${event.seq}',
                    style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.75), fontSize: 11),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDependencyGraph(AgenticGraphSnapshot graph) {
    final nodeLabelById = <String, String>{
      for (final node in graph.nodes) node.id: node.label,
    };

    return Container(
      key: const Key('ide-agentic-graph'),
      color: const Color(0xFF0A1421),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Row(
              children: [
                const Icon(Icons.account_tree_outlined, size: 14, color: ZoyaTheme.textMuted),
                const SizedBox(width: 6),
                Text(
                  'Graph (${graph.nodes.length} nodes, ${graph.edges.length} edges)',
                  style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 12, fontWeight: FontWeight.w600),
                ),
                const Spacer(),
                if (graph.truncated)
                  Text(
                    'trimmed ${graph.droppedNodes}',
                    style: TextStyle(color: Colors.orangeAccent.withValues(alpha: 0.9), fontSize: 11),
                  ),
              ],
            ),
          ),
          if (graph.nodes.isEmpty)
            Expanded(
              child: Center(
                child: Text(
                  'No dependency graph data',
                  style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.85)),
                ),
              ),
            )
          else
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(10),
                children: [
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: graph.nodes
                        .map(
                          (node) => Container(
                            key: Key('ide-agentic-graph-node-${node.id}'),
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                            decoration: BoxDecoration(
                              color: node.type == AgenticGraphNodeType.task
                                  ? ZoyaTheme.accent.withValues(alpha: 0.15)
                                  : Colors.blueGrey.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: ZoyaTheme.glassBorder),
                            ),
                            child: Text(
                              '${node.type.name}: ${node.label}',
                              style: const TextStyle(color: ZoyaTheme.textMain, fontSize: 11),
                            ),
                          ),
                        )
                        .toList(growable: false),
                  ),
                  const SizedBox(height: 12),
                  if (graph.edges.isEmpty)
                    Text(
                      'No dependency edges yet',
                      style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.8), fontSize: 11),
                    )
                  else
                    ...graph.edges.map(
                      (edge) {
                        final from = nodeLabelById[edge.fromNodeId] ?? edge.fromNodeId;
                        final to = nodeLabelById[edge.toNodeId] ?? edge.toNodeId;
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: Text(
                            '$from → $to (${edge.kind})',
                            style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.9), fontSize: 11),
                          ),
                        );
                      },
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
