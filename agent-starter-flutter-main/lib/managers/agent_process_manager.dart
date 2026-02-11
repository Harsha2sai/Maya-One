import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';

/// Manages the lifecycle of the Python Agent backend process.
/// This allows the Flutter app to automatically start and stop the agent.
class AgentProcessManager {
  static final AgentProcessManager _instance = AgentProcessManager._internal();
  factory AgentProcessManager() => _instance;
  AgentProcessManager._internal();

  Process? _agentProcess;
  bool _isRunning = false;
  final List<String> _logs = [];
  
  // Callbacks for UI updates
  Function(String)? onLog;
  Function(bool)? onStatusChange;

  /// Configuration - adjust these paths for your system
  static const String pythonPath = '/home/harsha/Downloads/projects/LIveKIt/version 2/LIVEKIT vvv2/Agent/venv/bin/python';
  static const String agentScriptPath = '/home/harsha/Downloads/projects/LIveKIt/version 2/LIVEKIT vvv2/Agent/agent.py';
  static const String workingDirectory = '/home/harsha/Downloads/projects/LIveKIt/version 2/LIVEKIT vvv2/Agent';

  bool get isRunning => _isRunning;
  List<String> get logs => List.unmodifiable(_logs);

  /// Starts the Python agent process
  Future<bool> startAgent() async {
    if (_isRunning) {
      _log('[AgentManager] Agent is already running.');
      return true;
    }

    // Check if Python and script exist
    if (!await File(pythonPath).exists()) {
      _log('[AgentManager] ERROR: Python not found at $pythonPath');
      return false;
    }
    if (!await File(agentScriptPath).exists()) {
      _log('[AgentManager] ERROR: Agent script not found at $agentScriptPath');
      return false;
    }

    _log('[AgentManager] Starting Python agent...');

    try {
      _agentProcess = await Process.start(
        pythonPath,
        [agentScriptPath, 'dev'], // 'dev' mode for development
        workingDirectory: workingDirectory,
        environment: Platform.environment, // Inherit environment variables
      );

      _isRunning = true;
      onStatusChange?.call(true);
      _log('[AgentManager] Agent process started (PID: ${_agentProcess!.pid})');

      // Listen to stdout
      _agentProcess!.stdout.transform(const SystemEncoding().decoder).listen((data) {
        for (var line in data.split('\n')) {
          if (line.trim().isNotEmpty) {
            _log('[Agent] $line');
          }
        }
      });

      // Listen to stderr
      _agentProcess!.stderr.transform(const SystemEncoding().decoder).listen((data) {
        for (var line in data.split('\n')) {
          if (line.trim().isNotEmpty) {
            _log('[Agent ERR] $line');
          }
        }
      });

      // Handle process exit
      _agentProcess!.exitCode.then((exitCode) {
        _log('[AgentManager] Agent process exited with code $exitCode');
        _isRunning = false;
        _agentProcess = null;
        onStatusChange?.call(false);
      });

      return true;
    } catch (e) {
      _log('[AgentManager] Failed to start agent: $e');
      _isRunning = false;
      return false;
    }
  }

  /// Stops the Python agent process gracefully
  Future<void> stopAgent() async {
    if (!_isRunning || _agentProcess == null) {
      _log('[AgentManager] Agent is not running.');
      return;
    }

    _log('[AgentManager] Stopping agent (PID: ${_agentProcess!.pid})...');

    try {
      // Send SIGTERM for graceful shutdown
      _agentProcess!.kill(ProcessSignal.sigterm);
      
      // Wait up to 5 seconds for graceful shutdown
      bool exited = false;
      for (int i = 0; i < 10; i++) {
        await Future.delayed(const Duration(milliseconds: 500));
        try {
          // Check if process still exists by sending signal 0
          Process.runSync('kill', ['-0', _agentProcess!.pid.toString()]);
        } catch (e) {
          exited = true;
          break;
        }
      }

      // Force kill if still running
      if (!exited) {
        _log('[AgentManager] Force killing agent...');
        _agentProcess!.kill(ProcessSignal.sigkill);
      }

      _isRunning = false;
      _agentProcess = null;
      onStatusChange?.call(false);
      _log('[AgentManager] Agent stopped.');
    } catch (e) {
      _log('[AgentManager] Error stopping agent: $e');
    }
  }

  /// Restarts the agent
  Future<bool> restartAgent() async {
    await stopAgent();
    await Future.delayed(const Duration(seconds: 1));
    return startAgent();
  }

  void _log(String message) {
    final timestamp = DateTime.now().toIso8601String().substring(11, 19);
    final logLine = '[$timestamp] $message';
    _logs.add(logLine);
    
    // Keep only last 500 lines
    if (_logs.length > 500) {
      _logs.removeAt(0);
    }
    
    debugPrint(logLine);
    onLog?.call(logLine);
  }

  /// Clears all logs
  void clearLogs() {
    _logs.clear();
  }
}
