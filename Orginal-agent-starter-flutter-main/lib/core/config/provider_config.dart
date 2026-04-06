import 'llm_config.dart';
import 'stt_config.dart';
import 'tts_config.dart';
import 'shared_config.dart';

class ProviderConfig {
  static List<Map<String, dynamic>> get llmProviders => LLMConfig.providersAsMaps;
  static List<Map<String, dynamic>> get sttProviders => STTConfig.providersAsMaps;
  static List<Map<String, dynamic>> get ttsProviders => TTSConfig.providersAsMaps;
  
  static List<Map<String, String>> get sttLanguages => STTConfig.languages;
  static List<Map<String, String>> get awsRegions => SharedConfig.awsRegions;
  static List<Map<String, String>> get preferredLanguages => SharedConfig.preferredLanguages;
  static List<Map<String, String>> get assistantPersonalities => SharedConfig.assistantPersonalities;

  // Helper methods
  static String getProviderName(String providerId, String type) {
    List<Map<String, dynamic>> providers;
    switch (type) {
      case 'llm':
        providers = llmProviders;
        break;
      case 'stt':
        providers = sttProviders;
        break;
      case 'tts':
        providers = ttsProviders;
        break;
      default:
        return providerId;
    }
    
    try {
      final provider = providers.firstWhere(
        (p) => p['id'] == providerId,
        orElse: () => {'name': providerId},
      );
      return provider['name'] as String;
    } catch (_) {
      return providerId;
    }
  }

  static List<String> getModelsForProvider(String providerId, String type) {
    List<Map<String, dynamic>> providers;
    switch (type) {
      case 'llm':
        providers = llmProviders;
        break;
      case 'stt':
        providers = sttProviders;
        break;
      default:
        return [];
    }
    
    try {
      final provider = providers.firstWhere(
        (p) => p['id'] == providerId,
        orElse: () => {'models': []},
      );
      return List<String>.from(provider['models'] ?? []);
    } catch (_) {
      return [];
    }
  }

  static List<String> getVoicesForProvider(String providerId) {
    try {
      final provider = ttsProviders.firstWhere(
        (p) => p['id'] == providerId,
        orElse: () => {'voices': []},
      );
      return List<String>.from(provider['voices'] ?? []);
    } catch (_) {
      return [];
    }
  }

  static String getVoiceDisplayLabel(String providerId, String voiceId) {
    if (providerId == 'elevenlabs') {
      return _elevenLabsVoiceLabels[voiceId] ?? voiceId;
    }
    return voiceId;
  }

  static const Map<String, String> _elevenLabsVoiceLabels = {
    '21m00Tcm4TlvDq8ikWAM': 'Rachel - Calm Narrator',
    'AZnzlk1XvdvUeBnXmlld': 'Domi - Strong Confident',
    'EXAVITQu4vr4xnSDxMaL': 'Sarah - Warm Conversational',
    'ErXwobaYiN019PkySvjV': 'Antoni - Deep Authoritative',
    'MF3mGyEYCl7XYWbV9V6O': 'Elli - Soft Friendly',
  };
}
