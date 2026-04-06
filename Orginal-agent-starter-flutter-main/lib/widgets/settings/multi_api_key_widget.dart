import 'dart:async';
import 'package:flutter/material.dart';
import '../../ui/theme/app_theme.dart';
import '../common/shared_widgets.dart';
import 'package:google_sign_in/google_sign_in.dart';

/// Configuration for a provider that supports multiple API key slots.
class MultiKeyProviderConfig {
  /// Display name, e.g. "Groq"
  final String displayName;

  /// Base provider id, e.g. "groq"
  final String providerId;

  /// Number of key slots (1 = regular single-key, 2+ = expandable multi-key)
  final int slotCount;

  /// Whether an active-slot selector is shown
  final bool hasActiveSlotSelector;

  /// Whether backend runtime actually honors the selected active slot.
  final bool runtimeSlotAware;

  const MultiKeyProviderConfig({
    required this.displayName,
    required this.providerId,
    this.slotCount = 1,
    this.hasActiveSlotSelector = false,
    this.runtimeSlotAware = false,
  });

  /// Internal key name for slot [slot] (1-indexed).
  /// Slot 1 → providerId,  Slot 2 → "${providerId}_2", etc.
  String slotKey(int slot) => slot == 1 ? providerId : '${providerId}_${slot}';

  /// Internal key name for the active-slot preference.
  String get activeSlotKey => '${providerId}_active_slot';
}

// ─────────────────────────────────────────────────────────────────────────────

class MultiApiKeyWidget extends StatefulWidget {
  final MultiKeyProviderConfig config;
  final Map<String, dynamic> apiKeys;
  final Map<String, bool> showApiKey;
  final Map<String, dynamic> apiStatus;
  final Map<String, String> maskedApiKeys;
  final Function(String, String) onApiKeyChanged;
  final Function(String, bool) onVisibilityChanged;

  const MultiApiKeyWidget({
    super.key,
    required this.config,
    required this.apiKeys,
    required this.showApiKey,
    required this.apiStatus,
    required this.maskedApiKeys,
    required this.onApiKeyChanged,
    required this.onVisibilityChanged,
  });

  @override
  State<MultiApiKeyWidget> createState() => _MultiApiKeyWidgetState();
}

class _MultiApiKeyWidgetState extends State<MultiApiKeyWidget> {
  static const List<String> _googleScopes = <String>[
    'email',
    'https://www.googleapis.com/auth/cloud-platform',
  ];
  static final GoogleSignIn _googleSignIn = GoogleSignIn.instance;
  static Future<void>? _googleSignInInitialization;

  bool _expanded = false;
  late int _currentSlotCount;

  @override
  void initState() {
    super.initState();
    _initSlotCount();
    unawaited(_attemptSilentRefresh());
  }

  Future<void> _attemptSilentRefresh() async {
    final cfg = widget.config;
    if (cfg.providerId == 'gemini') {
      try {
        final googleSignIn = await _ensureGoogleSignInInitialized();
        final attempt = googleSignIn.attemptLightweightAuthentication();
        if (attempt == null) {
          return;
        }
        final account = await attempt;
        if (account != null) {
          final token = await _requestGoogleAccessToken(
            account,
            promptIfNecessary: false,
          );
          if (token == null || token.isEmpty) {
            return;
          }

          for (int i = 1; i <= _currentSlotCount; i++) {
            final key = cfg.slotKey(i);
            final currentVal = widget.apiKeys[key] ?? '';
            if (currentVal.startsWith('OAUTH:')) {
              widget.onApiKeyChanged(key, 'OAUTH:$token');
            }
          }
        }
      } catch (e) {
        debugPrint('Silent refresh failed: $e');
      }
    }
  }

  Future<void> _handleGoogleSignIn(int slot) async {
    try {
      final googleSignIn = await _ensureGoogleSignInInitialized();
      if (!googleSignIn.supportsAuthenticate()) {
        _showSnackBar(
          'Google Sign-In is not supported on this platform. Use the Gemini API key field instead.',
          isError: true,
        );
        return;
      }

      final account = await googleSignIn.authenticate(scopeHint: _googleScopes);
      final token = await _requestGoogleAccessToken(
        account,
        promptIfNecessary: true,
      );
      if (token == null || token.isEmpty) {
        _showSnackBar(
          'Google account authenticated, but no access token was granted for the required scope.',
          isError: true,
        );
        return;
      }

      widget.onApiKeyChanged(cfg.slotKey(slot), 'OAUTH:$token');
      _showSnackBar(
        'Successfully authenticated with Google as ${account.email}',
      );
    } catch (error) {
      _showSnackBar('Sign in failed: $error', isError: true);
    }
  }

  Future<GoogleSignIn> _ensureGoogleSignInInitialized() async {
    _googleSignInInitialization ??= _googleSignIn.initialize();
    await _googleSignInInitialization;
    return _googleSignIn;
  }

