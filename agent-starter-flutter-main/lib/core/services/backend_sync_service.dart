import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:logging/logging.dart';

class BackendSyncService {
  final Logger _logger = Logger('BackendSyncService');
  final String _baseUrl = 'http://localhost:5050';

  /// Fetch API key status from the agent backend (shows configured/masked keys)
  Future<Map<String, dynamic>> fetchApiKeyStatus() async {
    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/api-keys/status'),
      ).timeout(const Duration(seconds: 2));
      
      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      } else {
        _logger.warning('Failed to fetch API key status: ${response.statusCode}');
      }
    } catch (e) {
      _logger.warning('Could not connect to agent backend: $e');
    }
    return {};
  }

  /// Sync API keys or configuration to the agent backend
  Future<Map<String, dynamic>> syncToBackend(Map<String, dynamic> data) async {
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api-keys'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(data),
      ).timeout(const Duration(seconds: 5));
      
      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      } else {
        _logger.severe('Failed to sync to backend: ${response.statusCode}');
      }
    } catch (e) {
      _logger.severe('Error syncing to backend: $e');
    }
    return {'success': false, 'error': 'Connection failed'};
  }

  /// Specialized method for syncing API keys
  Future<bool> syncApiKeys(Map<String, String> apiKeys) async {
    final result = await syncToBackend({'apiKeys': apiKeys});
    return result['success'] == true;
  }

  /// Specialized method for syncing general config
  Future<bool> syncConfig(Map<String, String> config) async {
    final result = await syncToBackend({'config': config});
    return result['success'] == true;
  }
}
