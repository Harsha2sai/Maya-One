import 'package:flutter/material.dart';
import '../shared_widgets.dart';
import '../../ui/zoya_theme.dart';

class GeneralPanel extends StatelessWidget {
  final String interfaceTheme;
  final bool quantumParticlesEnabled;
  final bool orbitalGlowEnabled;
  final bool soundEffectsEnabled;
  final Function(String) onThemeChanged;
  final Function(bool) onParticlesChanged;
  final Function(bool) onGlowChanged;
  final Function(bool) onSoundChanged;

  const GeneralPanel({
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
        buildSectionHeader('🎭 Interface Theme', 'Choose the visual personality of your assistant.'),
        const SizedBox(height: 20),
        Row(
          children: [
            _buildThemeOption('ZOYA', interfaceTheme == 'zoya', onTap: () => onThemeChanged('zoya')),
            const SizedBox(width: 20),
            _buildThemeOption('Classic', interfaceTheme == 'classic', onTap: () => onThemeChanged('classic')),
          ],
        ),
        const SizedBox(height: 40),
        buildSectionHeader('👁️ Visual Effects', ''),
        _buildToggle('Quantum Particles', quantumParticlesEnabled, onChanged: onParticlesChanged),
        _buildToggle('Orbital Glow Effects', orbitalGlowEnabled, onChanged: onGlowChanged),
        _buildToggle('Sound Effects', soundEffectsEnabled, onChanged: onSoundChanged),
      ],
    );
  }

  Widget _buildThemeOption(String label, bool isActive, {required VoidCallback onTap}) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        decoration: BoxDecoration(
          color: isActive ? ZoyaTheme.accent.withValues(alpha: 0.15) : Colors.white.withValues(alpha: 0.05),
          border: Border.all(
            color: isActive ? ZoyaTheme.accent : Colors.white.withValues(alpha: 0.1),
            width: 1.5,
          ),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(
          label,
          style: ZoyaTheme.fontDisplay.copyWith(
            fontSize: 14,
            color: isActive ? ZoyaTheme.accent : Colors.white.withValues(alpha: 0.6),
            letterSpacing: 1,
          ),
        ),
      ),
    );
  }

  Widget _buildToggle(String label, bool value, {required ValueChanged<bool> onChanged}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 14)),
          Switch(
            value: value,
            onChanged: onChanged,
            activeColor: ZoyaTheme.accent,
          ),
        ],
      ),
    );
  }
}
