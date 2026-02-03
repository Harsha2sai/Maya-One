import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

class StorageService {
  static const _settingsKey = 'app_settings';
  static const _conversationHistoryKey = 'conversation_history';

  /// Get app settings
  Future<Map<String, dynamic>?> getSettings() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_settingsKey);
      if (jsonString != null) {
        return jsonDecode(jsonString) as Map<String, dynamic>;
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  /// Save app settings
  Future<bool> saveSettings(Map<String, dynamic> settings) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = jsonEncode(settings);
      return await prefs.setString(_settingsKey, jsonString);
    } catch (e) {
      return false;
    }
  }

  /// Get conversation history
  Future<List<String>> getConversationHistory() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getStringList(_conversationHistoryKey) ?? [];
    } catch (e) {
      return [];
    }
  }

  /// Save conversation history
  Future<bool> saveConversationHistory(List<String> history) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return await prefs.setStringList(_conversationHistoryKey, history);
    } catch (e) {
      return false;
    }
  }

  /// Clear all stored data
  Future<bool> clearAll() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return await prefs.clear();
    } catch (e) {
      return false;
    }
  }
}
