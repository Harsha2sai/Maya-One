import 'package:flutter/material.dart';
import '../../core/config/provider_config.dart';
import '../../state/providers/settings_provider.dart';
import '../shared_widgets.dart';
import '../../ui/zoya_theme.dart';
import 'package:provider/provider.dart';

class AIProvidersPanel extends StatelessWidget {
  final String llmProvider;
  final String llmModel;
  final double llmTemperature;
  final Function(String) onProviderChanged;
  final Function(String) onModelChanged;
  final Function(double) onTemperatureChanged;

  const AIProvidersPanel({
    super.key,
    required this.llmProvider,
    required this.llmModel,
    required this.llmTemperature,
    required this.onProviderChanged,
    required this.onModelChanged,
    required this.onTemperatureChanged,
  });

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('🤖 LLM Provider', 'Choose the language model for conversations.'),
        const SizedBox(height: 20),
        _buildProviderDropdown(
          'Provider',
          llmProvider,
          ProviderConfig.llmProviders,
          settings.apiKeyStatus,
          (val) {
            if (val != null) {
              onProviderChanged(val);
              final models = ProviderConfig.getModelsForProvider(val, 'llm');
              if (models.isNotEmpty) onModelChanged(models.first);
            }
          },
        ),
        const SizedBox(height: 24),
        _buildDropdown(
          'Model',
          llmModel,
          ProviderConfig.getModelsForProvider(llmProvider, 'llm'),
          (val) { if (val != null) onModelChanged(val); },
        ),
        const SizedBox(height: 24),
        _buildSlider('Temperature: ${llmTemperature.toStringAsFixed(1)}', llmTemperature, 0, 1, onTemperatureChanged),
      ],
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

  Widget _buildSlider(String label, double value, double min, double max, ValueChanged<double> onChanged) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white70, fontSize: 12)),
        Slider(
          value: value,
          min: min,
          max: max,
          activeColor: ZoyaTheme.accent,
          inactiveColor: Colors.white12,
          onChanged: onChanged,
        ),
      ],
    );
  }
}
