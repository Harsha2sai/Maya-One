import 'package:flutter/material.dart';
import '../../core/config/provider_config.dart';
import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';

class ProfilePanel extends StatefulWidget {
  final String userName;
  final String userEmail;
  final String preferredLanguage;
  final Function(String) onNameChanged;
  final Function(String) onLanguageChanged;

  const ProfilePanel({
    super.key,
    required this.userName,
    required this.userEmail,
    required this.preferredLanguage,
    required this.onNameChanged,
    required this.onLanguageChanged,
  });

  @override
  State<ProfilePanel> createState() => _ProfilePanelState();
}

class _ProfilePanelState extends State<ProfilePanel> {
  late final TextEditingController _nameController;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.userName);
  }

  @override
  void didUpdateWidget(covariant ProfilePanel oldWidget) {
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
    final selectedLanguage = _normalizeSelection(
      widget.preferredLanguage,
      languageOptions,
      fallback: 'en-US',
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        buildSectionHeader('👤 Identity', 'Manage how you are identified across the platform.'),
        const SizedBox(height: 24),

        // Name Field
        _buildTextField('Full Name', _nameController, widget.onNameChanged),
        const SizedBox(height: 20),

        // Email (Read-only)
        _buildReadOnlyField('Primary Email', widget.userEmail, Icons.verified_user_outlined),
        const SizedBox(height: 24),

        buildSubsectionHeader('🌍 Regional Options'),
        _buildLanguageDropdown(
          'Interface Language',
          selectedLanguage,
          ProviderConfig.preferredLanguages,
          (value) {
            if (value != null) {
              widget.onLanguageChanged(value);
            }
          },
        ),
      ],
    );
  }

  String _normalizeSelection(String value, List<String> options, {required String fallback}) {
    if (options.contains(value)) return value;
    return fallback;
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

  Widget _buildReadOnlyField(String label, String value, IconData icon) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(), style: const TextStyle(color: Colors.white54, fontSize: 10, letterSpacing: 1.5)),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.03),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white.withValues(alpha: 0.05)),
          ),
          child: Row(
            children: [
              Icon(icon, size: 18, color: ZoyaTheme.accent.withValues(alpha: 0.5)),
              const SizedBox(width: 12),
              Expanded(
                child: Text(value, style: const TextStyle(color: Colors.white70, fontSize: 14)),
              ),
              const Icon(Icons.lock_outline, size: 14, color: Colors.white24),
            ],
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
