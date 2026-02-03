import 'package:flutter/material.dart';
import '../../core/config/provider_config.dart';
import '../../state/providers/settings_provider.dart';
import '../shared_widgets.dart';
import '../../ui/zoya_theme.dart';
import 'package:provider/provider.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class ApiKeysPanel extends StatefulWidget {
  final Map<String, dynamic> apiKeys;
  final Map<String, bool> showApiKey;
  final String awsAccessKey;
  final String awsSecretKey;
  final String awsRegion;
  final Function(String, String) onApiKeyChanged;
  final Function(String, bool) onVisibilityChanged;
  final Function(String) onAwsAccessKeyChanged;
  final Function(String) onAwsSecretKeyChanged;
  final Function(String?) onAwsRegionChanged;

  const ApiKeysPanel({
    super.key,
    required this.apiKeys,
    required this.showApiKey,
    required this.awsAccessKey,
    required this.awsSecretKey,
    required this.awsRegion,
    required this.onApiKeyChanged,
    required this.onVisibilityChanged,
    required this.onAwsAccessKeyChanged,
    required this.onAwsSecretKeyChanged,
    required this.onAwsRegionChanged,
  });

  @override
  State<ApiKeysPanel> createState() => _ApiKeysPanelState();
}

class _ApiKeysPanelState extends State<ApiKeysPanel> {
  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();
    final apiStatus = settings.apiKeyStatus;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader(
          '🔑 API Keys',
          'Manage your API keys for different providers. Keys are stored securely.',
        ),
        const SizedBox(height: 20),
        
        buildSubsectionHeader('📡 LiveKit Configuration'),
        _buildLiveKitSection(apiStatus['livekit'] == true),
        
        const SizedBox(height: 30),
        
        buildSubsectionHeader('🤖 LLM Providers'),
        ...[
          'groq', 'openai', 'gemini', 'anthropic', 'deepseek', 'mistral', 'perplexity', 'together'
        ].map((provider) => _buildSecureApiKeyInput(
          ProviderConfig.getProviderName(provider, 'llm'),
          provider,
          apiStatus[provider] == true,
        )),
        
        const SizedBox(height: 30),
        
        buildSubsectionHeader('🎤 Speech Providers'),
        ...[
          'deepgram', 'assemblyai', 'cartesia', 'elevenlabs'
        ].map((provider) => _buildSecureApiKeyInput(
          ProviderConfig.getProviderName(provider, provider.contains('deep') || provider.contains('assembly') ? 'stt' : 'tts'),
          provider,
          apiStatus[provider] == true,
        )),
        
        const SizedBox(height: 30),
        
        buildSubsectionHeader('☁️ AWS Polly'),
        _buildAwsCredentialsSection(apiStatus['aws'] == true),
        
        const SizedBox(height: 30),
        
