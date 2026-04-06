import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';
import '../../core/config/provider_config.dart';

class DeveloperPanel extends StatefulWidget {
  final bool isAdvancedMode;
  final Map<String, String> localApiKeys;
  final Map<String, dynamic> apiKeyStatus;
  final Function(bool) onAdvancedModeChanged;
  final Function(String, String) onApiKeyChanged;
  final String awsAccessKey;
  final String awsSecretKey;
  final String awsRegion;
  final Function(String) onAwsAccessKeyChanged;
  final Function(String) onAwsSecretKeyChanged;
  final Function(String) onAwsRegionChanged;

  const DeveloperPanel({
    super.key,
    required this.isAdvancedMode,
    required this.localApiKeys,
    required this.apiKeyStatus,
    required this.onAdvancedModeChanged,
    required this.onApiKeyChanged,
    required this.awsAccessKey,
    required this.awsSecretKey,
    required this.awsRegion,
    required this.onAwsAccessKeyChanged,
    required this.onAwsSecretKeyChanged,
    required this.onAwsRegionChanged,
  });

  @override
  State<DeveloperPanel> createState() => _DeveloperPanelState();
}

class _DeveloperPanelState extends State<DeveloperPanel> {
  static const int _maxSlots = 3;
  final Map<String, bool> _showApiKey = {};

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('🛠️ Developer Settings', 'Advanced tools and configuration for system engineers.'),
        const SizedBox(height: 24),
        _buildAdvancedToggle(),
        const SizedBox(height: 16),
        _buildExtApiKeySection(),
        const SizedBox(height: 40),
        if (widget.isAdvancedMode) ...[
          buildSubsectionHeader('📡 LiveKit Configuration'),
          _buildLiveKitSection(),
          const SizedBox(height: 40),
          buildSubsectionHeader('🤖 LLM Providers'),
          ...[
            'groq',
            'openai',
            'gemini',
            'anthropic',
            'deepseek',
            'mistral',
            'perplexity',
            'together',
          ].map((id) => _buildSlotAwareApiKeyField(ProviderConfig.getProviderName(id, 'llm'), id)),
          const SizedBox(height: 40),
          buildSubsectionHeader('🎤 Speech Providers'),
          ...[
            'deepgram',
            'assemblyai',
            'cartesia',
            'elevenlabs',
          ].map((id) => _buildSlotAwareApiKeyField(
              ProviderConfig.getProviderName(id, id.contains('deep') || id.contains('assembly') ? 'stt' : 'tts'), id)),
          const SizedBox(height: 40),
          buildSubsectionHeader('☁️ Cloud & Infrastructure'),
          _buildAwsCredentialsSection(),
        ] else ...[
          const Center(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 40),
              child: Text(
                'Enable Advanced Mode to view system configurations.',
                style: TextStyle(color: Colors.white24, fontSize: 13, fontStyle: FontStyle.italic),
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildAdvancedToggle() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: widget.isAdvancedMode
            ? ZoyaTheme.secondaryAccent.withValues(alpha: 0.1)
            : Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: widget.isAdvancedMode ? ZoyaTheme.secondaryAccent.withValues(alpha: 0.3) : Colors.white12),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text('ADVANCED MODE',
                    style: ZoyaTheme.fontDisplay.copyWith(
                        color: widget.isAdvancedMode ? ZoyaTheme.secondaryAccent : Colors.white,
                        fontSize: 13,
                        letterSpacing: 2,
                        fontWeight: FontWeight.bold)),
              ),
              Switch(
                value: widget.isAdvancedMode,
                onChanged: widget.onAdvancedModeChanged,
                activeThumbColor: ZoyaTheme.secondaryAccent,
              ),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'Enabling Advanced Mode reveals LiveKit, API Key slots, and cloud infrastructure settings necessary for system orchestration.',
            style: TextStyle(color: Colors.white38, fontSize: 11, height: 1.4),
          ),
        ],
      ),
    );
  }

  Widget _buildLiveKitSection() {
    final status = widget.apiKeyStatus['livekit'] == true;
    final activeSlot = _selectedSlot('livekit_active_slot');
    final urlKey = _slotKey('livekit_url', activeSlot);
    final apiKeyName = _slotKey('livekit_api_key', activeSlot);
    final secretKeyName = _slotKey('livekit_api_secret', activeSlot);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.03),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('LIVEKIT CLOUD',
                  style:
                      TextStyle(color: Colors.white54, fontSize: 11, letterSpacing: 1.5, fontWeight: FontWeight.bold)),
              buildStatusBadge(status),
            ],
          ),
          const SizedBox(height: 20),
          _buildSlotSelector('livekit_active_slot', activeSlot),
          const SizedBox(height: 20),
          _buildTextField('Server URL', urlKey, widget.localApiKeys[urlKey] ?? ''),
          const SizedBox(height: 16),
          _buildTextField('API Key', apiKeyName, widget.localApiKeys[apiKeyName] ?? '', obscure: true),
          const SizedBox(height: 16),
          _buildTextField('API Secret', secretKeyName, widget.localApiKeys[secretKeyName] ?? '', obscure: true),
        ],
      ),
    );
  }

  Widget _buildAwsCredentialsSection() {
    final status = widget.apiKeyStatus['aws'] == true;
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.orange.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.orange.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  const FaIcon(FontAwesomeIcons.aws, color: Colors.orange, size: 16),
                  const SizedBox(width: 10),
                  const Text('AWS Polly',
                      style: TextStyle(
                          color: Colors.orange, fontSize: 11, letterSpacing: 1.5, fontWeight: FontWeight.bold)),
                ],
              ),
              buildStatusBadge(status),
            ],
          ),
          const SizedBox(height: 20),
          _buildTextField('Access Key', 'aws_access_key', widget.awsAccessKey,
              obscure: true, onManualChange: widget.onAwsAccessKeyChanged),
          const SizedBox(height: 16),
          _buildTextField('Secret Key', 'aws_secret_key', widget.awsSecretKey,
              obscure: true, onManualChange: widget.onAwsSecretKeyChanged),
          const SizedBox(height: 16),
          _buildRegionDropdown('Region', widget.awsRegion, widget.onAwsRegionChanged),
        ],
      ),
    );
  }

  Widget _buildExtApiKeySection() {
    final activeSlot = _selectedSlot('ext_api_key_active_slot', slotCount: 2);
    final keyName = _slotKey('ext_api_key', activeSlot);
    final hasValue = ['ext_api_key', 'ext_api_key_2'].any(
      (k) => (widget.localApiKeys[k] ?? '').trim().isNotEmpty,
    );
    final status = widget.apiKeyStatus['ext_api_key'] == true || hasValue;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: ZoyaTheme.accent.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: ZoyaTheme.accent.withValues(alpha: 0.12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'EXT API KEY',
                style: TextStyle(
                  color: Colors.white54,
                  fontSize: 11,
                  letterSpacing: 1.5,
                  fontWeight: FontWeight.bold,
                ),
              ),
              buildStatusBadge(status),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'Future integration key. Stored now, feature enablement will be wired later.',
            style: TextStyle(color: Colors.white38, fontSize: 11, height: 1.4),
          ),
          const SizedBox(height: 16),
          const Text(
            'Select: |_|_|',
            style: TextStyle(color: Colors.white38, fontSize: 11),
          ),
          const SizedBox(height: 8),
          _buildSlotSelector('ext_api_key_active_slot', activeSlot, compact: true, slotCount: 2),
          const SizedBox(height: 12),
          _buildTextField(
            'EXT API Key',
            keyName,
            widget.localApiKeys[keyName] ?? '',
            obscure: true,
          ),
        ],
      ),
    );
  }

  // --- Helper Widgets ---

  Widget _buildSlotAwareApiKeyField(String label, String provider) {
    final slotKey = '${provider}_active_key_slot';
    final activeSlot = _selectedSlot(slotKey);
    final keyName = _slotKey(provider, activeSlot);
    final isVisible = _showApiKey[keyName] ?? false;
    final value = widget.localApiKeys[keyName] ?? '';
    final status = widget.apiKeyStatus[provider] == true;

    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label.toUpperCase(),
                  style: const TextStyle(color: Colors.white54, fontSize: 10, letterSpacing: 1.5)),
              buildStatusBadge(status),
            ],
          ),
          const SizedBox(height: 8),
          _buildSlotSelector(slotKey, activeSlot, compact: true),
          const SizedBox(height: 8),
          TextFormField(
            key: ValueKey('dev_key_$keyName'),
            initialValue: value,
            onChanged: (v) => widget.onApiKeyChanged(keyName, v),
            obscureText: !isVisible,
            style: const TextStyle(color: Colors.white, fontSize: 13, fontFamily: 'monospace'),
            decoration: InputDecoration(
              filled: true,
              fillColor: ZoyaTheme.sidebarBg.withValues(alpha: 0.5),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: ZoyaTheme.glassBorder)),
              enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: ZoyaTheme.glassBorder)),
              focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: ZoyaTheme.accent.withValues(alpha: 0.5))),
              suffixIcon: IconButton(
                icon: Icon(isVisible ? Icons.visibility_off : Icons.visibility, size: 16, color: Colors.white24),
                onPressed: () => setState(() => _showApiKey[keyName] = !isVisible),
              ),
              hintText: 'Enter $label key...',
              hintStyle: const TextStyle(color: Colors.white12, fontSize: 13),
              prefixIcon: Icon(Icons.key_outlined,
                  size: 16, color: status ? ZoyaTheme.success.withValues(alpha: 0.6) : Colors.white24),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSlotSelector(String key, int activeSlot, {bool compact = false, int slotCount = _maxSlots}) {
    return Row(
      children: [
        if (!compact) const Text('Active Slot: ', style: TextStyle(color: Colors.white38, fontSize: 12)),
        ...List.generate(slotCount, (index) {
          final slotId = index + 1;
          final isActive = activeSlot == slotId;
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: InkWell(
              key: ValueKey('slot_${key}_$slotId'),
              onTap: () => widget.onApiKeyChanged(key, '$slotId'),
              borderRadius: BorderRadius.circular(8),
              child: Container(
                padding: EdgeInsets.symmetric(horizontal: compact ? 10 : 16, vertical: 6),
                decoration: BoxDecoration(
                  color: isActive ? ZoyaTheme.accent.withValues(alpha: 0.2) : Colors.white.withValues(alpha: 0.05),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: isActive ? ZoyaTheme.accent.withValues(alpha: 0.4) : Colors.white12),
                ),
                child: Text(
                  'S$slotId',
                  style: TextStyle(
                    color: isActive ? ZoyaTheme.accent : Colors.white38,
                    fontSize: 11,
                    fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
                  ),
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildTextField(String label, String keyName, String value,
      {bool obscure = false, Function(String)? onManualChange}) {
    final isVisible = _showApiKey[keyName] ?? !obscure;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(), style: const TextStyle(color: Colors.white54, fontSize: 10, letterSpacing: 1.5)),
        const SizedBox(height: 8),
        TextFormField(
          key: ValueKey('dev_text_$keyName'),
          initialValue: value,
          onChanged: (v) => (onManualChange != null) ? onManualChange(v) : widget.onApiKeyChanged(keyName, v),
          obscureText: !isVisible,
          style: const TextStyle(color: Colors.white, fontSize: 13),
          decoration: InputDecoration(
            filled: true,
            fillColor: ZoyaTheme.sidebarBg.withValues(alpha: 0.5),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: ZoyaTheme.glassBorder)),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: ZoyaTheme.glassBorder)),
            focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: ZoyaTheme.accent.withValues(alpha: 0.5))),
            suffixIcon: obscure
                ? IconButton(
                    icon: Icon(isVisible ? Icons.visibility_off : Icons.visibility, size: 16, color: Colors.white24),
                    onPressed: () => setState(() => _showApiKey[keyName] = !isVisible),
                  )
                : null,
          ),
        ),
      ],
    );
  }

  Widget _buildRegionDropdown(String label, String value, Function(String) onChanged) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(), style: const TextStyle(color: Colors.white54, fontSize: 10, letterSpacing: 1.5)),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: ZoyaTheme.sidebarBg.withValues(alpha: 0.5),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: ZoyaTheme.glassBorder),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: value,
              isExpanded: true,
              dropdownColor: Colors.grey[900],
              style: const TextStyle(color: Colors.white, fontSize: 13),
              items: ProviderConfig.awsRegions
                  .map((r) => DropdownMenuItem(
                        value: r['id'],
                        child: Text(r['name']!),
                      ))
                  .toList(),
              onChanged: (v) {
                if (v != null) onChanged(v);
              },
            ),
          ),
        ),
      ],
    );
  }

  int _selectedSlot(String slotKey, {int slotCount = _maxSlots}) {
    final val = widget.localApiKeys[slotKey] ?? widget.apiKeyStatus[slotKey]?.toString();
    final parsed = int.tryParse(val ?? '');
    return (parsed == null || parsed < 1 || parsed > slotCount) ? 1 : parsed;
  }

  String _slotKey(String baseKey, int slot) => (slot <= 1) ? baseKey : '${baseKey}_$slot';
}
