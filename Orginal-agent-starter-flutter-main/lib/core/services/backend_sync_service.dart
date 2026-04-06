import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:logging/logging.dart';

class BackendSyncService {
  final Logger _logger = Logger('BackendSyncService');
  final String _baseUrl = 'http://127.0.0.1:5050';

  /// Fetch API key status from the agent backend (shows configured/masked keys)
  Future<Map<String, dynamic>> fetchApiKeyStatus() async {
    try {
      final response = await http
          .get(
            Uri.parse('$_baseUrl/api-keys/status'),
          )
          .timeout(const Duration(seconds: 5));

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
      final response = await http
          .post(
            Uri.parse('$_baseUrl/api-keys'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(data),
          )
          .timeout(const Duration(seconds: 5));

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

  /// Polls the backend until it is ready or times out
  Future<void> waitForBackend() async {
    final url = '$_baseUrl/api-keys/status';

    for (int i = 0; i < 30; i++) {
      try {
        final res = await http.get(Uri.parse(url));
        if (res.statusCode == 200) {
          _logger.info('Backend ready');
          return;
        }
      } catch (_) {}

      await Future.delayed(const Duration(seconds: 1));
    }

    throw Exception('Backend never started');
  }
}
