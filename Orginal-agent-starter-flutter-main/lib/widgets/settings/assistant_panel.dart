import 'package:flutter/material.dart';
import '../../core/config/provider_config.dart';
import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';

class AssistantPanel extends StatelessWidget {
  final String llmProvider;
  final String llmModel;
  final double llmTemperature;
  final String assistantPersonality;
  final Function(String) onProviderChanged;
  final Function(String) onModelChanged;
  final Function(double) onTemperatureChanged;
  final Function(String) onPersonalityChanged;

  const AssistantPanel({
    super.key,
    required this.llmProvider,
    required this.llmModel,
    required this.llmTemperature,
    required this.assistantPersonality,
    required this.onProviderChanged,
    required this.onModelChanged,
    required this.onTemperatureChanged,
    required this.onPersonalityChanged,
  });

  @override
  Widget build(BuildContext context) {
    final personalityOptions = ProviderConfig.assistantPersonalities.map((item) => item['id']!).toList();
    final selectedPersonality = _normalizeSelection(
      assistantPersonality,
      personalityOptions,
      fallback: 'professional',
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('🧠 Intelligence', 'Configure the core reasoning engine of your assistant.'),
        const SizedBox(height: 24),

        // LLM Provider
        _buildDropdown(
          'Model Provider',
          llmProvider,
          ProviderConfig.llmProviders,
          (value) => value != null ? onProviderChanged(value) : null,
        ),
        const SizedBox(height: 20),

        // LLM Model
        _buildSimpleDropdown(
          'Active Model',
          llmModel,
          ProviderConfig.getModelsForProvider(llmProvider, 'llm'),
          (value) => value != null ? onModelChanged(value) : null,
        ),
        const SizedBox(height: 24),

        // Temperature Slider
        _buildTemperatureSlider(),
        const SizedBox(height: 40),

        buildSectionHeader('🎭 Personality', 'Define the conversational tone and behavioral style.'),
        const SizedBox(height: 20),

        _buildPersonalityDropdown(
          'Behavioral Persona',
          selectedPersonality,
          ProviderConfig.assistantPersonalities,
          (value) => value != null ? onPersonalityChanged(value) : null,
        ),
      ],
    );
  }

  String _normalizeSelection(String value, List<String> options, {required String fallback}) {
    if (options.contains(value)) return value;
    return fallback;
  }

  Widget _buildTemperatureSlider() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text('CREATIVITY (TEMPERATURE)',
                style: TextStyle(color: Colors.white54, fontSize: 10, letterSpacing: 1.5)),
            Text(llmTemperature.toStringAsFixed(1),
                style: const TextStyle(color: ZoyaTheme.accent, fontWeight: FontWeight.bold, fontSize: 12)),
          ],
        ),
        SliderTheme(
          data: SliderThemeData(
            activeTrackColor: ZoyaTheme.accent,
            inactiveTrackColor: Colors.white10,
            thumbColor: ZoyaTheme.accent,
            overlayColor: ZoyaTheme.accent.withValues(alpha: 0.1),
            valueIndicatorColor: ZoyaTheme.accent,
          ),
          child: Slider(
            value: llmTemperature,
            min: 0.0,
            max: 1.0,
            divisions: 10,
            onChanged: (v) => onTemperatureChanged(v),
          ),
        ),
        const Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Precise', style: TextStyle(color: Colors.white24, fontSize: 10)),
            Text('Creative', style: TextStyle(color: Colors.white24, fontSize: 10)),
          ],
        ),
      ],
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
              icon: Icon(Icons.psychology_outlined, color: ZoyaTheme.accent),
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
                      if (description != null)
                        Text(description, style: const TextStyle(fontSize: 10, color: Colors.white38)),
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
}
