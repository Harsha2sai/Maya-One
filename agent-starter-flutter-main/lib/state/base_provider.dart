import 'package:flutter/foundation.dart';
import 'package:logging/logging.dart';

/// Base class for all providers with common functionality
/// Provides error handling, loading states, and logging
abstract class BaseProvider extends ChangeNotifier {
  final Logger _logger;
  bool _disposed = false;
  bool _loading = false;
  String? _error;

  BaseProvider(String loggerName) : _logger = Logger(loggerName);

  bool get loading => _loading;
  String? get error => _error;
  bool get hasError => _error != null;

  @protected
  void setLoading(bool value) {
    if (_disposed) return;
    _loading = value;
    notifyListeners();
  }

  @protected
  void setError(String? error) {
    if (_disposed) return;
    _error = error;
    if (error != null) {
      _logger.severe('Error: $error');
    }
    notifyListeners();
  }

  @protected
  void clearError() {
    setError(null);
  }

  @protected
  void log(String message, {Level level = Level.INFO}) {
    _logger.log(level, message);
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  /// Execute an async action with automatic error handling and loading states
  @protected
  Future<T?> safeExecute<T>(Future<T> Function() action) async {
    try {
      setLoading(true);
      clearError();
      final result = await action();
      return result;
    } catch (e, stackTrace) {
      setError(e.toString());
      _logger.severe('Action failed', e, stackTrace);
      return null;
    } finally {
      setLoading(false);
    }
  }
}
