import 'package:flutter/material.dart';
import '../../core/config/provider_config.dart';
import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';

class VoiceInteractionPanel extends StatelessWidget {
  final String sttProvider;
  final String sttModel;
  final String sttLanguage;
  final String ttsProvider;
  final String ttsVoice;
  final String interactionMode;
  final Function(String) onSttProviderChanged;
  final Function(String) onSttModelChanged;
  final Function(String) onSttLanguageChanged;
  final Function(String) onTtsProviderChanged;
  final Function(String) onTtsVoiceChanged;
  final Function(String) onInteractionModeChanged;

  const VoiceInteractionPanel({
    super.key,
    required this.sttProvider,
    required this.sttModel,
    required this.sttLanguage,
    required this.ttsProvider,
    required this.ttsVoice,
    required this.interactionMode,
    required this.onSttProviderChanged,
    required this.onSttModelChanged,
    required this.onSttLanguageChanged,
    required this.onTtsProviderChanged,
    required this.onTtsVoiceChanged,
    required this.onInteractionModeChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('🎙️ Interaction', 'Choose how you want to communicate with Maya.'),
        const SizedBox(height: 24),

        // Interaction Mode
        _buildInteractionModeSelector(),
        const SizedBox(height: 40),

        buildSubsectionHeader('🗣️ Speech-to-Text (Input)'),
        _buildDropdown(
          'STT Provider',
          sttProvider,
          ProviderConfig.sttProviders,
          (value) => value != null ? onSttProviderChanged(value) : null,
        ),
        const SizedBox(height: 20),
        _buildSimpleDropdown(
          'STT Model',
          sttModel,
          ProviderConfig.getModelsForProvider(sttProvider, 'stt'),
          (value) => value != null ? onSttModelChanged(value) : null,
        ),
        const SizedBox(height: 20),
        _buildDropdownFromMaps(
          'STT Language',
          sttLanguage,
          ProviderConfig.preferredLanguages,
          (value) => value != null ? onSttLanguageChanged(value) : null,
        ),
        const SizedBox(height: 40),

        buildSubsectionHeader('🔊 Text-to-Speech (Output)'),
        _buildDropdown(
          'TTS Provider',
          ttsProvider,
          ProviderConfig.ttsProviders,
          (value) => value != null ? onTtsProviderChanged(value) : null,
        ),
        const SizedBox(height: 20),
        _buildSimpleDropdown(
          'Voice Personality',
          ttsVoice,
          ProviderConfig.getVoicesForProvider(ttsProvider),
          (value) => value != null ? onTtsVoiceChanged(value) : null,
        ),
      ],
    );
  }

  Widget _buildInteractionModeSelector() {
    return Row(
      children: [
        _buildModeButton('VOICE', 'voice', Icons.mic_none_outlined),
        const SizedBox(width: 12),
        _buildModeButton('TEXT', 'text', Icons.keyboard_outlined),
        const SizedBox(width: 12),
        _buildModeButton('AUTO', 'auto', Icons.hdr_auto_outlined),
      ],
    );
  }

  Widget _buildModeButton(String label, String value, IconData icon) {
    final isActive = interactionMode == value;
    return Expanded(
      child: InkWell(
        onTap: () => onInteractionModeChanged(value),
        borderRadius: BorderRadius.circular(12),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 16),
          decoration: BoxDecoration(
            color: isActive ? ZoyaTheme.accent.withValues(alpha: 0.1) : Colors.white.withValues(alpha: 0.03),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isActive ? ZoyaTheme.accent : Colors.white12,
              width: 1.5,
            ),
            boxShadow: isActive ? [BoxShadow(color: ZoyaTheme.accentGlow, blurRadius: 8)] : [],
          ),
          child: Column(
            children: [
              Icon(icon, color: isActive ? ZoyaTheme.accent : Colors.white54, size: 24),
              const SizedBox(height: 8),
              Text(
                label,
                style: ZoyaTheme.fontDisplay.copyWith(
                  fontSize: 10,
                  color: isActive ? ZoyaTheme.accent : Colors.white54,
                  letterSpacing: 1,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDropdown(
    String label,
    String value,
    List<Map<String, dynamic>> items,
    ValueChanged<String?> onChanged,
  ) {
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
              value: items.any((i) => i['id'] == value) ? value : null,
              isExpanded: true,
              dropdownColor: ZoyaTheme.sidebarBg,
              icon: Icon(Icons.keyboard_arrow_down, color: ZoyaTheme.accent),
              style: const TextStyle(color: Colors.white, fontSize: 14),
              items: items.map((item) {
                return DropdownMenuItem(
                  value: item['id'] as String,
                  child: Text(item['name'] as String? ?? item['id'] as String),
                );
              }).toList(),
              onChanged: onChanged,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDropdownFromMaps(
    String label,
    String value,
    List<Map<String, String>> items,
    ValueChanged<String?> onChanged,
  ) {
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
              value: items.any((i) => i['id'] == value) ? value : null,
              isExpanded: true,
              dropdownColor: ZoyaTheme.sidebarBg,
              icon: Icon(Icons.keyboard_arrow_down, color: ZoyaTheme.accent),
              style: const TextStyle(color: Colors.white, fontSize: 14),
              items: items.map((item) {
                return DropdownMenuItem(
                  value: item['id']!,
                  child: Text(item['name'] ?? item['id']!),
                );
              }).toList(),
              onChanged: onChanged,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSimpleDropdown(
    String label,
    String value,
    List<String> items,
    ValueChanged<String?> onChanged,
  ) {
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
              value: items.contains(value) ? value : (items.isNotEmpty ? items.first : null),
              isExpanded: true,
              dropdownColor: ZoyaTheme.sidebarBg,
              icon: Icon(Icons.keyboard_arrow_down, color: ZoyaTheme.accent),
              style: const TextStyle(color: Colors.white, fontSize: 14),
              items: items.map((item) {
                return DropdownMenuItem(
                  value: item,
                  child: Text(item),
                );
              }).toList(),
              onChanged: onChanged,
            ),
          ),
        ),
      ],
    );
  }
}
