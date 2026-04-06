import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

import '../../state/models/conversation_models.dart';

class StorageService {
  static const _settingsKey = 'app_settings';
  static const _conversationHistoryKey = 'conversation_history';
  static const _conversationStoreKey = 'conversation_store_v1';
  static const _conversationMigrationCompleteKey = 'conversation_store_v1_migration_complete';

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

  Future<ConversationStoreSnapshot?> loadConversationStore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_conversationStoreKey);
      if (jsonString == null || jsonString.trim().isEmpty) {
        return null;
      }
      final decoded = jsonDecode(jsonString);
      if (decoded is! Map) {
        return null;
      }
      return ConversationStoreSnapshot.fromJson(decoded.cast<String, dynamic>());
    } catch (e) {
      return null;
    }
  }

  Future<bool> saveConversationStore(ConversationStoreSnapshot store) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return await prefs.setString(_conversationStoreKey, store.toJsonString());
    } catch (e) {
      return false;
    }
  }

  Future<bool> hasConversationStore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.containsKey(_conversationStoreKey);
    } catch (e) {
      return false;
    }
  }

  Future<bool> isConversationMigrationComplete() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool(_conversationMigrationCompleteKey) ?? false;
    } catch (e) {
      return false;
    }
  }

  Future<bool> setConversationMigrationComplete(bool value) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return await prefs.setBool(_conversationMigrationCompleteKey, value);
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
