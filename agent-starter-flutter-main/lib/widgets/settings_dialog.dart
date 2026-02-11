import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../ui/zoya_theme.dart';
import '../state/providers/settings_provider.dart';
import 'glass_container.dart';
import 'settings/general_panel.dart';
import 'settings/ai_providers_panel.dart';
import 'settings/voice_audio_panel.dart';
import 'settings/api_keys_panel.dart';
import 'settings/memory_panel.dart';
import 'settings/personalization_panel.dart';
import 'settings/account_panel.dart';

class SettingsDialog extends StatefulWidget {
  const SettingsDialog({super.key});

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  String _activePanel = 'general';
  
  // Local form state
  late String _userName;
  late String _llmProvider;
  late String _llmModel;
  late double _llmTemperature;
  late String _sttProvider;
  late String _sttModel;
  late String _sttLanguage;
  late String _ttsProvider;
  late String _ttsVoice;
  late bool _mem0Enabled;
  late String _interfaceTheme;
  late String _mem0ApiKey;
  late String _preferredLanguage;
  late String _assistantPersonality;
  late bool _quantumParticlesEnabled;
  late bool _orbitalGlowEnabled;
  late bool _soundEffectsEnabled;
  
  // API Keys state
  final Map<String, String> _apiKeys = {};
  final Map<String, bool> _showApiKey = {};
  
  // AWS Polly specific
  String _awsAccessKey = '';
  String _awsSecretKey = '';
  String _awsRegion = 'us-east-1';

