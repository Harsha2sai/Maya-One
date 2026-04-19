import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/services/ide_terminal_service.dart';
import '../../../state/providers/auth_provider.dart';
import '../../../ui/theme/app_theme.dart';

class IDETab extends StatefulWidget {
  const IDETab({super.key});

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
            children: const [
              _FilesPane(),
              _TerminalPane(),
              _AgenticPane(),
            ],
          ),
        ),
      ],
    );
  }
}

class _FilesPane extends StatelessWidget {
  const _FilesPane();

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const Key('ide-pane-files'),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.folder_open, size: 48, color: ZoyaTheme.textMuted.withValues(alpha: 0.5)),
          const SizedBox(height: 16),
          const Text(
            'Files - Coming in P12.4',
            style: TextStyle(color: ZoyaTheme.textMuted, fontSize: 14),
          ),
          const SizedBox(height: 8),
          Text(
            'Workspace file tree and editing',
            style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.7), fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _TerminalPane extends StatefulWidget {
  const _TerminalPane();

  @override
  State<_TerminalPane> createState() => _TerminalPaneState();
}

class _TerminalPaneState extends State<_TerminalPane> {
  static const int _maxOutputChars = 200000;

  final IdeTerminalService _service = IdeTerminalService(maxOutputChars: _maxOutputChars);
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
      IdeTerminalStatus.connecting || IdeTerminalStatus.opening || IdeTerminalStatus.reconnecting => Colors.orangeAccent,
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

class _AgenticPane extends StatelessWidget {
  const _AgenticPane();

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const Key('ide-pane-agentic'),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.smart_toy_outlined, size: 48, color: ZoyaTheme.textMuted.withValues(alpha: 0.5)),
          const SizedBox(height: 16),
          const Text(
            'Agentic - Coming in P12.5',
            style: TextStyle(color: ZoyaTheme.textMuted, fontSize: 14),
          ),
          const SizedBox(height: 8),
          Text(
            'AI-powered code assistance',
            style: TextStyle(color: ZoyaTheme.textMuted.withValues(alpha: 0.7), fontSize: 12),
          ),
        ],
      ),
    );
  }
}
