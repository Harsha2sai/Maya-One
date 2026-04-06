import 'package:flutter/material.dart';
import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';

class PreferencesPanel extends StatelessWidget {
  final String interfaceTheme;
  final bool quantumParticlesEnabled;
  final bool orbitalGlowEnabled;
  final bool soundEffectsEnabled;
  final Function(String) onThemeChanged;
  final Function(bool) onParticlesChanged;
  final Function(bool) onGlowChanged;
  final Function(bool) onSoundChanged;

  const PreferencesPanel({
    super.key,
    required this.interfaceTheme,
    required this.quantumParticlesEnabled,
    required this.orbitalGlowEnabled,
    required this.soundEffectsEnabled,
    required this.onThemeChanged,
    required this.onParticlesChanged,
    required this.onGlowChanged,
    required this.onSoundChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('🎨 Interface Theme', 'Choose the visual personality of your assistant.'),
        const SizedBox(height: 24),
        Row(
          children: [
            _buildThemeOption('MAYA', interfaceTheme == 'zoya', onTap: () => onThemeChanged('zoya')),
            const SizedBox(width: 16),
            _buildThemeOption('Classic', interfaceTheme == 'classic', onTap: () => onThemeChanged('classic')),
          ],
        ),
        const SizedBox(height: 40),
        buildSectionHeader('👁️ Visual Effects', 'Configure the rendering complexity of the interface.'),
        const SizedBox(height: 20),
        _buildToggle(
            'Quantum Particles', 'Enable dynamic floating particles in the background.', quantumParticlesEnabled,
            onChanged: onParticlesChanged),
        _buildToggle(
            'Orbital Glow Effects', 'Enable outer glow and neon lighting around focus elements.', orbitalGlowEnabled,
            onChanged: onGlowChanged),
        _buildToggle(
            'Interference Sound Effects', 'Play subtle sonic feedback for UI interactions.', soundEffectsEnabled,
            onChanged: onSoundChanged),
      ],
    );
  }

  Widget _buildThemeOption(String label, bool isActive, {required VoidCallback onTap}) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 20),
          decoration: BoxDecoration(
            color: isActive ? ZoyaTheme.accent.withValues(alpha: 0.15) : Colors.white.withValues(alpha: 0.05),
            border: Border.all(
              color: isActive ? ZoyaTheme.accent : Colors.white.withValues(alpha: 0.1),
              width: 1.5,
            ),
            borderRadius: BorderRadius.circular(12),
            boxShadow: isActive ? [BoxShadow(color: ZoyaTheme.accentGlow, blurRadius: 10)] : [],
          ),
          child: Center(
            child: Text(
              label,
              style: ZoyaTheme.fontDisplay.copyWith(
                fontSize: 14,
                color: isActive ? ZoyaTheme.accent : Colors.white.withValues(alpha: 0.6),
                letterSpacing: 2,
                fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildToggle(String label, String subtitle, bool value, {required ValueChanged<bool> onChanged}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(subtitle, style: const TextStyle(color: Colors.white38, fontSize: 11)),
              ],
            ),
          ),
          const SizedBox(width: 16),
          Switch(
            value: value,
            onChanged: onChanged,
            activeThumbColor: ZoyaTheme.accent,
            activeTrackColor: ZoyaTheme.accent.withValues(alpha: 0.2),
            inactiveThumbColor: Colors.white24,
            inactiveTrackColor: Colors.white10,
          ),
        ],
      ),
    );
  }
}
