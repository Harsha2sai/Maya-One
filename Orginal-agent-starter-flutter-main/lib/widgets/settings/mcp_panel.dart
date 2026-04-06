import 'package:flutter/material.dart';

import '../../ui/zoya_theme.dart';
import '../shared_widgets.dart';

class McpPanel extends StatefulWidget {
  final String n8nUrl;
  final bool isConfigured;
  final Map<String, Map<String, dynamic>> connectorStatus;
  final ValueChanged<String> onN8nUrlChanged;

  const McpPanel({
    super.key,
    required this.n8nUrl,
    required this.isConfigured,
    required this.connectorStatus,
    required this.onN8nUrlChanged,
  });

  @override
  State<McpPanel> createState() => _McpPanelState();
}

class _McpPanelState extends State<McpPanel> {
  late final TextEditingController _n8nController;

  @override
  void initState() {
    super.initState();
    _n8nController = TextEditingController(text: widget.n8nUrl);
  }

  @override
  void didUpdateWidget(covariant McpPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.n8nUrl != oldWidget.n8nUrl && widget.n8nUrl != _n8nController.text) {
      _n8nController.text = widget.n8nUrl;
    }
  }

  @override
  void dispose() {
    _n8nController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionHeader('🛠️ Tools & MCP', 'Technical execution layer for AI tools and external servers.'),
        const SizedBox(height: 24),
        _buildMcpServerCard(
          'N8N MCP Server',
          'Primary automation and tool routing server. Connects Maya to Spotify, Slack, and Google Workspace.',
          widget.n8nUrl,
          widget.onN8nUrlChanged,
          controller: _n8nController,
          isActive: widget.isConfigured,
        ),
        const SizedBox(height: 32),
        buildSubsectionHeader('🛡️ Local Tool Servers'),
        _buildMcpServerCard(
          'Postgres Tool Server',
          'Native database introspection and query execution.',
          'postgresql://localhost:5432/maya',
          (_) {},
          isActive: true,
          readOnly: true,
        ),
        const SizedBox(height: 48),
        buildSubsectionHeader('📡 Active Workflow Routing'),
        const SizedBox(height: 16),
        _buildRoutingItem('GET_WEATHER', 'WeatherAPI', '0.42s latency', true),
        _buildRoutingItem(
          'SPOTIFY_CONTROL',
          'N8N Server',
          '0.9s latency',
          widget.isConfigured && _connectorEnabled('spotify'),
        ),
        _buildRoutingItem(
          'YOUTUBE_PLAYBACK',
          'N8N Server',
          '1.0s latency',
          widget.isConfigured && _connectorEnabled('youtube'),
        ),
        _buildRoutingItem('QUERY_DB', 'Postgres Server', '0.08s latency', true),
        _buildRoutingItem(
          'SEND_EMAIL',
          'Google Workspace',
          '1.2s latency',
          widget.isConfigured && _connectorEnabled('google_workspace') && _connectorAvailable('google_workspace'),
        ),
        _buildRoutingItem(
          'HOME_AUTOMATION',
          'N8N Server',
          '1.4s latency',
          widget.isConfigured && _connectorEnabled('home_assistant') && _connectorAvailable('home_assistant'),
        ),
        const SizedBox(height: 32),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: ZoyaTheme.secondaryAccent.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: ZoyaTheme.secondaryAccent.withValues(alpha: 0.1)),
          ),
          child: Row(
            children: [
              Icon(Icons.info_outline, color: ZoyaTheme.secondaryAccent, size: 18),
              const SizedBox(width: 12),
              const Expanded(
                child: Text(
                  '💡 MCP (Model Context Protocol) allows Maya to use standardized tools across different servers.',
                  style: TextStyle(color: Colors.white54, fontSize: 11, height: 1.4),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildMcpServerCard(
    String name,
    String description,
    String url,
    ValueChanged<String> onChanged, {
    TextEditingController? controller,
    bool isActive = false,
    bool readOnly = false,
  }) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.03),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isActive ? ZoyaTheme.secondaryAccent.withValues(alpha: 0.3) : Colors.white12,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                name.toUpperCase(),
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  letterSpacing: 1,
                ),
              ),
              buildStatusBadge(isActive),
            ],
          ),
          const SizedBox(height: 8),
          Text(description, style: const TextStyle(color: Colors.white38, fontSize: 11, height: 1.4)),
          const SizedBox(height: 20),
          if (controller != null)
            TextField(
              controller: controller,
              onChanged: onChanged,
              readOnly: readOnly,
              style: const TextStyle(color: Colors.white, fontSize: 13, fontFamily: 'monospace'),
              decoration: _urlFieldDecoration(isActive),
            )
          else
            TextFormField(
              key: ValueKey('mcp_${name.toLowerCase()}_readonly'),
              initialValue: url,
              onChanged: onChanged,
              readOnly: readOnly,
              style: const TextStyle(color: Colors.white, fontSize: 13, fontFamily: 'monospace'),
              decoration: _urlFieldDecoration(isActive),
            ),
        ],
      ),
    );
  }

  InputDecoration _urlFieldDecoration(bool isActive) {
    return InputDecoration(
      filled: true,
      fillColor: ZoyaTheme.sidebarBg.withValues(alpha: 0.5),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
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
        borderSide: BorderSide(color: ZoyaTheme.secondaryAccent.withValues(alpha: 0.5)),
      ),
      hintText: 'Enter Server URL (e.g. http://localhost:5678)...',
      hintStyle: const TextStyle(color: Colors.white12, fontSize: 13),
      prefixIcon: Icon(
        Icons.link_outlined,
        size: 16,
        color: isActive ? ZoyaTheme.secondaryAccent.withValues(alpha: 0.6) : Colors.white24,
      ),
    );
  }

  bool _connectorEnabled(String id) => widget.connectorStatus[id]?['enabled'] == true;

  bool _connectorAvailable(String id) => widget.connectorStatus[id]?['available'] == true;

  Widget _buildRoutingItem(String tool, String server, String latency, bool isSystemActive) {
    final safeId = tool.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '_');
    return Padding(
      key: ValueKey('mcp_workflow_$safeId'),
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: isSystemActive ? ZoyaTheme.secondaryAccent : Colors.white10,
                  shape: BoxShape.circle,
                  boxShadow: isSystemActive ? [BoxShadow(color: ZoyaTheme.secondaryAccent, blurRadius: 4)] : [],
                ),
              ),
              const SizedBox(width: 12),
              Text(
                tool,
                style: TextStyle(
                  color: isSystemActive ? Colors.white : Colors.white24,
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          Row(
            children: [
              Container(
                key: ValueKey('mcp_workflow_status_$safeId'),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: isSystemActive ? ZoyaTheme.secondaryAccent.withValues(alpha: 0.15) : Colors.white10,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: isSystemActive ? ZoyaTheme.secondaryAccent.withValues(alpha: 0.35) : Colors.white12,
                  ),
                ),
                child: Text(
                  isSystemActive ? 'ACTIVE' : 'INACTIVE',
                  style: TextStyle(
                    color: isSystemActive ? ZoyaTheme.secondaryAccent : Colors.white38,
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Text(
                server,
                style: TextStyle(color: isSystemActive ? Colors.white38 : Colors.white10, fontSize: 11),
              ),
              const SizedBox(width: 12),
              Text(
                latency,
                style: TextStyle(
                  color: isSystemActive ? ZoyaTheme.secondaryAccent.withValues(alpha: 0.4) : Colors.white10,
                  fontSize: 9,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
