import 'package:flutter/material.dart';
import '../../core/config/provider_config.dart';
import '../../state/providers/settings_provider.dart';
import '../shared_widgets.dart';
import '../../ui/zoya_theme.dart';
import 'package:provider/provider.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class VoiceAudioPanel extends StatelessWidget {
  final String sttProvider;
  final String sttModel;
  final String sttLanguage;
  final String ttsProvider;
  final String ttsVoice;
  
  // AWS Polly Specific
  final String awsRegion;
  
  final Function(String) onSttProviderChanged;
  final Function(String) onSttModelChanged;
  final Function(String) onSttLanguageChanged;
  final Function(String) onTtsProviderChanged;
  final Function(String) onTtsVoiceChanged;
  final Function(String) onAwsRegionChanged;

  const VoiceAudioPanel({
    super.key,
    required this.sttProvider,
    required this.sttModel,
    required this.sttLanguage,
    required this.ttsProvider,
    required this.ttsVoice,
    required this.awsRegion,
    required this.onSttProviderChanged,
    required this.onSttModelChanged,
    required this.onSttLanguageChanged,
    required this.onTtsProviderChanged,
    required this.onTtsVoiceChanged,
    required this.onAwsRegionChanged,
  });

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('🎤 Speech-to-Text (STT)', 'Choose how your voice is transcribed.'),
        const SizedBox(height: 20),
        _buildProviderDropdown(
          'Provider',
          sttProvider,
          ProviderConfig.sttProviders,
          settings.apiKeyStatus,
          (val) {
            if (val != null) {
              onSttProviderChanged(val);
              final models = ProviderConfig.getModelsForProvider(val, 'stt');
              if (models.isNotEmpty) onSttModelChanged(models.first);
            }
          },
        ),
        const SizedBox(height: 24),
        _buildDropdown(
          'Model',
          sttModel,
          ProviderConfig.getModelsForProvider(sttProvider, 'stt'),
          (val) { if (val != null) onSttModelChanged(val); },
        ),
        const SizedBox(height: 24),
        _buildLanguageDropdown(
          'Language',
          sttLanguage,
          ProviderConfig.sttLanguages,
          (val) { if (val != null) onSttLanguageChanged(val); },
        ),
        const SizedBox(height: 40),
        buildSectionHeader('🔊 Text-to-Speech (TTS)', 'Choose the voice for responses.'),
        const SizedBox(height: 20),
        _buildProviderDropdown(
          'Provider',
          ttsProvider,
          ProviderConfig.ttsProviders,
          settings.apiKeyStatus,
          (val) {
            if (val != null) {
              onTtsProviderChanged(val);
              final voices = ProviderConfig.getVoicesForProvider(val);
              if (voices.isNotEmpty) onTtsVoiceChanged(voices.first);
            }
          },
        ),
        const SizedBox(height: 24),
        if (ttsProvider == 'aws_polly') ...[
          _buildAwsPollyBanner(),
          const SizedBox(height: 24),
        ],
        _buildDropdown(
          'Voice',
          ttsVoice,
          ProviderConfig.getVoicesForProvider(ttsProvider),
          (val) { if (val != null) onTtsVoiceChanged(val); },
        ),
      ],
    );
  }

  Widget _buildAwsPollyBanner() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.orange.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.orange.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const FaIcon(FontAwesomeIcons.aws, color: Colors.orange, size: 20),
              const SizedBox(width: 10),
              Text(
                'AWS Credentials',
                style: ZoyaTheme.fontDisplay.copyWith(fontSize: 14, color: Colors.white),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Configure AWS access for Polly in the API Keys panel.',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 12),
          ),
        ],
      ),
    );
  }

  Widget _buildProviderDropdown(String label, String value, List<Map<String, dynamic>> items, Map<String, dynamic> status, ValueChanged<String?> onChanged) {
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
              items: items.map<DropdownMenuItem<String>>((item) {
                final id = item['id'].toString();
                final isConfigured = status[id] == true;
                return DropdownMenuItem<String>(
                  value: id,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(item['name'].toString()),
                      if (isConfigured)
                        const Icon(Icons.check_circle, color: ZoyaTheme.success, size: 14),
                    ],
                  ),
                );
              }).toList(),
              onChanged: onChanged,
            ),
          ),
        ),
      ],
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

  Widget _buildLanguageDropdown(String label, String value, List<Map<String, String>> items, ValueChanged<String?> onChanged) {
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
              items: items.map((item) => DropdownMenuItem(value: item['id']!, child: Text(item['name']!))).toList(),
              onChanged: onChanged,
            ),
          ),
        ),
      ],
    );
  }
}
