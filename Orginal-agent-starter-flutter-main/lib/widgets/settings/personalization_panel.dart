import 'package:flutter/material.dart';

import '../../core/config/provider_config.dart';
import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';

class PersonalizationPanel extends StatefulWidget {
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
  State<PersonalizationPanel> createState() => _PersonalizationPanelState();
}

class _PersonalizationPanelState extends State<PersonalizationPanel> {
  late final TextEditingController _nameController;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.userName);
  }

  @override
  void didUpdateWidget(covariant PersonalizationPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.userName != widget.userName && _nameController.text != widget.userName) {
      _nameController.value = TextEditingValue(
        text: widget.userName,
        selection: TextSelection.collapsed(offset: widget.userName.length),
      );
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final languageOptions = ProviderConfig.preferredLanguages.map((item) => item['id']!).toList();
    final personalityOptions = ProviderConfig.assistantPersonalities.map((item) => item['id']!).toList();
    final selectedLanguage = _normalizeSelection(
      widget.preferredLanguage,
      languageOptions,
      fallback: 'en-US',
    );
    final selectedPersonality = _normalizeSelection(
      widget.assistantPersonality,
      personalityOptions,
      fallback: 'professional',
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('👤 User Profile', 'Tell the assistant about yourself for a better experience.'),
        const SizedBox(height: 20),
        _buildTextField('Your Name', _nameController, widget.onNameChanged),
        const SizedBox(height: 24),
        _buildLanguageDropdown(
          'Preferred Language',
          selectedLanguage,
          ProviderConfig.preferredLanguages,
          (value) {
            if (value != null) {
              widget.onLanguageChanged(value);
            }
          },
        ),
        const SizedBox(height: 40),
        buildSectionHeader('🗣️ Interaction Style', 'Customize how the assistant communicates.'),
        const SizedBox(height: 20),
        _buildPersonalityDropdown(
          'Assistant Personality',
          selectedPersonality,
          ProviderConfig.assistantPersonalities,
          (value) {
            if (value != null) {
              widget.onPersonalityChanged(value);
            }
          },
        ),
      ],
    );
  }

  String _normalizeSelection(String value, List<String> options, {required String fallback}) {
    if (options.contains(value)) {
      return value;
    }
    if (options.contains(fallback)) {
      return fallback;
    }
    return options.first;
  }

  Widget _buildTextField(String label, TextEditingController controller, ValueChanged<String> onChanged) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(), style: const TextStyle(color: Colors.white54, fontSize: 10, letterSpacing: 1.5)),
        const SizedBox(height: 8),
        TextField(
          controller: controller,
          onChanged: onChanged,
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
              borderSide: BorderSide(color: ZoyaTheme.accent.withValues(alpha: 0.5)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPersonalityDropdown(
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
              value: value,
              isExpanded: true,
              dropdownColor: ZoyaTheme.sidebarBg,
              icon: Icon(Icons.keyboard_arrow_down, color: ZoyaTheme.accent),
              style: const TextStyle(color: Colors.white, fontSize: 14),
              items: items.map((item) {
                final title = item['name'] ?? item['id'] ?? 'Unknown';
                final description = item['description'];
                return DropdownMenuItem(
                  value: item['id']!,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(title),
                      if (description != null && description.isNotEmpty)
                        Text(
                          description,
                          style: TextStyle(fontSize: 10, color: Colors.white.withValues(alpha: 0.4)),
                        ),
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

  Widget _buildLanguageDropdown(
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
              value: value,
              isExpanded: true,
              dropdownColor: ZoyaTheme.sidebarBg,
              icon: Icon(Icons.language, color: ZoyaTheme.accent, size: 20),
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
}
