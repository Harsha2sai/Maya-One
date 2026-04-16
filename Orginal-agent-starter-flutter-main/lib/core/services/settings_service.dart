import 'dart:async';
import 'package:logging/logging.dart';
import 'supabase_service.dart';
import '../config/provider_config.dart';

class SettingsService {
  final Logger _logger = Logger('SettingsService');
  final SupabaseService _supabaseService;

  SettingsService(this._supabaseService);

  /// Fetch available providers and defaults from the local configuration
  /// This replaces the legacy API call
  Future<Map<String, dynamic>> fetchServerConfig() async {
    // Return local configuration immediately
    return {
      'providers': {
        'llm': ProviderConfig.llmProviders.map((p) => Map<String, dynamic>.from(p)).toList(),
        'stt': ProviderConfig.sttProviders.map((p) => Map<String, dynamic>.from(p)).toList(),
        'tts': ProviderConfig.ttsProviders.map((p) => Map<String, dynamic>.from(p)).toList(),
      },
      'apiKeyStatus': <String, dynamic>{}, // Client-side handled
    };
  }

  /// Sync settings with Supabase user_profiles table
  Future<Map<String, dynamic>?> fetchUserSettings(String userId) async {
    if (!_supabaseService.isAvailable) {
      _logger.info('Supabase unavailable; skipping remote user settings fetch');
      return null;
    }

    try {
      final response = await _supabaseService.client
          .from('user_profiles')
          .select('preferences')
          .eq('id', userId)
          .maybeSingle()
          .timeout(const Duration(seconds: 6));

      if (response != null && response['preferences'] != null) {
        return response['preferences'] as Map<String, dynamic>;
      }
    } on TimeoutException {
      _logger.warning('Timed out fetching user settings from Supabase; using local defaults');
    } catch (e) {
      _logger.severe('Error fetching user settings from Supabase: $e');
    }
    return null;
  }

  Future<void> updateUserSettings(String userId, Map<String, dynamic> settings) async {
    if (!_supabaseService.isAvailable) {
      _logger.info('Supabase unavailable; skipping remote user settings update');
      return;
    }

    try {
      await _supabaseService.client.from('user_profiles').upsert({
        'id': userId,
        'preferences': settings,
        'updated_at': DateTime.now().toIso8601String(),
      });
    } catch (e) {
      _logger.severe('Error updating user settings in Supabase: $e');
      rethrow;
    }
  }
}
