import 'package:flutter/material.dart';
import '../../../ui/theme/app_theme.dart';

class IDETab extends StatefulWidget {
  const IDETab({super.key});

  @override
  State<IDETab> createState() => _IDETabState();
}

enum IDESubTab { files, terminal, agentic }

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
              Tab(text: 'Files', icon: Icon(Icons.folder_outlined, size: 18)),
              Tab(text: 'Terminal', icon: Icon(Icons.terminal_outlined, size: 18)),
              Tab(text: 'Agentic', icon: Icon(Icons.smart_toy_outlined, size: 18)),
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
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.folder_open, size: 48, color: ZoyaTheme.textMuted.withOpacity(0.5)),
          const SizedBox(height: 16),
          Text(
            'Files - Coming in P12.3',
            style: TextStyle(color: ZoyaTheme.textMuted, fontSize: 14),
          ),
          const SizedBox(height: 8),
          Text(
            'Workspace file tree and editing',
            style: TextStyle(color: ZoyaTheme.textMuted.withOpacity(0.7), fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _TerminalPane extends StatelessWidget {
  const _TerminalPane();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.terminal, size: 48, color: ZoyaTheme.textMuted.withOpacity(0.5)),
          const SizedBox(height: 16),
          Text(
            'Terminal - Coming in P12.4',
            style: TextStyle(color: ZoyaTheme.textMuted, fontSize: 14),
          ),
          const SizedBox(height: 8),
          Text(
            'Remote shell execution via backend',
            style: TextStyle(color: ZoyaTheme.textMuted.withOpacity(0.7), fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _AgenticPane extends StatelessWidget {
  const _AgenticPane();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.smart_toy_outlined, size: 48, color: ZoyaTheme.textMuted.withOpacity(0.5)),
          const SizedBox(height: 16),
          Text(
            'Agentic - Coming in P12.5',
            style: TextStyle(color: ZoyaTheme.textMuted, fontSize: 14),
          ),
          const SizedBox(height: 8),
          Text(
            'AI-powered code assistance',
            style: TextStyle(color: ZoyaTheme.textMuted.withOpacity(0.7), fontSize: 12),
          ),
        ],
      ),
    );
  }
}
