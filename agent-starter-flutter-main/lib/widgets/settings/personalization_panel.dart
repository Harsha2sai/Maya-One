import 'package:flutter/material.dart';
import '../../core/config/provider_config.dart';
import '../shared_widgets.dart';
import '../../ui/zoya_theme.dart';

class PersonalizationPanel extends StatelessWidget {
  final String userName;
  final String preferredLanguage;
  final String assistantPersonality;
  final Function(String) onNameChanged;
  final Function(String) onLanguageChanged;
  final Function(String) onPersonalityChanged;

  const PersonalizationPanel({
    super.key,
    required this.userName,
    required this.preferredLanguage,
    required this.assistantPersonality,
    required this.onNameChanged,
    required this.onLanguageChanged,
    required this.onPersonalityChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('👤 User Profile', 'Tell the assistant about yourself for a better experience.'),
        const SizedBox(height: 20),
        _buildTextField('Your Name', userName, onNameChanged),
        const SizedBox(height: 24),
        _buildLanguageDropdown(
          'Preferred Language',
          preferredLanguage,
          ProviderConfig.preferredLanguages,
          (val) { if (val != null) onLanguageChanged(val); },
        ),
        const SizedBox(height: 40),
        buildSectionHeader('🗣️ Interaction Style', 'Customize how the assistant communicates.'),
        const SizedBox(height: 20),
        _buildDropdown(
          'Assistant Personality',
          assistantPersonality,
          ProviderConfig.assistantPersonalities.map((p) => p['id']!).toList(),
          (val) { if (val != null) onPersonalityChanged(val); },
        ),
      ],
    );
  }

  Widget _buildTextField(String label, String value, ValueChanged<String> onChanged) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12)),
        const SizedBox(height: 8),
        TextField(
          onChanged: onChanged,
          controller: TextEditingController(text: value)..selection = TextSelection.fromPosition(TextPosition(offset: value.length)),
          style: const TextStyle(color: Colors.white, fontSize: 14),
          decoration: InputDecoration(
            filled: true,
            fillColor: Colors.white.withValues(alpha: 0.05),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Colors.white12)),
            enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Colors.white12)),
            focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: ZoyaTheme.accent)),
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
              items: items.map((item) {
                final personality = ProviderConfig.assistantPersonalities.firstWhere((p) => p['id'] == item);
                return DropdownMenuItem(
                  value: item,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(personality['name']!),
                      Text(personality['description']!, style: TextStyle(fontSize: 10, color: Colors.white.withValues(alpha: 0.4))),
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