  Future<String?> _requestGoogleAccessToken(
    GoogleSignInAccount account, {
    required bool promptIfNecessary,
  }) async {
    final headers = await account.authorizationClient.authorizationHeaders(
      _googleScopes,
      promptIfNecessary: promptIfNecessary,
    );
    if (headers == null) {
      return null;
    }

    final authorization = headers['Authorization'] ?? headers['authorization'];
    if (authorization == null) {
      return null;
    }

    const bearerPrefix = 'Bearer ';
    if (!authorization.startsWith(bearerPrefix)) {
      return null;
    }
    return authorization.substring(bearerPrefix.length).trim();
  }

  void _showSnackBar(String message, {bool isError = false}) {
    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Colors.redAccent : ZoyaTheme.success,
      ),
    );
  }

  @override
  void didUpdateWidget(MultiApiKeyWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    _initSlotCount();
  }

  void _initSlotCount() {
    final rawCount = widget.apiKeys['${cfg.providerId}_slot_count'];
    final savedCount = (rawCount != null) ? int.tryParse(rawCount.toString()) : null;
    _currentSlotCount = savedCount ?? cfg.slotCount;
  }

  void _updateSlotCount(int newCount) {
    setState(() => _currentSlotCount = newCount);
    // Tell SettingsProvider to save this generic key, which will sync to .env
    widget.onApiKeyChanged('${cfg.providerId}_slot_count', newCount.toString());
  }

  MultiKeyProviderConfig get cfg => widget.config;

  int get _activeSlot {
    final raw = widget.apiKeys[cfg.activeSlotKey];
    return (raw is int) ? raw : int.tryParse(raw?.toString() ?? '') ?? 1;
  }

  bool _isSlotConfigured(int slot) => widget.apiStatus[cfg.slotKey(slot)] == true;

  bool get _anyConfigured => List.generate(_currentSlotCount, (i) => i + 1).any(_isSlotConfigured);

  void _activateSlot(int slot) {
    widget.onApiKeyChanged(cfg.activeSlotKey, slot.toString());
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    // Render all LLM providers as multi-key expandable cards
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Container(
        decoration: BoxDecoration(
          color: ZoyaTheme.accent.withValues(alpha: 0.04),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: _anyConfigured ? ZoyaTheme.success.withValues(alpha: 0.35) : Colors.white.withValues(alpha: 0.08),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Header row (always visible) ─────────────────────────────
            InkWell(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
              onTap: () => setState(() => _expanded = !_expanded),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
                child: Row(
                  children: [
                    // Status dot
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: _anyConfigured ? ZoyaTheme.success : Colors.white24,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            cfg.displayName,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${_countConfigured()} / $_currentSlotCount keys configured'
                            '${cfg.hasActiveSlotSelector ? '  •  Active: Slot $_activeSlot' : ''}'
                            '${cfg.runtimeSlotAware ? '  •  Runtime slot-aware' : ''}',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.45),
                              fontSize: 11,
                            ),
                          ),
                          if (cfg.runtimeSlotAware)
                            Padding(
                              padding: const EdgeInsets.only(top: 2),
                              child: Text(
                                'Inactive configured slots are fallback.',
                                style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.38),
                                  fontSize: 10,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                    Icon(
                      _expanded ? Icons.expand_less : Icons.expand_more,
                      color: Colors.white38,
                      size: 20,
                    ),
                  ],
                ),
              ),
            ),

            // ── Slot 1 (always visible inside the card) ─────────────────
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: _buildSlotField(1, label: 'Key 1 (Primary)'),
            ),

            // ── Expandable body: slots 2…N + slot selector ───────────────
            AnimatedCrossFade(
              firstChild: const SizedBox.shrink(),
              secondChild: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ...List.generate(
                      _currentSlotCount - 1,
                      (i) => Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: _buildSlotField(i + 2, label: 'Key ${i + 2}'),
                      ),
                    ),
                    if (_currentSlotCount < 5)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: TextButton.icon(
                          onPressed: () => _updateSlotCount(_currentSlotCount + 1),
                          icon: const Icon(Icons.add, size: 16),
                          label: const Text('Add Key Slot'),
                          style: TextButton.styleFrom(
                            foregroundColor: ZoyaTheme.accent,
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              crossFadeState: _expanded ? CrossFadeState.showSecond : CrossFadeState.showFirst,
              duration: const Duration(milliseconds: 220),
            ),
          ],
        ),
      ),
    );
  }

  int _countConfigured() => List.generate(_currentSlotCount, (i) => i + 1).where(_isSlotConfigured).length;

  Widget _buildSlotField(int slot, {String? label}) {
    final key = cfg.slotKey(slot);
    final isVisible = widget.showApiKey[key] ?? false;
    final masked = widget.maskedApiKeys[key] ?? '';
    final isConfigured = widget.apiStatus[key] == true;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (label != null)
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: 8,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(
                    label,
                    style: const TextStyle(color: Colors.white60, fontSize: 12),
                  ),
                  if (_currentSlotCount > 1 && slot > 1)
                    InkWell(
                      onTap: () => _confirmDeleteSlot(slot),
                      borderRadius: BorderRadius.circular(4),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                        child: Text(
                          'REMOVE',
                          style: TextStyle(
                            color: Colors.redAccent.withValues(alpha: 0.8),
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 6),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  if (cfg.hasActiveSlotSelector) _buildActivateButton(slot),
                  buildStatusBadge(isConfigured),
                ],
              ),
            ],
          ),
        if (label != null) const SizedBox(height: 6),
        GestureDetector(
          onLongPress: _currentSlotCount > 1 ? () => _confirmDeleteSlot(slot) : null,
          child: Tooltip(
            message: _currentSlotCount > 1 ? 'Long press to delete this slot' : '',
            child: TextField(
              obscureText: !isVisible,
              onChanged: (val) => widget.onApiKeyChanged(key, val),
              style: const TextStyle(color: Colors.white, fontSize: 14),
              decoration: InputDecoration(
                hintText:
                    (cfg.providerId == 'gemini' && masked.isNotEmpty && !masked.contains('*') && masked.length > 20)
                        ? 'Authenticated via Google'
                        : (masked.isNotEmpty ? masked : 'Enter API Key for slot $slot'),
                hintStyle: TextStyle(
                  color: masked.isNotEmpty ? ZoyaTheme.success.withValues(alpha: 0.55) : Colors.white24,
                  fontFamily: 'monospace',
                  fontSize: 13,
                ),
                filled: true,
                fillColor: Colors.white.withValues(alpha: 0.05),
                suffixIcon: IconButton(
                  icon: Icon(
                    isVisible ? Icons.visibility_off : Icons.visibility,
                    color: Colors.white30,
                    size: 18,
                  ),
                  onPressed: () => widget.onVisibilityChanged(key, !isVisible),
                ),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                  borderSide: BorderSide.none,
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
              ),
            ),
          ),
        ),
        if (cfg.providerId == 'gemini') ...[
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            height: 36,
            child: ElevatedButton.icon(
              onPressed: () => _handleGoogleSignIn(slot),
              style: ElevatedButton.styleFrom(
                backgroundColor: isConfigured ? Colors.white.withValues(alpha: 0.1) : Colors.white,
                foregroundColor: isConfigured ? Colors.white : Colors.black87,
                elevation: 0,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              icon: Icon(
                Icons.g_mobiledata,
                size: 28,
                color: isConfigured ? Colors.white70 : const Color(0xFF4285F4),
              ),
              label: Text(
                isConfigured ? 'Re-authenticate with Google' : 'Sign in with Google',
                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
              ),
            ),
          ),
        ],
      ],
    );
  }

  void _confirmDeleteSlot(int slot) {
    unawaited(
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: const Color(0xFF1E1E2E), // ZoyaTheme.surface doesn't exist, using dark surface
          title: const Text('Delete Slot?', style: TextStyle(color: Colors.white)),
          content: Text(
            'Are you sure you want to remove Key Slot $slot? This will delete the key from the backend.',
            style: const TextStyle(color: Colors.white70),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel', style: TextStyle(color: Colors.white54)),
            ),
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                _deleteSlot(slot);
              },
              child: const Text('Delete', style: TextStyle(color: Colors.redAccent)),
            ),
          ],
        ),
      ),
    );
  }

  void _deleteSlot(int deletedSlot) {
    // We send an empty string to the backend to "delete" the key.
    widget.onApiKeyChanged(cfg.slotKey(deletedSlot), '');

    // Decrease the count
    _updateSlotCount(_currentSlotCount - 1);

    // Optional: If you delete the *active* slot, maybe fallback to slot 1?
    if (_activeSlot == deletedSlot) {
      widget.onApiKeyChanged(cfg.activeSlotKey, '1');
    }
  }

  Widget _buildActivateButton(int slot) {
    final isActive = slot == _activeSlot;
    if (isActive) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: ZoyaTheme.accent.withValues(alpha: 0.20),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: ZoyaTheme.accent.withValues(alpha: 0.45)),
        ),
        child: Text(
          'ACTIVE',
          style: TextStyle(
            color: ZoyaTheme.accent,
            fontSize: 10,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.6,
          ),
        ),
      );
    }

    return SizedBox(
      height: 28,
      child: OutlinedButton(
        onPressed: () => _activateSlot(slot),
        style: OutlinedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          side: BorderSide(color: Colors.white.withValues(alpha: 0.28)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          foregroundColor: Colors.white70,
          textStyle: const TextStyle(fontSize: 10, fontWeight: FontWeight.w600),
        ),
        child: const Text('Activate'),
      ),
    );
  }
}