        buildSubsectionHeader('🔌 MCP Server (N8N)'),
        _buildMcpSection(apiStatus['n8n_mcp'] == true),
      ],
    );
  }

  Widget _buildSecureApiKeyInput(String label, String provider, bool isConfigured) {
    final settings = context.watch<SettingsProvider>();
    final isVisible = widget.showApiKey[provider] ?? false;
    final maskedValue = settings.maskedApiKeys[provider] ?? '';
    
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: const TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w500)),
              buildStatusBadge(isConfigured),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            obscureText: !isVisible,
            onChanged: (val) => widget.onApiKeyChanged(provider, val),
            style: const TextStyle(color: Colors.white, fontSize: 14),
            decoration: InputDecoration(
              hintText: maskedValue.isNotEmpty ? maskedValue : 'Enter $label API Key',
              hintStyle: TextStyle(
                color: maskedValue.isNotEmpty ? ZoyaTheme.success.withValues(alpha: 0.6) : Colors.white24,
                fontFamily: 'monospace'
              ),
              filled: true,
              fillColor: Colors.white.withValues(alpha: 0.05),
              suffixIcon: IconButton(
                icon: Icon(isVisible ? Icons.visibility_off : Icons.visibility, color: Colors.white30, size: 20),
                onPressed: () => widget.onVisibilityChanged(provider, !isVisible),
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
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(Icons.radio_button_checked, color: ZoyaTheme.accent, size: 18),
                  const SizedBox(width: 10),
                  const Text('LiveKit Cloud', style: TextStyle(fontWeight: FontWeight.w600)),
                ],
              ),
              buildStatusBadge(isConfigured),
            ],
          ),
          const SizedBox(height: 16),
          _buildTextField('LiveKit URL', maskedKeys['livekit_url'] ?? '', (val) => widget.onApiKeyChanged('livekit_url', val)),
          const SizedBox(height: 12),
          _buildSecureTextField('API Key', maskedKeys['livekit_api_key'] ?? '', 'livekit_api_key'),
          const SizedBox(height: 12),
          _buildSecureTextField('API Secret', maskedKeys['livekit_api_secret'] ?? '', 'livekit_api_secret'),
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
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  const FaIcon(FontAwesomeIcons.aws, color: Colors.orange, size: 18),
                  const SizedBox(width: 10),
                  const Text('AWS Credentials', style: TextStyle(fontWeight: FontWeight.w600)),
                ],
              ),
              buildStatusBadge(isConfigured),
            ],
          ),
          const SizedBox(height: 16),
          _buildSecureTextField('Access Key ID', widget.awsAccessKey, 'aws_access_key', onChanged: widget.onAwsAccessKeyChanged),
          const SizedBox(height: 12),
          _buildSecureTextField('Secret Access Key', widget.awsSecretKey, 'aws_secret_key', onChanged: widget.onAwsSecretKeyChanged),
          const SizedBox(height: 12),
          _buildDropdown('AWS Region', widget.awsRegion, ProviderConfig.awsRegions.map((r) => r['id'].toString()).toList(), widget.onAwsRegionChanged),
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
    final maskedKeys = settings.maskedApiKeys;
    
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
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(Icons.hub, color: Colors.orange, size: 18),
                  const SizedBox(width: 10),
                  const Text('N8N MCP Server', style: TextStyle(fontWeight: FontWeight.w600)),
                ],
              ),
              buildStatusBadge(isConfigured),
            ],
          ),
          const SizedBox(height: 16),
          _buildTextField('MCP Server URL', maskedKeys['n8n_mcp_url'] ?? '', (val) => widget.onApiKeyChanged('n8n_mcp_url', val)),
          const SizedBox(height: 12),
          Text(
            '💡 Connect your N8N instance for workflow automation tools (Spotify, Home Automation, etc.)',
            style: TextStyle(color: Colors.orange.withValues(alpha: 0.7), fontSize: 11),
          ),
        ],
      ),
    );
  }

  Widget _buildTextField(String label, String hint, ValueChanged<String> onChanged) {
    return TextField(
      onChanged: onChanged,
      style: const TextStyle(color: Colors.white, fontSize: 14),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        hintStyle: const TextStyle(color: Colors.white24),
        labelStyle: const TextStyle(color: Colors.white70),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.05),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Colors.white12)),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Colors.white12)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: ZoyaTheme.accent)),
      ),
    );
  }

  Widget _buildSecureTextField(String label, String hint, String provider, {ValueChanged<String>? onChanged}) {
    final isVisible = widget.showApiKey[provider] ?? false;
    return TextField(
      obscureText: !isVisible,
      onChanged: (val) {
        if (onChanged != null) {
          onChanged(val);
        } else {
          widget.onApiKeyChanged(provider, val);
        }
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
          onPressed: () => widget.onVisibilityChanged(provider, !isVisible),
        ),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Colors.white12)),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Colors.white12)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: ZoyaTheme.accent)),
      ),
    );
  }

  Widget _buildDropdown(String label, String value, List<String> items, ValueChanged<String?> onChanged) {
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
              items: items.map((item) => DropdownMenuItem(value: item, child: Text(item))).toList(),
              onChanged: onChanged,
            ),
          ),
        ),
      ],
    );
  }
}
