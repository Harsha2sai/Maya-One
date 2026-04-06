import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/overlay_models.dart';

class OverlayController extends ChangeNotifier {
  SystemActionToastData? _systemActionToast;
  MediaResultToastData? _mediaResultToast;
  ConfirmationPromptData? _pendingConfirmation;
  bool _isReconnectPromptVisible = false;
  bool _compactWorkbenchSheetOpen = false;

  SystemActionToastData? get systemActionToast => _systemActionToast;
  MediaResultToastData? get mediaResultToast => _mediaResultToast;
  ConfirmationPromptData? get pendingConfirmation => _pendingConfirmation;
  bool get isReconnectPromptVisible => _isReconnectPromptVisible;
  bool get compactWorkbenchSheetOpen => _compactWorkbenchSheetOpen;

  Timer? _mediaToastTimer;

  void showSystemActionToast(SystemActionToastData data) {
    _systemActionToast = data;
    notifyListeners();
  }

  void clearSystemActionToast() {
    _systemActionToast = null;
    notifyListeners();
  }

  void showMediaResultToast(MediaResultToastData data) {
    _mediaToastTimer?.cancel();
    _mediaResultToast = data;
    notifyListeners();

    _mediaToastTimer = Timer(const Duration(seconds: 3), () {
      clearMediaResultToast();
    });
  }

  void clearMediaResultToast() {
    _mediaToastTimer?.cancel();
    _mediaResultToast = null;
    notifyListeners();
  }

  void showConfirmationPrompt(ConfirmationPromptData data) {
    _pendingConfirmation = data;
    notifyListeners();
  }

  void clearConfirmationPrompt() {
    _pendingConfirmation = null;
    notifyListeners();
  }

  void setReconnectPromptVisible(bool visible) {
    if (_isReconnectPromptVisible != visible) {
      _isReconnectPromptVisible = visible;
      notifyListeners();
    }
  }

  void setCompactWorkbenchSheetOpen(bool value) {
    if (_compactWorkbenchSheetOpen == value) {
      return;
    }
    _compactWorkbenchSheetOpen = value;
    notifyListeners();
  }

  void reset() {
    _systemActionToast = null;
    _mediaResultToast = null;
    _pendingConfirmation = null;
    _isReconnectPromptVisible = false;
    _compactWorkbenchSheetOpen = false;
    _mediaToastTimer?.cancel();
    notifyListeners();
  }

  @override
  void dispose() {
    _mediaToastTimer?.cancel();
    super.dispose();
  }
}
