import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/providers/settings_provider.dart';
import '../shared_widgets.dart';

class IntegrationsPanel extends StatelessWidget {
  const IntegrationsPanel({super.key});

  static const List<_ConnectorMeta> _connectors = [
    _ConnectorMeta(
      id: 'spotify',
      name: 'Spotify',
      description: 'Control playback and search songs.',
      iconData: Icons.music_note,
      color: Color(0xFF1DB954),
    ),
    _ConnectorMeta(
      id: 'google_workspace',
      name: 'Google Workspace',
      description: 'Manage mail, calendar, and drive.',
      iconData: Icons.mail_outline,
      color: Color(0xFF4285F4),
    ),
    _ConnectorMeta(
      id: 'slack',
      name: 'Slack',
      description: 'Send messages and monitor channels.',
      iconData: Icons.chat_bubble_outline,
      color: Color(0xFF4A154B),
    ),
    _ConnectorMeta(
      id: 'home_assistant',
      name: 'Home Assistant',
      description: 'Control smart home devices.',
      iconData: Icons.home_outlined,
      color: Color(0xFF03A9F4),
    ),
    _ConnectorMeta(
      id: 'github',
      name: 'GitHub',
      description: 'Monitor repos and issues.',
      iconData: Icons.code,
      color: Colors.white70,
    ),
    _ConnectorMeta(
      id: 'youtube',
      name: 'YouTube',
      description: 'Search and play video content.',
      iconData: Icons.play_circle_outline,
      color: Color(0xFFFF0000),
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Consumer<SettingsProvider>(
      builder: (context, settings, _) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            buildSectionHeader('🔌 Connectors', 'Enable Maya to interact with your favorite applications.'),
            const SizedBox(height: 32),
            GridView(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: MediaQuery.of(context).size.width > 800 ? 3 : 2,
                mainAxisSpacing: 16,
                crossAxisSpacing: 16,
                mainAxisExtent: 220,
              ),
              children: _connectors.map((meta) => _buildConnectorCard(context, settings, meta)).toList(growable: false),
            ),
          ],
        );
      },
    );
  }

  Widget _buildConnectorCard(BuildContext context, SettingsProvider settings, _ConnectorMeta meta) {
    final enabled = settings.connectorEnabled(meta.id);
    final available = settings.connectorAvailable(meta.id);
    final reason = settings.connectorReason(meta.id);
    final saving = settings.isConnectorSaving(meta.id);
    final error = settings.connectorError(meta.id);

    final effectiveColor = available ? meta.color : Colors.white24;
    final statusLabel = !available
        ? 'COMING SOON'
        : enabled
            ? 'ENABLED'
            : 'DISABLED';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: enabled && available ? effectiveColor.withValues(alpha: 0.3) : Colors.white.withValues(alpha: 0.06),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: effectiveColor.withValues(alpha: 0.1),
                  shape: BoxShape.circle,
                ),
                child: Icon(meta.iconData, color: effectiveColor, size: 20),
              ),
              const Spacer(),
              if (saving)
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            meta.name,
            style: TextStyle(
              color: available ? Colors.white : Colors.white54,
              fontWeight: FontWeight.bold,
              fontSize: 14,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            meta.description,
            style: const TextStyle(color: Colors.white38, fontSize: 10, height: 1.4),
          ),
          const SizedBox(height: 8),
          if (!available && reason.isNotEmpty)
            Text(
              reason,
              style: const TextStyle(color: Colors.white30, fontSize: 10, height: 1.3),
            ),
          if (error != null && error.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                error,
                style: const TextStyle(color: Color(0xFFFF6B6B), fontSize: 10, height: 1.3),
              ),
            ),
          const Spacer(),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: enabled && available
                      ? effectiveColor.withValues(alpha: 0.1)
                      : Colors.white.withValues(alpha: 0.05),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  statusLabel,
                  style: TextStyle(
                    color: enabled && available ? effectiveColor : Colors.white38,
                    fontSize: 8,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1,
                  ),
                ),
              ),
              Switch(
                value: enabled,
                onChanged: (!available || saving)
                    ? null
                    : (value) => unawaited(_toggleConnector(context, settings, meta.id, value)),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _toggleConnector(
    BuildContext context,
    SettingsProvider settings,
    String connectorId,
    bool enabled,
  ) async {
    final ok = await settings.setConnectorEnabled(connectorId, enabled);
    if (!ok && context.mounted) {
      final error = settings.connectorError(connectorId) ?? 'Failed to save connector setting.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error), backgroundColor: const Color(0xFFB3261E)),
      );
    }
  }
}

class _ConnectorMeta {
  final String id;
  final String name;
  final String description;
  final IconData iconData;
  final Color color;

  const _ConnectorMeta({
    required this.id,
    required this.name,
    required this.description,
    required this.iconData,
    required this.color,
  });
}
