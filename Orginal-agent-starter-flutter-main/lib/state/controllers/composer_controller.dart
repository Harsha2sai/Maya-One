import 'dart:io';

import 'package:flutter/widgets.dart';

enum VoiceInputMode {
  pushToTalk,
  continuous,
}

class ComposerController extends ChangeNotifier {
  final List<File> _attachments = <File>[];
  bool _isUploading = false;
  bool _isSending = false;
  VoiceInputMode _voiceMode = VoiceInputMode.pushToTalk;
  bool _composerRevealed = true;
  final TextEditingController _textController = TextEditingController();
  final FocusNode _focusNode = FocusNode();

  TextEditingController get textController => _textController;
  FocusNode get focusNode => _focusNode;
  String get draftText => _textController.text;
  List<File> get attachments => List.unmodifiable(_attachments);
  bool get isUploading => _isUploading;
  bool get isSending => _isSending;
  VoiceInputMode get voiceMode => _voiceMode;
  bool get composerRevealed => _composerRevealed;

  void setDraftText(String value) {
    if (_textController.text == value) {
      return;
    }
    _textController.value = _textController.value.copyWith(
      text: value,
      selection: TextSelection.collapsed(offset: value.length),
      composing: TextRange.empty,
    );
    notifyListeners();
  }

  void clearDraft() {
    if (_textController.text.isEmpty) {
      return;
    }
    _textController.clear();
    notifyListeners();
  }

  void addAttachment(File file) {
    final exists = _attachments.any((attachment) => attachment.path == file.path);
    if (exists) {
      return;
    }
    _attachments.add(file);
    notifyListeners();
  }

  void removeAttachment(File file) {
    final hadAttachment = _attachments.any((attachment) => attachment.path == file.path);
    _attachments.removeWhere((attachment) => attachment.path == file.path);
    if (hadAttachment) {
      notifyListeners();
    }
  }

  void clearAttachments() {
    if (_attachments.isEmpty) {
      return;
    }
    _attachments.clear();
    notifyListeners();
  }

  void setUploading(bool value) {
    if (_isUploading == value) {
      return;
    }
    _isUploading = value;
    notifyListeners();
  }

  void setSending(bool value) {
    if (_isSending == value) {
      return;
    }
    _isSending = value;
    notifyListeners();
  }

  void setVoiceMode(VoiceInputMode mode) {
    if (_voiceMode == mode) {
      return;
    }
    _voiceMode = mode;
    notifyListeners();
  }

  void toggleVoiceMode() {
    setVoiceMode(
      _voiceMode == VoiceInputMode.pushToTalk ? VoiceInputMode.continuous : VoiceInputMode.pushToTalk,
    );
  }

  void setComposerRevealed(bool value) {
    if (_composerRevealed == value) {
      return;
    }
    _composerRevealed = value;
    notifyListeners();
  }

  void revealComposer({bool requestFocus = false}) {
    var changed = false;
    if (!_composerRevealed) {
      _composerRevealed = true;
      changed = true;
    }
    if (requestFocus && !_focusNode.hasFocus) {
      _focusNode.requestFocus();
    }
    if (changed) {
      notifyListeners();
    }
  }

  void interrupt() {
    revealComposer(requestFocus: true);
  }

  @override
  void dispose() {
    _focusNode.dispose();
    _textController.dispose();
    super.dispose();
  }
}
