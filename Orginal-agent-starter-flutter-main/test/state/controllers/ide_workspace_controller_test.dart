import 'package:flutter_test/flutter_test.dart';
import 'package:voice_assistant/state/controllers/ide_workspace_controller.dart';

void main() {
  test('configureBuddy is deterministic for same user id', () {
    final controllerA = IDEWorkspaceController();
    final controllerB = IDEWorkspaceController();

    controllerA.configureBuddy('user-123');
    controllerB.configureBuddy('user-123');

    expect(controllerA.buddyConfig.userIdHash, controllerB.buddyConfig.userIdHash);
    expect(controllerA.buddyConfig.seed, controllerB.buddyConfig.seed);
    expect(controllerA.buddyConfig.species, controllerB.buddyConfig.species);
    expect(controllerA.buddyConfig.isShiny, controllerB.buddyConfig.isShiny);
  });

  test('panel sizing clamps to safe bounds', () {
    final controller = IDEWorkspaceController();

    controller.setLeftPanelWidth(900);
    controller.setRightPanelWidth(50);
    controller.setTerminalHeight(999);

    expect(controller.leftPanelWidth, 420);
    expect(controller.rightPanelWidth, 280);
    expect(controller.terminalHeight, 420);
  });

  test('mode and panel toggles update state', () {
    final controller = IDEWorkspaceController();

    controller.setMode(IdeWorkspaceMode.missionControl);
    controller.setTerminalVisible(false);
    controller.setLeftPanelVisible(false);
    controller.setRightPanelVisible(false);

    expect(controller.mode, IdeWorkspaceMode.missionControl);
    expect(controller.terminalVisible, isFalse);
    expect(controller.leftPanelVisible, isFalse);
    expect(controller.rightPanelVisible, isFalse);
  });
}
