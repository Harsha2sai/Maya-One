import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/controllers/agent_activity_controller.dart';
import '../../state/controllers/orb_controller.dart';

class AgentOrbStateBridge extends StatefulWidget {
  final Widget child;

  const AgentOrbStateBridge({
    super.key,
    required this.child,
  });

  @override
  State<AgentOrbStateBridge> createState() => _AgentOrbStateBridgeState();
}

class _AgentOrbStateBridgeState extends State<AgentOrbStateBridge> {
  AgentActivityController? _activityController;
  bool _syncScheduled = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final nextActivityController = context.read<AgentActivityController>();
    if (!identical(_activityController, nextActivityController)) {
      _activityController?.removeListener(_scheduleSyncOrbState);
      _activityController = nextActivityController;
      _activityController?.addListener(_scheduleSyncOrbState);
      _scheduleSyncOrbState();
    }
  }

  @override
  void dispose() {
    _activityController?.removeListener(_scheduleSyncOrbState);
    super.dispose();
  }

  void _scheduleSyncOrbState() {
    if (_syncScheduled || !mounted) {
      return;
    }
    _syncScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _syncScheduled = false;
      _syncOrbState();
    });
  }

  void _syncOrbState() {
    if (!mounted) {
      return;
    }
    final orb = context.read<OrbController>();
    final activity = _activityController ?? context.read<AgentActivityController>();
    final nextLifecycle = _mapVoiceStateToOrbLifecycle(activity.voiceUiState);
    if (orb.lifecycle != nextLifecycle) {
      orb.setLifecycle(nextLifecycle);
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

OrbLifecycle _mapVoiceStateToOrbLifecycle(VoiceUiState state) {
  switch (state) {
    case VoiceUiState.listening:
      return OrbLifecycle.listening;
    case VoiceUiState.speaking:
    case VoiceUiState.greeting:
      return OrbLifecycle.speaking;
    case VoiceUiState.thinking:
    case VoiceUiState.toolRunning:
    case VoiceUiState.bootstrapping:
    case VoiceUiState.reconnecting:
      return OrbLifecycle.initializing;
    case VoiceUiState.interrupted:
      return OrbLifecycle.active;
    case VoiceUiState.offline:
      return OrbLifecycle.muted;
    case VoiceUiState.idle:
      return OrbLifecycle.idle;
  }
}
