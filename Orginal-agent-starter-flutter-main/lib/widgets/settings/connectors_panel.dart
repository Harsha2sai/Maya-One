import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../state/providers/chat_provider.dart';
import '../../state/providers/settings_provider.dart';
import '../../state/providers/session_provider.dart';
import '../../ui/theme/app_theme.dart';
import '../common/shared_widgets.dart';

class ConnectorsPanel extends StatefulWidget {
  const ConnectorsPanel({super.key});

  @override
  State<ConnectorsPanel> createState() => _ConnectorsPanelState();
}

class _ConnectorsPanelState extends State<ConnectorsPanel> {
  lk.EventsListener<lk.RoomEvent>? _roomEventListener;
  lk.Room? _boundRoom;
  bool _waitingForSpotifyLogin = false;
  String? _statusMessage;
  String? _selectedConnectorId;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final room = context.read<SessionProvider>().room;
    if (!identical(room, _boundRoom)) {
      _bindRoomListener(room);
    }
  }

  void _bindRoomListener(lk.Room? room) {
    _roomEventListener?.dispose();
    _roomEventListener = null;
    _boundRoom = room;

    if (room == null) {
      return;
    }

    _roomEventListener = room.createListener()..on<lk.DataReceivedEvent>(_handleRoomDataEvent);
  }

  Future<void> _handleRoomDataEvent(lk.DataReceivedEvent event) async {
    final topic = event.topic;
    if (topic != 'maya/system/spotify/auth_url' &&
        topic != 'maya/system/spotify/connected' &&
        topic != 'maya/system/spotify/error') {
      return;
    }

    Map<String, dynamic> payload = const <String, dynamic>{};
    try {
      final decoded = jsonDecode(utf8.decode(event.data));
      if (decoded is Map) {
        payload = decoded.cast<String, dynamic>();
      }
    } catch (_) {
      payload = const <String, dynamic>{};
    }

    if (!mounted) {
      return;
    }

    if (topic == 'maya/system/spotify/auth_url') {
      final url = (payload['url'] ?? '').toString().trim();
      if (url.isEmpty) {
        setState(() {
          _waitingForSpotifyLogin = false;
          _statusMessage = 'Spotify login URL was empty.';
        });
        return;
      }

      final uri = Uri.tryParse(url);
      if (uri == null) {
        setState(() {
          _waitingForSpotifyLogin = false;
          _statusMessage = 'Spotify login URL is invalid.';
        });
        return;
      }

      final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!mounted) {
        return;
      }
      setState(() {
        _waitingForSpotifyLogin = true;
        _statusMessage = launched ? 'Waiting for Spotify login...' : 'Unable to open browser for Spotify login.';
      });
      return;
    }

    if (topic == 'maya/system/spotify/connected') {
      final connected = payload['connected'] == true;
      final displayName = payload['display_name']?.toString();
      context.read<ChatProvider>().updateSpotifyStatus(
            connected: connected,
            displayName: connected ? displayName : null,
          );
      setState(() {
        _waitingForSpotifyLogin = false;
        _statusMessage = connected ? 'Spotify connected.' : 'Spotify disconnected.';
      });
      return;
    }

    final message = (payload['message'] ?? 'Spotify operation failed.').toString();
    setState(() {
      _waitingForSpotifyLogin = false;
      _statusMessage = message;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _requestSpotifyAuth(SessionProvider session) async {
    final room = session.room;
    if (room?.localParticipant == null) {
      setState(() {
        _waitingForSpotifyLogin = false;
        _statusMessage = 'Connect to a session before starting Spotify login.';
      });
      return;
    }

    try {
      // Use the standard command channel so backend receives the request reliably.
      await session.sendCommand('spotify_connect_request', {'platform': 'desktop'});
      if (!mounted) {
        return;
      }
      setState(() {
        _waitingForSpotifyLogin = true;
        _statusMessage = 'Waiting for Spotify login...';
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _waitingForSpotifyLogin = false;
        _statusMessage = 'Failed to send Spotify login request.';
      });
    }
  }

  @override
  void dispose() {
    _roomEventListener?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final chat = context.watch<ChatProvider>();
    final settings = context.watch<SettingsProvider>();
    final session = context.read<SessionProvider>();
    final enabledMap = _resolveConnectorEnabledMap(settings);

    final cards = <_ConnectorCardData>[
      _ConnectorCardData(
        id: 'spotify',
        label: 'Spotify',
        description: 'Music playback and search',
        imageAsset: 'assets/connectors/spotify.png',
        connected: chat.spotifyConnected && (enabledMap['spotify'] ?? true),
        displayName: chat.spotifyDisplayName,
        enabled: enabledMap['spotify'] ?? true,
      ),
      const _ConnectorCardData(
        id: 'youtube',
        label: 'YouTube',
        description: 'Video search and playback',
        imageAsset: 'assets/connectors/youtube.png',
        comingSoon: true,
        enabled: false,
      ),
      const _ConnectorCardData(
        id: 'google-calendar',
        label: 'Google Cal',
        description: 'Calendar access',
        imageAsset: 'assets/connectors/google_calendar.png',
        comingSoon: true,
        enabled: false,
      ),
      const _ConnectorCardData(
        id: 'notion',
        label: 'Notion',
        description: 'Notes and documents',
        imageAsset: 'assets/connectors/notion.png',
        comingSoon: true,
        enabled: false,
      ),
    ];

    return SingleChildScrollView(
      key: const Key('connectors_panel'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_selectedConnectorId == null) ...[
            buildSectionHeader(
              'Connectors',
              "Connect external services to extend Maya's capabilities",
            ),
            if (_statusMessage != null && _statusMessage!.trim().isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                _statusMessage!,
                style: ZoyaTheme.fontBody.copyWith(
                  color: Colors.white70,
                  fontSize: 12,
                ),
              ),
            ],
            const SizedBox(height: 48),
            Center(
              child: Wrap(
                spacing: 40,
                runSpacing: 40,
                alignment: WrapAlignment.center,
                children: cards.map((card) {
                  return _buildGlowingIcon(
                    card,
                    onTap: () {
                      setState(() {
                        _selectedConnectorId = card.id;
                        _statusMessage = null;
                      });
                    },
                  );
                }).toList(),
              ),
            ),
          ] else
            _buildConnectorDetail(
              cards.firstWhere((c) => c.id == _selectedConnectorId),
              chat,
              settings,
              session,
            ),
        ],
      ),
    );
  }

  Widget _buildGlowingIcon(_ConnectorCardData card, {required VoidCallback onTap}) {
    final isConnected = card.connected;
    final isComingSoon = card.comingSoon;
    final isEnabled = card.enabled && !isComingSoon;

    // Theme colors
    final baseColor = const Color(0xFF1E1E24); // Dark background base
    final Color glowColor;
    if (isComingSoon) {
      glowColor = Colors.white24;
    } else if (!isEnabled) {
      glowColor = Colors.white24;
    } else if (isConnected) {
      if (card.id == 'spotify') {
        glowColor = const Color(0xFF1DB954);
      } else {
        glowColor = Colors.greenAccent;
      }
    } else {
      glowColor = ZoyaTheme.accent;
    }

    return GestureDetector(
      key: Key('connector_icon_${card.id}'),
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 86,
            height: 86,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: baseColor,
              border: Border.all(
                color:
                    isComingSoon || !isEnabled ? Colors.white12 : glowColor.withValues(alpha: isConnected ? 0.8 : 0.4),
                width: 2,
              ),
              boxShadow: [
                if (!isComingSoon && isEnabled)
                  BoxShadow(
                    color: glowColor.withValues(alpha: isConnected ? 0.4 : 0.15),
                    blurRadius: 20,
                    spreadRadius: 2,
                  ),
                // Soft dark inner-like shadow simulation
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.6),
                  offset: const Offset(4, 4),
                  blurRadius: 12,
                ),
                BoxShadow(
                  color: Colors.white.withValues(alpha: 0.03),
                  offset: const Offset(-4, -4),
                  blurRadius: 10,
                ),
              ],
            ),
            child: Center(
              child: Opacity(
                opacity: isComingSoon || !isEnabled ? 0.38 : 1.0,
                child: Image.asset(card.imageAsset, width: 40, height: 40),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            card.label,
            style: ZoyaTheme.fontBody.copyWith(
              color: Colors.white.withValues(alpha: isComingSoon || !isEnabled ? 0.4 : 0.9),
              fontWeight: FontWeight.w600,
              fontSize: 14,
              letterSpacing: 0.5,
            ),
          ),
          if (isConnected && isEnabled) ...[
            const SizedBox(height: 6),
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                color: glowColor,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(color: glowColor, blurRadius: 4, spreadRadius: 1),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildConnectorDetail(
    _ConnectorCardData card,
    ChatProvider chat,
    SettingsProvider settings,
    SessionProvider session,
  ) {
    final waiting = _waitingForSpotifyLogin && card.id == 'spotify';
    final isConnected = card.connected;
    final isComingSoon = card.comingSoon;
    final isEnabled = card.enabled && !isComingSoon;
    final statusLabel =
        isComingSoon ? 'Coming Soon' : (isEnabled ? (isConnected ? 'Connected' : 'Disconnected') : 'Disabled');
    final statusColor = isConnected && isEnabled ? Colors.greenAccent : Colors.white54;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            IconButton(
              icon: const Icon(Icons.arrow_back, color: Colors.white70),
              onPressed: () {
                setState(() {
                  _selectedConnectorId = null;
                  _statusMessage = null;
                });
              },
            ),
            const SizedBox(width: 8),
            Image.asset(card.imageAsset, width: 28, height: 28),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                card.label,
                style: ZoyaTheme.fontDisplay.copyWith(
                  fontSize: 22,
                  color: Colors.white,
                  letterSpacing: 1.0,
                ),
              ),
            ),
          ],
        ),
        if (_statusMessage != null && _statusMessage!.trim().isNotEmpty) ...[
          const SizedBox(height: 16),
          Text(
            _statusMessage!,
            style: ZoyaTheme.fontBody.copyWith(
              color: Colors.white70,
              fontSize: 13,
            ),
          ),
        ],
        const SizedBox(height: 24),
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.03),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: ZoyaTheme.accent.withValues(alpha: 0.15)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'APPLICATION CONNECTOR',
                style: ZoyaTheme.fontBody.copyWith(
                  color: Colors.white38,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                card.description,
                style: ZoyaTheme.fontBody.copyWith(color: Colors.white, fontSize: 16, height: 1.5),
              ),
              const SizedBox(height: 32),
              Row(
                children: [
                  Text(
                    'Status:',
                    style: ZoyaTheme.fontBody.copyWith(color: Colors.white54, fontSize: 14),
                  ),
                  const SizedBox(width: 12),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: statusColor.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: statusColor.withValues(alpha: 0.3),
                      ),
                    ),
                    child: Text(
                      statusLabel,
                      style: ZoyaTheme.fontBody.copyWith(
                        color: statusColor,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
              if (card.id == 'spotify' && isConnected && (card.displayName ?? '').isNotEmpty) ...[
                const SizedBox(height: 16),
                Row(
                  children: [
                    Text(
                      'Account:',
                      style: ZoyaTheme.fontBody.copyWith(color: Colors.white54, fontSize: 14),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      card.displayName!,
                      style: ZoyaTheme.fontBody.copyWith(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 24),
              Row(
                children: [
                  Text(
                    'Enabled:',
                    style: ZoyaTheme.fontBody.copyWith(color: Colors.white54, fontSize: 14),
                  ),
                  const SizedBox(width: 12),
                  Switch(
                    value: isEnabled,
                    onChanged: isComingSoon
                        ? null
                        : (value) async {
                            await _setConnectorEnabled(settings, card.id, value);
                          },
                    activeThumbColor: ZoyaTheme.accent,
                  ),
                ],
              ),
              const SizedBox(height: 48),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: (isComingSoon || !isEnabled)
                      ? null
                      : (isConnected
                          ? () => session.sendCommand(
                                'spotify_disconnect_request',
                                {'platform': 'desktop'},
                              )
                          : (waiting ? null : () => _requestSpotifyAuth(session))),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: isConnected ? Colors.redAccent.withValues(alpha: 0.15) : ZoyaTheme.accent,
                    foregroundColor: isConnected ? Colors.redAccent : Colors.black,
                    padding: const EdgeInsets.symmetric(vertical: 18),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    side: isConnected ? BorderSide(color: Colors.redAccent.withValues(alpha: 0.5)) : BorderSide.none,
                  ),
                  child: Text(
                    isComingSoon
                        ? 'Not Available'
                        : (!isEnabled
                            ? 'Disabled'
                            : (isConnected ? 'Disconnect Account' : (waiting ? 'Waiting...' : 'Connect Account'))),
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, letterSpacing: 0.5),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ConnectorCardData {
  final String id;
  final String label;
  final String description;
  final String imageAsset;
  final bool connected;
  final String? displayName;
  final bool comingSoon;
  final bool enabled;

  const _ConnectorCardData({
    required this.id,
    required this.label,
    required this.description,
    required this.imageAsset,
    this.connected = false,
    this.displayName,
    this.comingSoon = false,
    this.enabled = true,
  });
}

Map<String, bool> _resolveConnectorEnabledMap(SettingsProvider settings) {
  final prefs = settings.preferences;
  final raw = prefs['connectorsEnabled'];
  if (raw is Map) {
    return raw.map((key, value) => MapEntry(key.toString(), value == true));
  }
  return const {};
}

Future<void> _setConnectorEnabled(
  SettingsProvider settings,
  String connectorId,
  bool enabled,
) async {
  final current = Map<String, dynamic>.from(settings.preferences['connectorsEnabled'] ?? {});
  current[connectorId] = enabled;
  await settings.updatePreferences({'connectorsEnabled': current});
}
