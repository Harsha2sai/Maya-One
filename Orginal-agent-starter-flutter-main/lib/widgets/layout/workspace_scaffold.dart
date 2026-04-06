import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/controllers/workspace_controller.dart';
import '../../state/models/workspace_models.dart';

class WorkspaceScaffold extends StatelessWidget {
  final Color backgroundColor;
  final Widget? background;
  final Widget centerStage;
  final Widget? leftNavigationRail;
  final Widget? floatingRightPanel;
  final Widget? statusPanel;
  final Widget? conversationOverlay;
  final Widget? minimizedOrb;
  final Widget? leftControlBar;
  final Widget? voiceStatusBar;
  final Widget? agentWorkbenchPane;
  final Widget? voiceActionDock;
  final List<Widget> overlays;

  const WorkspaceScaffold({
    super.key,
    this.backgroundColor = Colors.transparent,
    this.background,
    required this.centerStage,
    this.leftNavigationRail,
    this.floatingRightPanel,
    this.statusPanel,
    this.conversationOverlay,
    this.minimizedOrb,
    this.leftControlBar,
    this.voiceStatusBar,
    this.agentWorkbenchPane,
    this.voiceActionDock,
    this.overlays = const <Widget>[],
  });

  @override
  Widget build(BuildContext context) {
    final layoutMode = context.watch<WorkspaceController>().layoutMode;

    return Scaffold(
      key: const Key('workspace_scaffold_root'),
      backgroundColor: backgroundColor,
      body: switch (layoutMode) {
        WorkspaceLayoutMode.compact => _CompactLayout(slots: this),
        WorkspaceLayoutMode.medium => _MediumLayout(slots: this),
        WorkspaceLayoutMode.wide => _WideLayout(slots: this),
      },
    );
  }
}

class _CompactLayout extends StatelessWidget {
  final WorkspaceScaffold slots;

  const _CompactLayout({required this.slots});

  @override
  Widget build(BuildContext context) {
    return _WorkspaceScaffoldBody(
      key: const ValueKey<String>('workspace_layout_compact'),
      slots: slots,
      layoutMode: WorkspaceLayoutMode.compact,
    );
  }
}

class _MediumLayout extends StatelessWidget {
  final WorkspaceScaffold slots;

  const _MediumLayout({required this.slots});

  @override
  Widget build(BuildContext context) {
    return _WorkspaceScaffoldBody(
      key: const ValueKey<String>('workspace_layout_medium'),
      slots: slots,
      layoutMode: WorkspaceLayoutMode.medium,
    );
  }
}

class _WideLayout extends StatelessWidget {
  final WorkspaceScaffold slots;

  const _WideLayout({required this.slots});

  @override
  Widget build(BuildContext context) {
    return _WorkspaceScaffoldBody(
      key: const ValueKey<String>('workspace_layout_wide'),
      slots: slots,
      layoutMode: WorkspaceLayoutMode.wide,
    );
  }
}

class _WorkspaceScaffoldBody extends StatelessWidget {
  final WorkspaceScaffold slots;
  final WorkspaceLayoutMode layoutMode;

  const _WorkspaceScaffoldBody({
    super.key,
    required this.slots,
    required this.layoutMode,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        if (slots.background != null) Positioned.fill(child: slots.background!),
        if (slots.voiceStatusBar != null)
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: slots.voiceStatusBar!,
          ),
        Positioned.fill(child: slots.centerStage),
        if (layoutMode != WorkspaceLayoutMode.compact && slots.agentWorkbenchPane != null)
          Positioned(
            top: 0,
            right: 0,
            bottom: 0,
            child: slots.agentWorkbenchPane!,
          ),
        if (slots.floatingRightPanel != null)
          Positioned(
            right: 20,
            top: 0,
            bottom: 0,
            child: Center(child: slots.floatingRightPanel!),
          ),
        if (slots.statusPanel != null)
          Positioned(
            top: 20,
            right: 20,
            child: slots.statusPanel!,
          ),
        if (slots.conversationOverlay != null) Positioned.fill(child: slots.conversationOverlay!),
        if (slots.minimizedOrb != null)
          Positioned(
            right: 40,
            bottom: 140,
            child: slots.minimizedOrb!,
          ),
        if (slots.leftNavigationRail != null)
          Positioned(
            left: 0,
            top: 0,
            bottom: 0,
            child: slots.leftNavigationRail!,
          ),
        if (slots.leftControlBar != null)
          Positioned(
            left: 20,
            top: 0,
            bottom: 0,
            child: Center(child: slots.leftControlBar!),
          ),
        if (slots.voiceActionDock != null)
          _DockPositioned(
            layoutMode: layoutMode,
            child: slots.voiceActionDock!,
          ),
        ...slots.overlays,
      ],
    );
  }
}

class _DockPositioned extends StatelessWidget {
  final WorkspaceLayoutMode layoutMode;
  final Widget child;

  const _DockPositioned({
    required this.layoutMode,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    switch (layoutMode) {
      case WorkspaceLayoutMode.compact:
      case WorkspaceLayoutMode.medium:
        return Positioned(
          bottom: 20,
          left: 0,
          right: 0,
          child: Center(child: child),
        );
      case WorkspaceLayoutMode.wide:
        return Positioned(
          right: 24,
          bottom: 24,
          child: child,
        );
    }
  }
}
