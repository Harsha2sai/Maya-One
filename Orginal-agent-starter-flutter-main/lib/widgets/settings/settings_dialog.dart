import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../state/providers/settings_provider.dart';
import '../../ui/zoya_theme.dart';
import '../../core/services/storage_service.dart';
import 'account_panel.dart';
import 'assistant_panel.dart';
import 'api_keys_panel.dart';
import 'developer_panel.dart';
import 'preferences_panel.dart';
import 'memory_privacy_panel.dart';
import 'profile_panel.dart';
import 'voice_interaction_panel.dart';
import 'integrations_panel.dart';
import 'mcp_panel.dart';

class SettingsDialog extends StatefulWidget {
  const SettingsDialog({super.key});

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  String? _selectedSection;
  final Map<String, dynamic> _apiKeyDraft = {};
  final Map<String, bool> _showApiKey = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(context.read<SettingsProvider>().fetchApiKeyStatus());
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SettingsProvider>(
      builder: (context, settings, _) {
        final panels = _buildPanels(settings);
        final filteredSections = _getFilteredSections(settings, panels.keys.toList());
        if (filteredSections.isEmpty) {
          return const SizedBox.shrink();
        }
        final activeSection = (_selectedSection != null && filteredSections.contains(_selectedSection))
            ? _selectedSection!
            : filteredSections.first;

        return Dialog(
          backgroundColor: Colors.transparent,
          elevation: 0,
          insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
              child: Container(
                constraints: const BoxConstraints(maxWidth: 1000, maxHeight: 800),
                decoration: BoxDecoration(
                  color: ZoyaTheme.mainBg.withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: ZoyaTheme.glassBorder, width: 1.5),
                  boxShadow: [
                    BoxShadow(
                      color: ZoyaTheme.accent.withValues(alpha: 0.05),
                      blurRadius: 40,
                      spreadRadius: 5,
                    ),
                  ],
                ),
                child: Material(
                  color: Colors.transparent,
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      final isMobile = constraints.maxWidth < 900;
                      if (isMobile) {
                        return _buildMobileLayout(constraints, filteredSections, panels);
                      } else {
                        return _buildDesktopLayout(
                          constraints,
                          activeSection,
                          filteredSections,
                          panels,
                        );
                      }
                    },
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  // ── Layouts ────────────────────────────────────────────────────────────────

  Widget _buildMobileLayout(BoxConstraints constraints, List<String> sections, Map<String, Widget> panels) {
    return Container(
      key: const Key('settings_mobile_layout'),
      child: _selectedSection == null
          ? _buildMobileSectionList(constraints, sections)
          : _buildMobileSectionPage(_selectedSection!, sections, panels),
    );
  }

  Widget _buildDesktopLayout(
    BoxConstraints constraints,
    String activeSection,
    List<String> sections,
    Map<String, Widget> panels,
  ) {
    final sidebarWidth = constraints.maxWidth >= 1100 ? 260.0 : 240.0;
    final contentPadding = constraints.maxWidth >= 1050 ? 32.0 : 24.0;
    final availablePanelWidth = constraints.maxWidth - sidebarWidth - (contentPadding * 2);
    final panelMaxWidth = availablePanelWidth.clamp(520.0, 680.0);

    return Column(
      key: const Key('settings_desktop_layout'),
      children: [
        _buildHeader(title: activeSection),
        Expanded(
          child: Row(
            children: [
              _buildSidebar(activeSection, sections, width: sidebarWidth),
              Expanded(
                child: Padding(
                  padding: EdgeInsets.all(contentPadding),
                  child: SingleChildScrollView(
                    child: Align(
                      alignment: Alignment.topLeft,
                      child: ConstrainedBox(
                        constraints: BoxConstraints(maxWidth: panelMaxWidth),
                        child: _panelForSection(activeSection, sections, panels),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // ── Sidebar ────────────────────────────────────────────────────────────────

  Widget _buildSidebar(String activeSection, List<String> sections, {required double width}) {
    return Container(
      width: width,
      decoration: BoxDecoration(
        color: ZoyaTheme.sidebarBg.withValues(alpha: 0.4),
        border: Border(right: BorderSide(color: ZoyaTheme.glassBorder)),
      ),
      child: ListView(
        padding: const EdgeInsets.symmetric(vertical: 24),
        children: [
          _buildSidebarGroup('ME', ['Profile', 'Preferences'], activeSection, sections),
          const SizedBox(height: 32),
          _buildSidebarGroup('BEHAVIOR', ['Assistant', 'Interaction', 'Memory & Privacy'], activeSection, sections),
          const SizedBox(height: 32),
          _buildSidebarGroup(
            'SYSTEM',
            ['API Keys', 'Connectors', 'Tools & MCP', 'Developer', 'Account'],
            activeSection,
            sections,
          ),
        ],
      ),
    );
  }

  Widget _buildSidebarGroup(String title, List<String> items, String activeSection, List<String> availableSections) {
    final filteredItems = items.where((i) => availableSections.contains(i)).toList();
    if (filteredItems.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
          child: Text(
            title,
            style: ZoyaTheme.fontDisplay.copyWith(
              color: Colors.white24,
              fontSize: 10,
              letterSpacing: 2,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        ...filteredItems.map((item) => _buildSidebarItem(item, activeSection == item)),
      ],
    );
  }

  Widget _buildSidebarItem(String title, bool isSelected) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: InkWell(
        onTap: () => setState(() => _selectedSection = title),
        borderRadius: BorderRadius.circular(10),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: isSelected ? ZoyaTheme.accent.withValues(alpha: 0.1) : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSelected ? ZoyaTheme.accent.withValues(alpha: 0.3) : Colors.transparent,
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: isSelected ? ZoyaTheme.accent : Colors.white70,
                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                    fontSize: 14,
                  ),
                ),
              ),
              if (isSelected) ...[
                const SizedBox(width: 8),
                Container(
                  width: 4,
                  height: 14,
                  decoration: BoxDecoration(
                    color: ZoyaTheme.accent,
                    borderRadius: BorderRadius.circular(2),
                    boxShadow: [BoxShadow(color: ZoyaTheme.accentGlow, blurRadius: 4)],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  // ── Panes ──────────────────────────────────────────────────────────────────

  Map<String, Widget> _buildPanels(SettingsProvider settings) {
    final slotState = <String, dynamic>{};
    for (final entry in settings.maskedApiKeys.entries) {
      final key = entry.key;
      if (key.endsWith('_active_slot') || key.endsWith('_slot_count') || key == 'livekit_active_slot') {
        slotState[key] = entry.value;
      }
    }
    final mergedApiKeys = <String, dynamic>{
      ...slotState,
      ...settings.localApiKeys,
      ..._apiKeyDraft,
    };

    return {
      'Profile': ProfilePanel(
        userName: settings.userName,
        userEmail: settings.userEmail,
        preferredLanguage: settings.preferredLanguage,
        onNameChanged: (v) => settings.updatePreference('userName', v),
        onLanguageChanged: (v) => settings.updatePreference('preferredLanguage', v),
      ),
      'Preferences': PreferencesPanel(
        interfaceTheme: settings.interfaceTheme,
        quantumParticlesEnabled: settings.quantumParticlesEnabled,
        orbitalGlowEnabled: settings.orbitalGlowEnabled,
        soundEffectsEnabled: settings.soundEffectsEnabled,
        onThemeChanged: (v) => settings.updatePreference('interfaceTheme', v),
        onParticlesChanged: (v) => settings.updatePreference('quantumParticlesEnabled', v),
        onGlowChanged: (v) => settings.updatePreference('orbitalGlowEnabled', v),
        onSoundChanged: (v) => settings.updatePreference('soundEffectsEnabled', v),
      ),
      'Assistant': AssistantPanel(
        llmProvider: settings.llmProvider,
        llmModel: settings.llmModel,
        llmTemperature: settings.llmTemperature,
        assistantPersonality: settings.assistantPersonality,
        onProviderChanged: (v) => settings.updatePreference('llmProvider', v),
        onModelChanged: (v) => settings.updatePreference('llmModel', v),
        onTemperatureChanged: (v) => settings.updatePreference('llmTemperature', v),
        onPersonalityChanged: (v) => settings.updatePreference('assistantPersonality', v),
      ),
      'Interaction': VoiceInteractionPanel(
        sttProvider: settings.sttProvider,
        sttModel: settings.sttModel,
        sttLanguage: settings.sttLanguage,
        ttsProvider: settings.ttsProvider,
        ttsVoice: settings.ttsVoice,
        interactionMode: settings.interactionMode,
        onSttProviderChanged: (v) => settings.updatePreference('sttProvider', v),
        onSttModelChanged: (v) => settings.updatePreference('sttModel', v),
        onSttLanguageChanged: (v) => settings.updatePreference('sttLanguage', v),
        onTtsProviderChanged: (v) => settings.updatePreference('ttsProvider', v),
        onTtsVoiceChanged: (v) => settings.updatePreference('ttsVoice', v),
        onInteractionModeChanged: (v) => settings.updatePreference('interactionMode', v),
      ),
      'Memory & Privacy': MemoryPrivacyPanel(
        mem0Enabled: settings.mem0Enabled,
        mem0ApiKey: settings.mem0ApiKey,
        onEnabledChanged: (v) => settings.updatePreference('mem0Enabled', v),
        onApiKeyChanged: (v) => settings.updateApiKey('mem0', v),
        onClearHistory: () {
          unawaited(_handleClearHistory(context, settings));
        },
        onExportData: () {
          unawaited(_handleExportData(context, settings));
        },
      ),
      'API Keys': ApiKeysPanel(
        apiKeys: mergedApiKeys,
        showApiKey: _showApiKey,
        awsAccessKey: mergedApiKeys['aws_access_key']?.toString() ?? '',
        awsSecretKey: mergedApiKeys['aws_secret_key']?.toString() ?? '',
        awsRegion: settings.awsRegion,
        llmTemperature: settings.llmTemperature,
        onApiKeyChanged: (key, value) {
          setState(() {
            if (value.trim().isEmpty) {
              _apiKeyDraft.remove(key);
            } else {
              _apiKeyDraft[key] = value;
            }
          });
          unawaited(settings.updateApiKey(key, value));
        },
        onVisibilityChanged: (key, visible) {
          setState(() {
            _showApiKey[key] = visible;
          });
        },
        onAwsAccessKeyChanged: (value) {
          setState(() {
            _apiKeyDraft['aws_access_key'] = value;
          });
          unawaited(settings.updateApiKey('aws_access_key', value));
        },
        onAwsSecretKeyChanged: (value) {
          setState(() {
            _apiKeyDraft['aws_secret_key'] = value;
          });
          unawaited(settings.updateApiKey('aws_secret_key', value));
        },
        onAwsRegionChanged: (value) {
          if (value == null) return;
          unawaited(settings.updatePreference('awsRegion', value));
        },
        onTemperatureChanged: (value) {
          unawaited(settings.updatePreference('llmTemperature', value));
        },
      ),
      'Connectors': const IntegrationsPanel(),
      'Tools & MCP': McpPanel(
        n8nUrl: settings.localApiKeys['n8n_mcp_url'] ?? settings.serverConfig['n8nUrl'] ?? '',
        isConfigured: settings.apiKeyStatus['n8n_mcp'] == true ||
            (settings.localApiKeys['n8n_mcp_url'] ?? settings.serverConfig['n8nUrl'] ?? '').trim().isNotEmpty,
        connectorStatus: settings.connectorStatus,
        onN8nUrlChanged: (v) => settings.updateApiKey('n8n_mcp_url', v),
      ),
      'Developer': DeveloperPanel(
        isAdvancedMode: settings.isAdvancedMode,
        localApiKeys: settings.localApiKeys,
        apiKeyStatus: settings.apiKeyStatus,
        onAdvancedModeChanged: (v) => settings.updatePreference('isAdvancedMode', v),
        onApiKeyChanged: (k, v) => settings.updateApiKey(k, v),
        awsAccessKey: settings.localApiKeys['aws_access_key'] ?? '',
        awsSecretKey: settings.localApiKeys['aws_secret_key'] ?? '',
        awsRegion: settings.awsRegion,
        onAwsAccessKeyChanged: (v) => settings.updateApiKey('aws_access_key', v),
        onAwsSecretKeyChanged: (v) => settings.updateApiKey('aws_secret_key', v),
        onAwsRegionChanged: (v) => settings.updatePreference('awsRegion', v),
      ),
      'Account': const AccountPanel(),
    };
  }

  List<String> _getFilteredSections(SettingsProvider settings, List<String> allSections) {
    return allSections;
  }

  // ── Shared UI ──────────────────────────────────────────────────────────────

  Widget _buildHeader({required String title}) {
    return Container(
      height: 70,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      decoration: BoxDecoration(
        color: ZoyaTheme.sidebarBg.withValues(alpha: 0.3),
        border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
      ),
      child: Row(
        children: [
          Text(
            title.toUpperCase(),
            style: ZoyaTheme.fontDisplay.copyWith(
              color: ZoyaTheme.accent,
              fontSize: 18,
              fontWeight: FontWeight.bold,
              letterSpacing: 2.0,
            ),
          ),
          const Spacer(),
          IconButton(
            icon: const Icon(Icons.close, color: Colors.white70),
            onPressed: () => Navigator.pop(context),
          ),
        ],
      ),
    );
  }

  Widget _buildMobileSectionList(BoxConstraints constraints, List<String> sections) {
    return Column(
      key: const Key('settings_mobile_section_list'),
      children: [
        _buildHeader(title: 'Settings'),
        Expanded(
          child: ListView(
            children: sections
                .map(
                  (s) => ListTile(
                    key: Key('settings_section_tile_${_sectionKeyId(s)}'),
                    title: Text(s, style: const TextStyle(color: Colors.white)),
                    onTap: () => setState(() => _selectedSection = s),
                  ),
                )
                .toList(),
          ),
        ),
      ],
    );
  }

  Widget _buildMobileSectionPage(String section, List<String> sections, Map<String, Widget> panels) {
    return Column(
      key: const Key('settings_section_page'),
      children: [
        _buildMobileHeader(title: section),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: _panelForSection(section, sections, panels),
          ),
        ),
      ],
    );
  }

  Widget _buildMobileHeader({required String title}) {
    return Container(
      height: 70,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: ZoyaTheme.sidebarBg.withValues(alpha: 0.3),
        border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
      ),
      child: Row(
        children: [
          IconButton(
            key: const Key('settings_section_close'),
            icon: const Icon(Icons.arrow_back, color: Colors.white70),
            onPressed: () => setState(() => _selectedSection = null),
          ),
          const SizedBox(width: 4),
          Expanded(
            child: Text(
              title.toUpperCase(),
              style: ZoyaTheme.fontDisplay.copyWith(
                color: ZoyaTheme.accent,
                fontSize: 16,
                fontWeight: FontWeight.bold,
                letterSpacing: 1.5,
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.close, color: Colors.white70),
            onPressed: () => Navigator.pop(context),
          ),
        ],
      ),
    );
  }

  Widget _panelForSection(String section, List<String> sections, Map<String, Widget> panels) {
    final fallbackSection = sections.first;
    return panels[section] ?? panels[fallbackSection] ?? const SizedBox.shrink();
  }

  String _sectionKeyId(String section) {
    if (section == 'Tools & MCP') {
      return 'mcp-servers';
    }
    return section.toLowerCase().replaceAll(' & ', '-').replaceAll(' ', '-');
  }

  Future<void> _handleClearHistory(BuildContext context, SettingsProvider settings) async {
    final success = await settings.clearLocalConversationHistory();
    if (!context.mounted) {
      return;
    }
    _showFeedback(
      context,
      message: success ? 'Local conversation history cleared.' : 'Failed to clear local conversation history.',
      isError: !success,
    );
  }

  Future<void> _handleExportData(BuildContext context, SettingsProvider settings) async {
    try {
      final storageService = StorageService();
      final conversationHistory = await storageService.getConversationHistory();
      final payload = <String, dynamic>{
        'exportedAt': DateTime.now().toIso8601String(),
        'profile': <String, dynamic>{
          'userName': settings.userName,
          'userEmail': settings.userEmail,
          'preferredLanguage': settings.preferredLanguage,
        },
        'preferences': Map<String, dynamic>.from(settings.preferences),
        // Never export raw API key values; only export key identifiers and backend status.
        'apiKeyStatus': Map<String, dynamic>.from(settings.apiKeyStatus),
        'configuredApiKeyIds': settings.localApiKeys.keys.toList()..sort(),
        'connectors': settings.connectorStatus,
        'conversationHistory': conversationHistory,
      };

      final exportJson = const JsonEncoder.withIndent('  ').convert(payload);
      final timestamp = DateTime.now().toIso8601String().replaceAll(':', '-');
      final exportFile = File('${Directory.systemTemp.path}/maya_export_$timestamp.json');
      await exportFile.writeAsString(exportJson);

      await Clipboard.setData(ClipboardData(text: exportJson));
      if (!context.mounted) return;
      _showFeedback(
        context,
        message: 'Exported JSON to ${exportFile.path} and copied to clipboard.',
        isError: false,
      );
    } catch (e) {
      if (!context.mounted) return;
      _showFeedback(
        context,
        message: 'Failed to export data: $e',
        isError: true,
      );
    }
  }

  void _showFeedback(BuildContext context, {required String message, required bool isError}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? ZoyaTheme.danger : ZoyaTheme.success,
      ),
    );
  }
}
