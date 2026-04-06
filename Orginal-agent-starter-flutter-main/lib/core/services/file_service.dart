import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:flutter/foundation.dart';

class FileService {
  final String baseUrl;

  FileService({this.baseUrl = 'http://localhost:5050'});

  Future<String?> uploadFile(File file) async {
    try {
      final uri = Uri.parse('$baseUrl/upload');
      final request = http.MultipartRequest('POST', uri);

      final fileStream = http.MultipartFile.fromBytes(
        'file',
        await file.readAsBytes(),
        filename: file.path.split('/').last,
      );

      request.files.add(fileStream);

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return data['url'];
      } else {
        debugPrint('Upload failed: ${response.statusCode} / ${response.body}');
        return null;
      }
    } catch (e) {
      debugPrint('Upload error: $e');
      return null;
    }
  }
}
