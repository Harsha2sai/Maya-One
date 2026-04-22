import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'state/providers/session_provider.dart';
import 'state/providers/auth_provider.dart';
import 'state/providers/settings_provider.dart';
import 'state/controllers/app_init_controller.dart';
import 'state/controllers/orb_controller.dart';
import 'state/controllers/workspace_controller.dart';
import 'state/controllers/overlay_controller.dart';
import 'state/models/workspace_models.dart';

import 'ui/screens/agent_screen.dart';
import 'ui/screens/welcome_screen.dart';
import 'ui/screens/login_screen.dart';
import 'ui/screens/projects_screen.dart';
import 'ui/screens/ide_workspace_screen.dart';
import 'widgets/layout/shell_sidebar.dart';
import 'widgets/common/error_banner.dart';
import 'ui/theme/app_theme.dart';

class App extends StatefulWidget {
  const App({super.key});

  @override
  State<App> createState() => _AppState();
}

class _AppState extends State<App> {
  bool _initialized = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final auth = Provider.of<AuthProvider>(context);
    if (auth.isAuthenticated && !_initialized) {
      _initialized = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _startInit();
      });
    }
  }

  void _startInit() {
    final auth = Provider.of<AuthProvider>(context, listen: false);
    final settings = Provider.of<SettingsProvider>(context, listen: false);
    final session = Provider.of<SessionProvider>(context, listen: false);
    final orb = Provider.of<OrbController>(context, listen: false);
    final init = Provider.of<AppInitController>(context, listen: false);

    init.initialize(auth, settings, session, orb);
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<SessionProvider>();
    final auth = context.watch<AuthProvider>();
    final init = context.watch<AppInitController>();
    final workspace = context.watch<WorkspaceController>();
    final viewportWidth = MediaQuery.of(context).size.width;
    final isCompact = viewportWidth < 900;
    final sidebarWidth = isCompact ? (viewportWidth * 0.82).clamp(240.0, 420.0).toDouble() : 280.0;
    final resolvedLayoutMode = viewportWidth < 700
        ? WorkspaceLayoutMode.compact
        : viewportWidth < 1100
            ? WorkspaceLayoutMode.medium
            : WorkspaceLayoutMode.wide;
    if (workspace.layoutMode != resolvedLayoutMode) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }

        final overlayCtrl = context.read<OverlayController>();
        final workspaceCtrl = context.read<WorkspaceController>();

        if (resolvedLayoutMode != WorkspaceLayoutMode.compact) {
          overlayCtrl.setCompactWorkbenchSheetOpen(false);
        }

        workspaceCtrl.setLayoutMode(resolvedLayoutMode);
      });
    }

    // Auth Guard
    if (!auth.isInitialized) {
      return const Scaffold(
        backgroundColor: ZoyaTheme.mainBg,
        body: Center(child: CircularProgressIndicator(color: ZoyaTheme.accent)),
      );
    }

    if (!auth.isAuthenticated) {
      return const LoginScreen();
    }

    return Scaffold(
      backgroundColor: ZoyaTheme.mainBg,
      body: Stack(
        children: [
          Row(
            children: [
              // Global Sidebar with Animated Collapse
              AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOut,
                width: workspace.sidebarCollapsed ? 0 : sidebarWidth,
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  physics: const NeverScrollableScrollPhysics(),
                  child: SizedBox(
                    width: sidebarWidth,
                    child: ShellSidebar(
                      activePage: workspace.currentPage,
                      width: sidebarWidth,
                      onNavigate: (page) => workspace.setCurrentPage(page),
                    ),
                  ),
                ),
              ),

              // Main Viewer
              Expanded(
                child: Stack(
                  children: [
                    _buildMainContent(workspace.currentPage, session.isConnected, init.state),

                    // Sidebar Toggle Button (visible when sidebar is collapsed)
                    if (workspace.sidebarCollapsed)
                      Positioned(
                        top: 20,
                        left: 20,
                        child: _SidebarToggleButton(
                          onTap: () => workspace.toggleSidebar(),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),

          // Global Error Banner
          const SessionErrorBanner(),
        ],
      ),
    );
  }

  Widget _buildMainContent(String page, bool isConnected, InitState initState) {
    if (page == 'home') {
      if (isConnected) {
        return const AgentScreen(); // Sidebar is global now, workspace handles its own rail
      }
      return const WelcomeScreen(showSidebar: false);
    }

    if (page == 'projects') {
      return const ProjectsScreen();
    }

    if (page == 'ide_workspace') {
      return const IDEWorkspaceScreen();
    }

    // Other pages: Dashboard, History, etc.
    return Container(
      decoration: BoxDecoration(
        color: ZoyaTheme.mainBg,
        gradient: ZoyaTheme.bgGradient,
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              page.toUpperCase(),
              style: ZoyaTheme.fontDisplay.copyWith(fontSize: 32, color: ZoyaTheme.accent),
            ),
            const SizedBox(height: 20),
            const Text(
              'Feature synchronization in progress...',
              style: TextStyle(color: ZoyaTheme.textMuted),
            ),
          ],
        ),
      ),
    );
  }
}

class _SidebarToggleButton extends StatelessWidget {
  final VoidCallback onTap;
  const _SidebarToggleButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.5),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: ZoyaTheme.glassBorder),
          ),
          child: const Center(
            child: FaIcon(
              FontAwesomeIcons.bars,
              size: 16,
              color: ZoyaTheme.textMain,
            ),
          ),
        ),
      ),
    );
  }
}
