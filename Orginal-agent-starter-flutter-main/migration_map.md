# Maya-One Flutter Migration Map

This file records the canonical Flutter paths for the redesign and the legacy
paths that should not receive new feature logic.

## Path Map

| Legacy path | Canonical replacement | Status | Notes |
| --- | --- | --- | --- |
| `lib/screens/` | `lib/ui/screens/` | `deleted phase 7 (2026-03-15)` | Canonical screens now live under `lib/ui/screens/`. |
| `lib/widgets/shell_sidebar.dart` | `lib/widgets/layout/shell_sidebar.dart` | `deleted phase 7 (2026-03-15)` | Wrapper retired; import canonical sidebar directly. |
| `lib/widgets/session/` | `lib/widgets/features/chat/` and `lib/widgets/layout/` | `deleted phase 7 (2026-03-15)` | Session widgets moved into canonical feature/layout folders. |
| `lib/widgets/message_bar.dart` | `lib/widgets/features/chat/message_bar.dart` | `deleted phase 7 (2026-03-15)` | Legacy wrapper removed after chat modernization. |
| `lib/widgets/system_menu.dart` | `lib/widgets/layout/system_menu.dart` | `deleted phase 7 (2026-03-15)` | Legacy wrapper removed after overlay consolidation. |
| `lib/state/providers/ui_provider.dart` | `lib/state/controllers/workspace_controller.dart` | `deleted phase 7 (2026-03-15)` | Shim retired after all call sites migrated to WorkspaceController. |
| `lib/widgets/session_error_banner.dart` | `lib/widgets/common/error_banner.dart` | `removed in phase 6` | Duplicate SessionErrorBanner removed after confirming canonical import in app shell. |
| `lib/widgets/settings_dialog.dart` | `lib/widgets/settings/settings_dialog.dart` | `removed in phase 6` | Legacy duplicate removed after confirming zero imports to legacy path. |
| `lib/widgets/workbench/artifacts_panel.dart` | `lib/widgets/features/workbench/artifacts_panel.dart` | `canonical` | Moved early after confirmed zero imports from legacy path. |
| `lib/widgets/workbench/memory_stub_panel.dart` | `lib/widgets/features/workbench/memory_stub_panel.dart` | `canonical` | Moved early after confirmed zero imports from legacy path. |
| `lib/widgets/workbench/logs_panel.dart` | `lib/widgets/features/workbench/logs_panel.dart` | `delete after phase 7` | Deletion executed early due to confirmed zero imports. |
| `lib/widgets/workbench/plan_timeline_panel.dart` | `lib/widgets/features/workbench/plan_timeline_panel.dart` | `delete after phase 7` | Deletion executed early due to confirmed zero imports. |
| `lib/widgets/workbench/research_artifact_panel.dart` | `lib/widgets/features/workbench/research_artifact_panel.dart` | `delete after phase 7` | Deletion executed early due to confirmed zero imports. |
| `lib/widgets/workbench/task_inspector.dart` | `lib/widgets/features/workbench/task_inspector.dart` | `delete after phase 7` | Deletion executed early due to confirmed zero imports. |
| `lib/widgets/workbench/task_list_panel.dart` | `lib/widgets/features/workbench/task_list_panel.dart` | `delete after phase 7` | Deletion executed early due to confirmed zero imports. |

## Cleanup Rules

- `canonical`: the path is the source of truth for new work.
- `wrapper only`: path may remain as a thin export/import bridge, but must not gain logic.
- `delete after phase X`: path is temporary and should be removed only after the listed phase lands and imports/tests are migrated.
- `legacy do not extend`: leave untouched except for compatibility fixes.
