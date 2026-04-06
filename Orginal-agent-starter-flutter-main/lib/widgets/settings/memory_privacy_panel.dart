import 'package:flutter/material.dart';

import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';

class MemoryPrivacyPanel extends StatefulWidget {
  final bool mem0Enabled;
  final String mem0ApiKey;
  final ValueChanged<bool> onEnabledChanged;
  final ValueChanged<String> onApiKeyChanged;
  final VoidCallback onClearHistory;
  final VoidCallback onExportData;

  const MemoryPrivacyPanel({
    super.key,
    required this.mem0Enabled,
    required this.mem0ApiKey,
    required this.onEnabledChanged,
    required this.onApiKeyChanged,
    required this.onClearHistory,
    required this.onExportData,
  });

  @override
  State<MemoryPrivacyPanel> createState() => _MemoryPrivacyPanelState();
}

class _MemoryPrivacyPanelState extends State<MemoryPrivacyPanel> {
  late final TextEditingController _mem0ApiKeyController;

  @override
  void initState() {
    super.initState();
    _mem0ApiKeyController = TextEditingController(text: widget.mem0ApiKey);
  }

  @override
  void didUpdateWidget(covariant MemoryPrivacyPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.mem0ApiKey != oldWidget.mem0ApiKey && widget.mem0ApiKey != _mem0ApiKeyController.text) {
      _mem0ApiKeyController.text = widget.mem0ApiKey;
    }
  }

  @override
  void dispose() {
    _mem0ApiKeyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('🧠 Memory', 'Control how Maya preserves context across sessions.'),
        const SizedBox(height: 24),
        _buildMemoryToggle(
          'Long-term Memory (Mem0)',
          'Allows the assistant to remember your name, preferences, and facts about you indefinitely.',
          widget.mem0Enabled,
          widget.onEnabledChanged,
        ),
        if (widget.mem0Enabled) ...[
          const SizedBox(height: 20),
          _buildTextField('Mem0 API Key'),
        ],
        const SizedBox(height: 40),
        buildSectionHeader('🛡️ Privacy & Data', 'Manage your conversation data and history.'),
        const SizedBox(height: 20),
        _buildDataAction(
          'Clear Session History',
          'Deletes the current conversation context from the immediate buffer.',
          'CLEAR BUFFER',
          ZoyaTheme.danger,
          widget.onClearHistory,
          const Key('memory_clear_history_button'),
        ),
        const SizedBox(height: 12),
        _buildDataAction(
          'Export Memories & Chat Data',
          'Download a copy of all stored memories and interactions.',
          'EXPORT JSON',
          ZoyaTheme.accent,
          widget.onExportData,
          const Key('memory_export_data_button'),
        ),
      ],
    );
  }

  Widget _buildMemoryToggle(
    String title,
    String subtitle,
    bool value,
    ValueChanged<bool> onChanged,
  ) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.03),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: value ? ZoyaTheme.accent.withValues(alpha: 0.2) : Colors.white12,
        ),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
              ),
              Switch(
                value: value,
                onChanged: onChanged,
                activeThumbColor: ZoyaTheme.accent,
                activeTrackColor: ZoyaTheme.accent.withValues(alpha: 0.2),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            subtitle,
            style: TextStyle(color: Colors.white.withValues(alpha: 0.4), fontSize: 12, height: 1.4),
          ),
        ],
      ),
    );
  }

  Widget _buildDataAction(
    String title,
    String subtitle,
    String actionLabel,
    Color actionColor,
    VoidCallback onTap,
    Key? actionKey,
  ) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.05)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 4),
                Text(subtitle, style: const TextStyle(color: Colors.white38, fontSize: 11)),
              ],
            ),
          ),
          const SizedBox(width: 16),
          TextButton(
            key: actionKey,
            onPressed: onTap,
            style: TextButton.styleFrom(
              foregroundColor: actionColor,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              side: BorderSide(color: actionColor.withValues(alpha: 0.3)),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            child: Text(
              actionLabel,
              style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 1),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTextField(String label) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label.toUpperCase(),
          style: const TextStyle(color: Colors.white54, fontSize: 10, letterSpacing: 1.5),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _mem0ApiKeyController,
          onChanged: widget.onApiKeyChanged,
          obscureText: true,
          style: const TextStyle(color: Colors.white, fontSize: 14),
          decoration: InputDecoration(
            filled: true,
            fillColor: ZoyaTheme.sidebarBg.withValues(alpha: 0.5),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: ZoyaTheme.glassBorder),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: ZoyaTheme.glassBorder),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: ZoyaTheme.accent),
            ),
            suffixIcon: const Icon(Icons.vpn_key_outlined, size: 18, color: Colors.white24),
          ),
        ),
      ],
    );
  }
}
