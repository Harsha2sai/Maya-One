import 'package:flutter/material.dart';
import '../shared_widgets.dart';
import '../../ui/zoya_theme.dart';
import '../../state/providers/settings_provider.dart';
import 'package:provider/provider.dart';

class MemoryPanel extends StatelessWidget {
  final bool mem0Enabled;
  final String mem0ApiKey;
  final Function(bool) onEnabledChanged;
  final Function(String) onApiKeyChanged;

  const MemoryPanel({
    super.key,
    required this.mem0Enabled,
    required this.mem0ApiKey,
    required this.onEnabledChanged,
    required this.onApiKeyChanged,
  });

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('💾 Mem0 Memory System', 'Enable persistent memory to remember conversations across sessions.'),
        _buildToggle('Enable Memory Storage', mem0Enabled, onChanged: onEnabledChanged),
        const SizedBox(height: 24),
        
        _buildSecureApiKeyInput(context, 'Mem0', 'mem0', mem0ApiKey.isNotEmpty),
        
        const SizedBox(height: 20),
        Text(
          'Get your API key from mem0.ai',
          style: TextStyle(color: ZoyaTheme.accent.withValues(alpha: 0.8), fontSize: 12),
        ),
        
        const SizedBox(height: 40),
        buildSubsectionHeader('📤 Data Management'),
        const SizedBox(height: 16),
        Row(
          children: [
            ElevatedButton.icon(
              onPressed: () {
                // TODO: Implement export
              },
              icon: const Icon(Icons.download),
              label: const Text('Export Memories'),
              style: ElevatedButton.styleFrom(
                backgroundColor: ZoyaTheme.accent.withValues(alpha: 0.2),
                foregroundColor: ZoyaTheme.accent,
              ),
            ),
            const SizedBox(width: 16),
            ElevatedButton.icon(
              onPressed: () {
                // TODO: Implement clear with confirmation
              },
              icon: const Icon(Icons.delete),
              label: const Text('Clear All Memories'),
              style: ElevatedButton.styleFrom(
                backgroundColor: ZoyaTheme.danger.withValues(alpha: 0.2),
                foregroundColor: ZoyaTheme.danger,
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildToggle(String label, bool value, {required ValueChanged<bool> onChanged}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 14)),
          Switch(
            value: value,
            onChanged: onChanged,
            activeThumbColor: ZoyaTheme.accent,
          ),
        ],
      ),
    );
  }

  Widget _buildSecureApiKeyInput(BuildContext context, String label, String provider, bool isConfigured) {
    final settings = context.read<SettingsProvider>();
    final maskedValue = settings.maskedApiKeys[provider] ?? '';
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: Colors.white70, fontSize: 13)),
            buildStatusBadge(isConfigured),
          ],
        ),
        const SizedBox(height: 8),
        TextField(
          obscureText: true,
          onChanged: onApiKeyChanged,
          style: const TextStyle(color: Colors.white, fontSize: 14),
          decoration: InputDecoration(
            hintText: maskedValue.isNotEmpty ? maskedValue : 'Enter $label API Key',
            hintStyle: TextStyle(
              color: maskedValue.isNotEmpty ? ZoyaTheme.success.withValues(alpha: 0.6) : Colors.white24,
            ),
            filled: true,
            fillColor: Colors.white.withValues(alpha: 0.05),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
          ),
        ),
      ],
    );
  }
}
