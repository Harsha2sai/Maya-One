import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureKeyStorageService {
  static const String _apiKeysBlobKey = 'secure_api_keys_v1';

  final FlutterSecureStorage _storage;

  SecureKeyStorageService({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  Future<Map<String, String>> loadApiKeys() async {
    final raw = await _storage.read(key: _apiKeysBlobKey);
    if (raw == null || raw.isEmpty) {
      return {};
    }

    final decoded = jsonDecode(raw);
    if (decoded is! Map) {
      return {};
    }

    return decoded.map(
      (key, value) => MapEntry(key.toString(), value?.toString() ?? ''),
    );
  }

  Future<void> saveApiKeys(Map<String, String> keys) async {
    final sanitized = <String, String>{};
    keys.forEach((key, value) {
      final trimmedKey = key.trim();
      final trimmedValue = value.trim();
      if (trimmedKey.isNotEmpty && trimmedValue.isNotEmpty) {
        sanitized[trimmedKey] = trimmedValue;
      }
    });

    if (sanitized.isEmpty) {
      await _storage.delete(key: _apiKeysBlobKey);
      return;
    }

    await _storage.write(key: _apiKeysBlobKey, value: jsonEncode(sanitized));
  }

  Future<void> removeApiKey(String key) async {
    final current = await loadApiKeys();
    current.remove(key);
    await saveApiKeys(current);
  }

  Future<void> clearApiKeys() async {
    await _storage.delete(key: _apiKeysBlobKey);
  }
}
