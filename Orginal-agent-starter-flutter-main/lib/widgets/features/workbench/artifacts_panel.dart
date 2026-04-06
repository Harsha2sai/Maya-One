import 'package:flutter/material.dart';
import '../../../ui/theme/app_theme.dart';

class ArtifactsPanel extends StatelessWidget {
  const ArtifactsPanel({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Generated Artifacts',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: ZoyaTheme.textMain,
            ),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: ListView(
              children: [
                _buildArtifactPlaceholder('Architecture Diagram', Icons.image),
                _buildArtifactPlaceholder('API Schema', Icons.data_object),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildArtifactPlaceholder(String title, IconData icon) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: ZoyaTheme.glassBorder.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(icon, color: ZoyaTheme.accent, size: 24),
          const SizedBox(width: 12),
          Text(title, style: const TextStyle(color: ZoyaTheme.textMain)),
        ],
      ),
    );
  }
}
