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
    try {
      final response = await _supabaseService.client
          .from('user_profiles')
          .select('preferences')
          .eq('id', userId)
          .maybeSingle();

      if (response != null && response['preferences'] != null) {
        return response['preferences'] as Map<String, dynamic>;
      }
    } catch (e) {
      _logger.severe('Error fetching user settings from Supabase: $e');
    }
    return null;
  }

  Future<void> updateUserSettings(String userId, Map<String, dynamic> settings) async {
    try {
      await _supabaseService.client
          .from('user_profiles')
          .upsert({
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
