import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/config/provider_config.dart';
import '../../state/providers/settings_provider.dart';
import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';

class ApiKeysPanel extends StatefulWidget {
  final Map<String, dynamic> apiKeys;
  final Map<String, bool> showApiKey;
  final String awsAccessKey;
  final String awsSecretKey;
  final String awsRegion;
  final double? llmTemperature;
  final Function(String, String) onApiKeyChanged;
  final Function(String, bool) onVisibilityChanged;
  final Function(String) onAwsAccessKeyChanged;
  final Function(String) onAwsSecretKeyChanged;
  final Function(String?) onAwsRegionChanged;
  final ValueChanged<double>? onTemperatureChanged;

  const ApiKeysPanel({
    super.key,
    required this.apiKeys,
    required this.showApiKey,
    required this.awsAccessKey,
    required this.awsSecretKey,
    required this.awsRegion,
    this.llmTemperature,
    required this.onApiKeyChanged,
    required this.onVisibilityChanged,
    required this.onAwsAccessKeyChanged,
    required this.onAwsSecretKeyChanged,
    required this.onAwsRegionChanged,
    this.onTemperatureChanged,
  });

  @override
  State<ApiKeysPanel> createState() => _ApiKeysPanelState();
}

class _ApiKeysPanelState extends State<ApiKeysPanel> {
  static const int _maxSlots = 3;

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();
    final apiStatus = settings.apiKeyStatus;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader(
          'API Keys',
          'Manage your API keys for different providers. Keys are stored securely.',
        ),
        const SizedBox(height: 20),
        buildSubsectionHeader('📡 LiveKit Configuration'),
        _buildLiveKitSection(apiStatus['livekit'] == true),
        const SizedBox(height: 30),
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
        ].map(
          (provider) => _buildSlotAwareProviderInput(
            ProviderConfig.getProviderName(provider, 'llm'),
            provider,
            apiStatus[provider] == true,
          ),
        ),
        const SizedBox(height: 30),
        buildSubsectionHeader('🎤 Speech Providers'),
        ...[
          'deepgram',
          'assemblyai',
          'cartesia',
          'elevenlabs',
        ].map(
          (provider) => _buildSlotAwareProviderInput(
            ProviderConfig.getProviderName(
              provider,
              provider.contains('deep') || provider.contains('assembly') ? 'stt' : 'tts',
            ),
            provider,
            apiStatus[provider] == true,
          ),
        ),
        const SizedBox(height: 30),
        buildSubsectionHeader('☁️ AWS Polly'),
        _buildAwsCredentialsSection(apiStatus['aws'] == true),
        const SizedBox(height: 30),
        buildSubsectionHeader('🔌 MCP Server (N8N)'),
        _buildMcpSection(apiStatus['n8n_mcp'] == true),
      ],
    );
  }

  int _selectedSlot(String slotKey) {
    final fromWidget = widget.apiKeys[slotKey]?.toString();
    final parsed = int.tryParse(fromWidget ?? '');
    if (parsed == null || parsed < 1 || parsed > _maxSlots) {
      return 1;
    }
    return parsed;
  }

  String _slotKey(String baseKey, int slot) {
    if (slot <= 1) {
      return baseKey;
    }
    return '${baseKey}_$slot';
  }

  String _fieldKey(String key) => '${key}_field';

  String _apiKeyValue(SettingsProvider settings, String key) {
    final fromWidget = widget.apiKeys[key];
    if (fromWidget is String && fromWidget.isNotEmpty) {
      return fromWidget;
    }
    return settings.localApiKeys[key] ?? '';
  }

  Widget _buildSlotSelector({
    required String slotKey,
    required int activeSlot,
    String label = 'Active slot',
  }) {
    final slots = List<String>.generate(_maxSlots, (index) => '${index + 1}');
    return _buildDropdown(
      label,
      '$activeSlot',
      slots,
      (value) {
        if (value == null) {
          return;
        }
        widget.onApiKeyChanged(slotKey, value);
      },
      slotStyle: true,
    );
  }

  Widget _buildSlotAwareProviderInput(String label, String provider, bool isConfigured) {
    final settings = context.watch<SettingsProvider>();
    final slotKey = '${provider}_active_key_slot';
    final activeSlot = _selectedSlot(slotKey);
    final keyName = _slotKey(provider, activeSlot);
    final isVisible = widget.showApiKey[keyName] ?? false;
    final value = _apiKeyValue(settings, keyName);
    final maskedValue = settings.maskedApiKeys[keyName] ?? settings.maskedApiKeys[provider] ?? '';

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w500),
                ),
              ),
              buildStatusBadge(isConfigured),
            ],
          ),
          const SizedBox(height: 8),
          _buildSlotSelector(slotKey: slotKey, activeSlot: activeSlot, label: 'Active key slot'),
          const SizedBox(height: 8),
          TextFormField(
            key: Key(_fieldKey(keyName)),
            initialValue: value,
            obscureText: !isVisible,
            onChanged: (val) => widget.onApiKeyChanged(keyName, val),
            style: const TextStyle(color: Colors.white, fontSize: 14),
            decoration: InputDecoration(
              hintText: maskedValue.isNotEmpty ? maskedValue : 'Enter $label API Key',
              hintStyle: TextStyle(
                color: maskedValue.isNotEmpty ? ZoyaTheme.success.withValues(alpha: 0.6) : Colors.white24,
                fontFamily: 'monospace',
              ),
              filled: true,
              fillColor: Colors.white.withValues(alpha: 0.05),
              suffixIcon: IconButton(
                icon: Icon(
                  isVisible ? Icons.visibility_off : Icons.visibility,
                  color: Colors.white30,
                  size: 20,
                ),
                onPressed: () => widget.onVisibilityChanged(keyName, !isVisible),
              ),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLiveKitSection(bool isConfigured) {
    final settings = context.watch<SettingsProvider>();
    final maskedKeys = settings.maskedApiKeys;
    final activeSlot = _selectedSlot('livekit_active_slot');
    final urlKey = _slotKey('livekit_url', activeSlot);
    final apiKeyName = _slotKey('livekit_api_key', activeSlot);
    final secretKeyName = _slotKey('livekit_api_secret', activeSlot);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ZoyaTheme.accent.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: ZoyaTheme.accent.withValues(alpha: 0.15)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Row(
                  children: [
                    Icon(Icons.radio_button_checked, color: ZoyaTheme.accent, size: 18),
                    const SizedBox(width: 10),
                    const Flexible(child: Text('LiveKit Cloud', style: TextStyle(fontWeight: FontWeight.w600))),
                  ],
                ),
              ),
              buildStatusBadge(isConfigured),
            ],
          ),
          const SizedBox(height: 16),
          _buildSlotSelector(slotKey: 'livekit_active_slot', activeSlot: activeSlot),
          const SizedBox(height: 12),
          _buildTextField(
            'LiveKit URL',
            keyName: urlKey,
            value: _apiKeyValue(settings, urlKey),
            hint: maskedKeys[urlKey] ?? maskedKeys['livekit_url'] ?? '',
            onChanged: (val) => widget.onApiKeyChanged(urlKey, val),
          ),
          const SizedBox(height: 12),
          _buildSecureTextField(
            'API Key',
            keyName: apiKeyName,
            value: _apiKeyValue(settings, apiKeyName),
            hint: maskedKeys[apiKeyName] ?? maskedKeys['livekit_api_key'] ?? '',
          ),
          const SizedBox(height: 12),
          _buildSecureTextField(
            'API Secret',
            keyName: secretKeyName,
            value: _apiKeyValue(settings, secretKeyName),
            hint: maskedKeys[secretKeyName] ?? maskedKeys['livekit_api_secret'] ?? '',
          ),
          const SizedBox(height: 12),
          Text(
            '💡 Get your LiveKit credentials from cloud.livekit.io',
            style: TextStyle(color: ZoyaTheme.accent.withValues(alpha: 0.7), fontSize: 11),
          ),
        ],
      ),
    );
  }

  Widget _buildAwsCredentialsSection(bool isConfigured) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.orange.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.orange.withValues(alpha: 0.15)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Row(
                  children: [
                    const FaIcon(FontAwesomeIcons.aws, color: Colors.orange, size: 18),
                    const SizedBox(width: 10),
                    const Flexible(child: Text('AWS Credentials', style: TextStyle(fontWeight: FontWeight.w600))),
                  ],
                ),
              ),
              buildStatusBadge(isConfigured),
            ],
          ),
          const SizedBox(height: 16),
          _buildSecureTextField(
            'Access Key ID',
            keyName: 'aws_access_key',
            value: widget.awsAccessKey,
            hint: '',
            onChanged: widget.onAwsAccessKeyChanged,
          ),
          const SizedBox(height: 12),
          _buildSecureTextField(
            'Secret Access Key',
            keyName: 'aws_secret_key',
            value: widget.awsSecretKey,
            hint: '',
            onChanged: widget.onAwsSecretKeyChanged,
          ),
          const SizedBox(height: 12),
          _buildDropdown(
            'AWS Region',
            widget.awsRegion,
            ProviderConfig.awsRegions.map((r) => r['id'].toString()).toList(),
            widget.onAwsRegionChanged,
          ),
          const SizedBox(height: 12),
          Text(
            '💡 Create IAM credentials in the AWS Console with polly:SynthesizeSpeech permissions.',
            style: TextStyle(color: Colors.orange.withValues(alpha: 0.7), fontSize: 11),
          ),
        ],
      ),
    );
  }

  Widget _buildMcpSection(bool isConfigured) {
    final settings = context.watch<SettingsProvider>();
    final keyName = 'n8n_mcp_url';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.orange.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.orange.withValues(alpha: 0.15)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Row(
                  children: [
                    Icon(Icons.hub, color: Colors.orange, size: 18),
                    const SizedBox(width: 10),
                    const Flexible(child: Text('N8N MCP Server', style: TextStyle(fontWeight: FontWeight.w600))),
                  ],
                ),
              ),
              buildStatusBadge(isConfigured),
            ],
          ),
          const SizedBox(height: 16),
          _buildTextField(
            'MCP Server URL',
            keyName: keyName,
            value: _apiKeyValue(settings, keyName),
            hint: settings.maskedApiKeys[keyName] ?? '',
            onChanged: (val) => widget.onApiKeyChanged(keyName, val),
          ),
          const SizedBox(height: 12),
          Text(
            '💡 Connect your N8N instance for workflow automation tools (Spotify, Home Automation, etc.)',
            style: TextStyle(color: Colors.orange.withValues(alpha: 0.7), fontSize: 11),
          ),
        ],
      ),
    );
  }

  Widget _buildTextField(
    String label, {
    required String keyName,
    required String value,
    required String hint,
    required ValueChanged<String> onChanged,
  }) {
    return TextFormField(
      key: Key(_fieldKey(keyName)),
      initialValue: value,
      onChanged: onChanged,
      style: const TextStyle(color: Colors.white, fontSize: 14),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        hintStyle: const TextStyle(color: Colors.white24),
        labelStyle: const TextStyle(color: Colors.white70),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.05),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.white12),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.white12),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: ZoyaTheme.accent),
        ),
      ),
    );
  }

  Widget _buildSecureTextField(
    String label, {
    required String keyName,
    required String value,
    required String hint,
    ValueChanged<String>? onChanged,
  }) {
    final isVisible = widget.showApiKey[keyName] ?? false;
    return TextFormField(
      key: Key(_fieldKey(keyName)),
      initialValue: value,
      obscureText: !isVisible,
      onChanged: (val) {
        if (onChanged != null) {
          onChanged(val);
          return;
        }
        widget.onApiKeyChanged(keyName, val);
      },
      style: const TextStyle(color: Colors.white, fontSize: 14),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        hintStyle: const TextStyle(color: Colors.white24, fontFamily: 'monospace'),
        labelStyle: const TextStyle(color: Colors.white70),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.05),
        suffixIcon: IconButton(
          icon: Icon(isVisible ? Icons.visibility_off : Icons.visibility, color: Colors.white30, size: 18),
          onPressed: () => widget.onVisibilityChanged(keyName, !isVisible),
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.white12),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.white12),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: ZoyaTheme.accent),
        ),
      ),
    );
  }

  Widget _buildDropdown(
    String label,
    String value,
    List<String> items,
    ValueChanged<String?> onChanged, {
    bool slotStyle = false,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12)),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white12),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: value,
              isExpanded: true,
              dropdownColor: Colors.grey[900],
              style: const TextStyle(color: Colors.white),
              items: items
                  .map(
                    (item) => DropdownMenuItem(
                      value: item,
                      child: Text(slotStyle ? 'Slot $item' : item),
                    ),
                  )
                  .toList(),
              onChanged: onChanged,
            ),
          ),
        ),
      ],
    );
  }
}
