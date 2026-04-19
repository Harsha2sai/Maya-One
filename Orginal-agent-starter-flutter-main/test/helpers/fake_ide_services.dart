import 'dart:async';

import 'package:voice_assistant/core/services/ide_files_service.dart';
import 'package:voice_assistant/core/services/ide_terminal_service.dart';

class FakeIdeFilesService extends IdeFilesService {
  FakeIdeFilesService({
    Map<String, List<IdeFilesEntry>>? directories,
    Map<String, String>? files,
  })  : _directories = directories ??
            <String, List<IdeFilesEntry>>{
              '': <IdeFilesEntry>[
                IdeFilesEntry(name: 'src', path: 'src', isDir: true, size: 0),
                IdeFilesEntry(name: 'README.md', path: 'README.md', isDir: false, size: 20),
              ],
              'src': <IdeFilesEntry>[
                IdeFilesEntry(name: 'main.dart', path: 'src/main.dart', isDir: false, size: 60),
              ],
            },
        _files = files ??
            <String, String>{
              'README.md': '# Maya-One\n',
              'src/main.dart': 'void main() {}\n',
            },
        super();

  final Map<String, List<IdeFilesEntry>> _directories;
  final Map<String, String> _files;

  String _sessionId = 'sess-1';
  IdeFilesError? writeFailure;

  @override
  Future<String> openIdeSession({required String userId, required String workspacePath}) async {
    _sessionId = 'sess-${DateTime.now().microsecondsSinceEpoch}';
    return _sessionId;
  }

  @override
  Future<void> closeIdeSession({required String sessionId}) async {}

  @override
  Future<IdeDirectorySnapshot> listDirectory({
    required String sessionId,
    required String relativePath,
  }) async {
    return IdeDirectorySnapshot(
      sessionId: _sessionId,
      path: relativePath,
      entries: List<IdeFilesEntry>.from(_directories[relativePath] ?? const <IdeFilesEntry>[]),
    );
  }

  @override
  Future<IdeFileDocument> readFile({
    required String sessionId,
    required String relativePath,
  }) async {
    if (!_files.containsKey(relativePath)) {
      throw IdeFilesError(statusCode: 400, message: 'File not found: $relativePath');
    }
    final content = _files[relativePath] ?? '';
    return IdeFileDocument(
      sessionId: _sessionId,
      path: relativePath,
      originalContent: content,
      draftContent: content,
    );
  }

  @override
  Future<IdeWriteResult> writeFile({
    required String sessionId,
    required String relativePath,
    required String content,
  }) async {
    final error = writeFailure;
    if (error != null) {
      throw error;
    }

    _files[relativePath] = content;
    return IdeWriteResult(
      sessionId: _sessionId,
      path: relativePath,
      lastSavedAt: DateTime.now().toUtc(),
    );
  }

  @override
  Future<void> dispose() async {}

  String? readCachedFile(String path) => _files[path];
}

class FakeIdeTerminalService extends IdeTerminalService {
  FakeIdeTerminalService() : super();

  final StreamController<String> _output = StreamController<String>.broadcast(sync: true);
  final StreamController<IdeTerminalStatus> _status = StreamController<IdeTerminalStatus>.broadcast(sync: true);

  IdeTerminalStatus _currentStatus = IdeTerminalStatus.idle;

  @override
  Stream<String> get outputStream => _output.stream;

  @override
  Stream<IdeTerminalStatus> get statusStream => _status.stream;

  @override
  IdeTerminalStatus get status => _currentStatus;

  @override
  String? get lastError => null;

  @override
  Future<void> start({required String userId, required String workspacePath, String cwd = '~'}) async {
    _currentStatus = IdeTerminalStatus.connected;
    _status.add(_currentStatus);
  }

  @override
  Future<void> stop() async {
    _currentStatus = IdeTerminalStatus.closed;
    _status.add(_currentStatus);
  }

  @override
  Future<void> sendInput(String input) async {}

  @override
  Future<void> sendResize({required int rows, required int cols}) async {}

  @override
  Future<void> dispose() async {
    await _output.close();
    await _status.close();
  }
}