  @override
  void initState() {
    super.initState();
    final settings = context.read<SettingsProvider>();
    _userName = settings.userName;
    _llmProvider = settings.llmProvider;
    _llmModel = settings.llmModel;
    _llmTemperature = settings.llmTemperature;
    _sttProvider = settings.sttProvider;
    _sttModel = settings.sttModel;
    _sttLanguage = settings.sttLanguage;
    _ttsProvider = settings.ttsProvider;
    _ttsVoice = settings.ttsVoice;
    _mem0Enabled = settings.mem0Enabled;
    _interfaceTheme = settings.interfaceTheme;
    _mem0ApiKey = settings.mem0ApiKey;
    _preferredLanguage = settings.preferredLanguage;
    _assistantPersonality = settings.assistantPersonality;
    _quantumParticlesEnabled = settings.quantumParticlesEnabled;
    _orbitalGlowEnabled = settings.orbitalGlowEnabled;
    _soundEffectsEnabled = settings.soundEffectsEnabled;
    _awsAccessKey = settings.awsAccessKey;
    _awsSecretKey = settings.awsSecretKey;
    _awsRegion = settings.awsRegion;
    
    // Fetch fresh API key status when dialog opens
    WidgetsBinding.instance.addPostFrameCallback((_) {
      settings.fetchApiKeyStatus();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 40),
      child: GlassContainer(
        width: 1100,
        height: 750,
        borderRadius: BorderRadius.circular(24),
        child: Row(
          children: [
            // Sidebar
            _buildSidebar(),
            // Main Content
            Expanded(
              child: _buildContent(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSidebar() {
    return Container(
      width: 240,
      decoration: BoxDecoration(
        border: Border(right: BorderSide(color: ZoyaTheme.accent.withValues(alpha: 0.1))),
        color: Colors.black.withValues(alpha: 0.2),
      ),
      child: Column(
        children: [
          const SizedBox(height: 40),
          _NavItem(
            icon: Icons.settings,
            label: 'General',
            isActive: _activePanel == 'general',
            onTap: () => setState(() => _activePanel = 'general'),
          ),
          _NavItem(
            icon: Icons.psychology,
            label: 'AI Providers',
            isActive: _activePanel == 'ai-providers',
            onTap: () => setState(() => _activePanel = 'ai-providers'),
          ),
          _NavItem(
            icon: Icons.graphic_eq,
            label: 'Voice & Audio',
            isActive: _activePanel == 'voice-audio',
            onTap: () => setState(() => _activePanel = 'voice-audio'),
          ),
           _NavItem(
            icon: Icons.key,
            label: 'API Keys',
            isActive: _activePanel == 'api-keys',
            onTap: () => setState(() => _activePanel = 'api-keys'),
          ),
          _NavItem(
            icon: Icons.storage,
            label: 'Memory',
            isActive: _activePanel == 'memory',
            onTap: () => setState(() => _activePanel = 'memory'),
          ),
          _NavItem(
            icon: Icons.person,
            label: 'Personalization',
            isActive: _activePanel == 'personalization',
            onTap: () => setState(() => _activePanel = 'personalization'),
          ),
          const Spacer(),
          _NavItem(
            icon: Icons.account_circle,
            label: 'Account',
            isActive: _activePanel == 'account',
            onTap: () => setState(() => _activePanel = 'account'),
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Widget _buildContent() {
    return Padding(
      padding: const EdgeInsets.all(40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                _activePanel.replaceAll('-', ' ').toUpperCase(),
                style: ZoyaTheme.fontDisplay.copyWith(
                  fontSize: 24,
                  color: ZoyaTheme.accent,
                  letterSpacing: 2,
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(context),
              ),
            ],
          ),
          const SizedBox(height: 30),
          Expanded(
            child: SingleChildScrollView(
              child: _buildActivePanel(),
            ),
          ),
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Cancel'),
              ),
              const SizedBox(width: 20),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: ZoyaTheme.accent,
                  foregroundColor: Colors.black,
                  padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 15),
                ),
                onPressed: _handleSave,
                child: const Text('SAVE SETTINGS'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildActivePanel() {
    switch (_activePanel) {
      case 'general':
        return GeneralPanel(
          interfaceTheme: _interfaceTheme,
          quantumParticlesEnabled: _quantumParticlesEnabled,
          orbitalGlowEnabled: _orbitalGlowEnabled,
          soundEffectsEnabled: _soundEffectsEnabled,
          onThemeChanged: (val) => setState(() => _interfaceTheme = val),
          onParticlesChanged: (val) => setState(() => _quantumParticlesEnabled = val),
          onGlowChanged: (val) => setState(() => _orbitalGlowEnabled = val),
          onSoundChanged: (val) => setState(() => _soundEffectsEnabled = val),
        );
      case 'ai-providers':
        return AIProvidersPanel(
          llmProvider: _llmProvider,
          llmModel: _llmModel,
          llmTemperature: _llmTemperature,
          onProviderChanged: (val) => setState(() => _llmProvider = val),
          onModelChanged: (val) => setState(() => _llmModel = val),
          onTemperatureChanged: (val) => setState(() => _llmTemperature = val),
        );
      case 'voice-audio':
        return VoiceAudioPanel(
          sttProvider: _sttProvider,
          sttModel: _sttModel,
          sttLanguage: _sttLanguage,
          ttsProvider: _ttsProvider,
          ttsVoice: _ttsVoice,
          awsRegion: _awsRegion,
          onSttProviderChanged: (val) => setState(() => _sttProvider = val),
          onSttModelChanged: (val) => setState(() => _sttModel = val),
          onSttLanguageChanged: (val) => setState(() => _sttLanguage = val),
          onTtsProviderChanged: (val) => setState(() => _ttsProvider = val),
          onTtsVoiceChanged: (val) => setState(() => _ttsVoice = val),
          onAwsRegionChanged: (val) => setState(() => _awsRegion = val),
        );
      case 'api-keys':
        return ApiKeysPanel(
          apiKeys: _apiKeys,
          showApiKey: _showApiKey,
          awsAccessKey: _awsAccessKey,
          awsSecretKey: _awsSecretKey,
          awsRegion: _awsRegion,
          onApiKeyChanged: (p, val) => _apiKeys[p] = val,
          onVisibilityChanged: (p, val) => setState(() => _showApiKey[p] = val),
          onAwsAccessKeyChanged: (val) => setState(() => _awsAccessKey = val),
          onAwsSecretKeyChanged: (val) => setState(() => _awsSecretKey = val),
          onAwsRegionChanged: (val) => setState(() => _awsRegion = val ?? 'us-east-1'),
        );
      case 'memory':
        return MemoryPanel(
          mem0Enabled: _mem0Enabled,
          mem0ApiKey: _mem0ApiKey,
          onEnabledChanged: (val) => setState(() => _mem0Enabled = val),
          onApiKeyChanged: (val) => setState(() => _mem0ApiKey = val),
        );
      case 'personalization':
        return PersonalizationPanel(
          userName: _userName,
          preferredLanguage: _preferredLanguage,
          assistantPersonality: _assistantPersonality,
          onNameChanged: (val) => setState(() => _userName = val),
          onLanguageChanged: (val) => setState(() => _preferredLanguage = val),
          onPersonalityChanged: (val) => setState(() => _assistantPersonality = val),
        );
      case 'account':
        return const AccountPanel();
      default:
        return const SizedBox.shrink();
    }
  }

  Widget _buildSecureTextField(
    String label,
    String placeholder,
    String value,
    String keyId,
    ValueChanged<String> onChanged,
  ) {
    final isConfigured = placeholder.isNotEmpty && placeholder != 'APIxxxxxxx' && placeholder != 'Your API Secret' && placeholder != 'eyJhbGciOiJIUzI1NiI...';
    
    return TextField(
      controller: TextEditingController(text: value),
      obscureText: !(_showApiKey[keyId] ?? false),
      onChanged: onChanged,
      style: const TextStyle(color: Colors.white),
      decoration: InputDecoration(
        labelText: label,
        hintText: placeholder,
        labelStyle: const TextStyle(color: Colors.white70),
        hintStyle: TextStyle(
          color: isConfigured ? ZoyaTheme.success.withValues(alpha: 0.6) : Colors.white30,
          fontFamily: isConfigured ? 'monospace' : null,
        ),
        suffixIcon: IconButton(
          icon: Icon(
            (_showApiKey[keyId] ?? false) ? Icons.visibility_off : Icons.visibility,
            color: Colors.white54,
          ),
          onPressed: () {
            setState(() {
              _showApiKey[keyId] = !(_showApiKey[keyId] ?? false);
            });
          },
        ),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.05),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.white12),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: isConfigured ? ZoyaTheme.success.withValues(alpha: 0.3) : Colors.white12),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: ZoyaTheme.accent),
        ),
      ),
    );
  }

  Widget _buildStatusBadge(bool isConfigured) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: (isConfigured ? Colors.green : Colors.orange).withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        isConfigured ? '✓ Configured' : '⚠️ Required',
        style: TextStyle(
          color: isConfigured ? Colors.green : Colors.orange,
          fontSize: 10,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Future<void> _handleSave() async {
    final settings = context.read<SettingsProvider>();
    
    // Prepare API keys map (only include non-empty keys)
    final apiKeysToSave = Map<String, String>.from(_apiKeys)
      ..removeWhere((key, value) => value.toString().trim().isEmpty);
    
    final success = await settings.updatePreferences({
      'userName': _userName,
      'llmProvider': _llmProvider,
      'llmModel': _llmModel,
      'llmTemperature': _llmTemperature,
      'sttProvider': _sttProvider,
      'sttModel': _sttModel,
      'sttLanguage': _sttLanguage,
      'ttsProvider': _ttsProvider,
      'ttsVoice': _ttsVoice,
      'mem0Enabled': _mem0Enabled,
      'interfaceTheme': _interfaceTheme,
      'mem0ApiKey': _mem0ApiKey,
      'preferredLanguage': _preferredLanguage,
      'assistantPersonality': _assistantPersonality,
      'quantumParticlesEnabled': _quantumParticlesEnabled,
      'orbitalGlowEnabled': _orbitalGlowEnabled,
      'soundEffectsEnabled': _soundEffectsEnabled,
      'apiKeys': apiKeysToSave,
      'awsAccessKey': _awsAccessKey,
      'awsSecretKey': _awsSecretKey,
      'awsRegion': _awsRegion,
    });

    if (success && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('✅ Settings saved successfully & synced to cloud!'),
          backgroundColor: ZoyaTheme.success,
        ),
      );
      Navigator.pop(context);
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('❌ Failed to save settings'),
          backgroundColor: ZoyaTheme.danger,
        ),
      );
    }
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;
  final VoidCallback onTap;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.isActive,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        decoration: BoxDecoration(
          border: Border(left: BorderSide(color: isActive ? ZoyaTheme.accent : Colors.transparent, width: 4)),
        ),
        child: Row(
          children: [
            Icon(icon, color: isActive ? ZoyaTheme.accent : ZoyaTheme.textMuted, size: 20),
            const SizedBox(width: 16),
            Text(
              label,
              style: TextStyle(
                color: isActive ? ZoyaTheme.accent : Colors.white60,
                fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MiniBar extends StatelessWidget {
  final double height;
  const _MiniBar({required this.height});
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 4,
      height: height,
      margin: const EdgeInsets.symmetric(horizontal: 1.5),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(2),
      ),
    );
  }
}
