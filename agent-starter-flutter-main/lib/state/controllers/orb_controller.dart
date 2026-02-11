import 'package:flutter/material.dart';
import '../../widgets/cosmic_orb.dart';

enum OrbLifecycle {
  hidden,
  initializing,
  appearing,
  idle,
  active,
  listening,
  speaking,
  floating,
  docked,
  minimized,
  muted
}

enum OrbLayoutState {
  centerDock,
  floatingRight,
  floatingLeft,
  minimizedRight,
  minimizedLeft,
  hidden
}

class OrbController extends ChangeNotifier {
  // --- Lifecycle State ---
  OrbLifecycle _lifecycle = OrbLifecycle.hidden;
  OrbLifecycle get lifecycle => _lifecycle;

  // --- Layout State ---
  OrbLayoutState _layoutState = OrbLayoutState.hidden;
  OrbLayoutState get layoutState => _layoutState;

  // --- Interaction State ---
  final double _scale = 1.0;
  Offset _position = Offset.zero;
  bool _isMuted = false;
  
  double get scale => _scale;
  Offset get position => _position;
  bool get isMuted => _isMuted;

  void setLifecycle(OrbLifecycle state) {
    if (_lifecycle != state) {
      _lifecycle = state;
      
      // Auto-map layout from lifecycle
      if (state == OrbLifecycle.hidden) {
        _layoutState = OrbLayoutState.hidden;
      } else if (state == OrbLifecycle.appearing) _layoutState = OrbLayoutState.centerDock;
      else if (state == OrbLifecycle.docked) _layoutState = OrbLayoutState.minimizedRight;
      
      notifyListeners();
    }
  }

  void setLayout(OrbLayoutState newState) {
    if (_layoutState != newState) {
      _layoutState = newState;
      notifyListeners();
    }
  }

  void toggleMute() {
    _isMuted = !_isMuted;
    _lifecycle = _isMuted ? OrbLifecycle.muted : OrbLifecycle.idle;
    notifyListeners();
  }

  void handleTap() {
    if (_lifecycle == OrbLifecycle.idle || _lifecycle == OrbLifecycle.minimized) {
      _lifecycle = OrbLifecycle.active;
    } else if (_lifecycle == OrbLifecycle.active) {
      _lifecycle = OrbLifecycle.idle;
    }
    notifyListeners();
  }

  void updatePosition(Offset delta) {
    _position += delta;
    notifyListeners();
  }

  void resetPosition() {
    _position = Offset.zero;
    notifyListeners();
  }

  // Bindings for the legacy CosmicOrb OrbState enum
  OrbState get orbState {
    switch (_lifecycle) {
      case OrbLifecycle.listening: return OrbState.listening;
      case OrbLifecycle.speaking: return OrbState.speaking;
      case OrbLifecycle.initializing: return OrbState.thinking;
      default: return OrbState.idle;
    }
  }
}
