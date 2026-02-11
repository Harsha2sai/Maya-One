import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import '../ui/zoya_theme.dart';
import '../state/providers/auth_provider.dart';
import '../state/providers/ui_provider.dart';
import 'settings_dialog.dart';
import 'system_menu.dart';

class ShellSidebar extends StatefulWidget {
  final String activePage;
  final Function(String) onNavigate;

  const ShellSidebar({
    super.key,
    required this.activePage,
    required this.onNavigate,
  });

  @override
  State<ShellSidebar> createState() => _ShellSidebarState();
}

class _ShellSidebarState extends State<ShellSidebar> {
  // Mock data matching React
  final List<Map<String, String>> _recentChats = [
    {'id': '1', 'title': 'Voice assistant architecture'},
    {'id': '2', 'title': 'LiveKit integration help'},
    {'id': '3', 'title': 'Agent configuration guide'},
    {'id': '4', 'title': 'Audio settings troubleshooting'},
    {'id': '5', 'title': 'Dashboard customization'},
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 280, // React: 280px
      decoration: BoxDecoration(
        color: ZoyaTheme.sidebarBg, // #0a0a14
        border: Border(
          right: BorderSide(color: ZoyaTheme.glassBorder),
        ),
        boxShadow: [
           BoxShadow(color: Colors.black.withValues(alpha: 0.5), blurRadius: 30, offset: const Offset(4, 0)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Sidebar Header
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Text(
                      'ZOYA',
                      style: ZoyaTheme.fontDisplay.copyWith(
                        fontSize: 24, // 1.5em
                        fontWeight: FontWeight.bold,
                        color: ZoyaTheme.accent,
                        letterSpacing: 2,
                        shadows: [
                          Shadow(color: ZoyaTheme.accentGlow, blurRadius: 10),
                        ],
                      ),
                    ),
                    const SystemMenu(),
                  ],
                ),
                _SidebarIconButton(
                  icon: FontAwesomeIcons.chevronLeft,
                  onTap: () => context.read<UIProvider>().toggleSidebar(),
                  tooltip: 'Close Sidebar',
                ),
              ],
            ),
          ),

          // New Chat Button
          Padding(
            padding: const EdgeInsets.all(10),
            child: _NewChatButton(
              onTap: () => widget.onNavigate('newChat'),
            ),
          ),

          // Main Nav
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 20),
            child: Column(
              children: [
                _NavItem(
                  icon: FontAwesomeIcons.solidImage,
                  label: 'Images',
                  isActive: widget.activePage == 'images',
                  badge: 'NEW',
                  onTap: () => widget.onNavigate('images'),
                ),
                const SizedBox(height: 8),
                _NavItem(
                  icon: FontAwesomeIcons.tableCellsLarge,
                  label: 'Apps',
                  isActive: widget.activePage == 'apps',
                  onTap: () => widget.onNavigate('apps'),
                ),
                const SizedBox(height: 8),
                _NavItem(
                  icon: FontAwesomeIcons.folder,
                  label: 'Projects',
                  isActive: widget.activePage == 'projects',
                  onTap: () => widget.onNavigate('projects'),
                ),
              ],
            ),
          ),

          // Divider
          Container(
            height: 1,
            color: ZoyaTheme.glassBorder,
            margin: const EdgeInsets.symmetric(vertical: 10),
          ),

          // Recent Chats
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                   Padding(
                     padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                     child: Text(
                       'YOUR CHATS',
                       style: ZoyaTheme.fontBody.copyWith(
                         fontSize: 11, // 0.8em
                         fontWeight: FontWeight.w600,
                         color: ZoyaTheme.textMuted,
                         letterSpacing: 1,
                       ),
                     ),
                   ),
                   Expanded(
                     child: ListView.builder(
                       itemCount: _recentChats.length,
                       itemBuilder: (context, index) {
                         final chat = _recentChats[index];
                         return _ChatItem(
                           title: chat['title']!,
                           onTap: () => widget.onNavigate('history'),
                         );
                       },
                     ),
                   ),
                ],
              ),
            ),
          ),

          // Sidebar Bottom
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: ZoyaTheme.glassBorder)),
            ),
            child: Column(
              children: [
                _NavItem(
                  icon: FontAwesomeIcons.gear,
                  label: 'Settings',
                  isActive: widget.activePage == 'settings',
                  onTap: () {
                    showDialog(
                      context: context,
                      builder: (context) => const SettingsDialog(),
                    );
                    // Don't navigate - just show the dialog overlay
                  },
                ),
                const SizedBox(height: 12),
                const _UserProfile(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SidebarIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  final String tooltip;

  const _SidebarIconButton({required this.icon, required this.onTap, required this.tooltip});

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: FaIcon(icon, size: 16, color: ZoyaTheme.textMuted),
        ),
      ),
    );
  }
}

class _NewChatButton extends StatefulWidget {
  final VoidCallback onTap;
  const _NewChatButton({required this.onTap});

  @override
  State<_NewChatButton> createState() => _NewChatButtonState();
}

class _NewChatButtonState extends State<_NewChatButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            color: _hover ? ZoyaTheme.accent.withValues(alpha: 0.1) : Colors.transparent,
            border: Border.all(
              color: _hover ? ZoyaTheme.accent : ZoyaTheme.accent.withValues(alpha: 0.3),
            ),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Row(
            children: [
              FaIcon(
                FontAwesomeIcons.penToSquare, 
                size: 16, 
                color: _hover ? ZoyaTheme.accent : ZoyaTheme.textMain
              ),
              const SizedBox(width: 12),
              Text(
                'New chat',
                style: ZoyaTheme.fontBody.copyWith(
                   color: _hover ? ZoyaTheme.accent : ZoyaTheme.textMain,
                   fontSize: 14,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatefulWidget {
  final IconData icon;
  final String label;
  final bool isActive;
  final String? badge;
  final VoidCallback onTap;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.isActive,
    this.badge,
    required this.onTap,
  });

  @override
  State<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends State<_NavItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final active = widget.isActive || _hover;
    
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            color: active ? ZoyaTheme.accent.withValues(alpha: 0.1) : Colors.transparent,
            border: Border.all(
              color: active 
                  ? (widget.isActive ? ZoyaTheme.accent : ZoyaTheme.accent.withValues(alpha: 0.2)) 
                  : Colors.transparent,
            ),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Row(
            children: [
              SizedBox(
                width: 20,
                child: Center(
                  child: FaIcon(
                    widget.icon, 
                    size: 16, 
                    color: active ? ZoyaTheme.accent : const Color(0xFFB0B8C4),
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Text(
                  widget.label,
                  style: ZoyaTheme.fontBody.copyWith(
                     color: active ? ZoyaTheme.accent : const Color(0xFFB0B8C4),
                     fontSize: 14,
                  ),
                ),
              ),
              if (widget.badge != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: ZoyaTheme.accent,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    widget.badge!,
                    style: ZoyaTheme.fontDisplay.copyWith(
                      color: Colors.black,
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChatItem extends StatefulWidget {
  final String title;
  final VoidCallback onTap;

  const _ChatItem({required this.title, required this.onTap});

  @override
  State<_ChatItem> createState() => _ChatItemState();
}

class _ChatItemState extends State<_ChatItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          margin: const EdgeInsets.only(bottom: 4),
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
          decoration: BoxDecoration(
            color: _hover ? ZoyaTheme.accent.withValues(alpha: 0.05) : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            children: [
               FaIcon(
                 FontAwesomeIcons.commentDots, 
                 size: 14, 
                 color: _hover ? ZoyaTheme.textMain : ZoyaTheme.textMuted.withValues(alpha: 0.7),
               ),
               const SizedBox(width: 10),
               Expanded(
                 child: Text(
                   widget.title,
                   style: ZoyaTheme.fontBody.copyWith(
                     color: _hover ? ZoyaTheme.textMain : const Color(0xFFB0B8C4),
                     fontSize: 13,
                   ),
                   maxLines: 1,
                   overflow: TextOverflow.ellipsis,
                 ),
               ),
            ],
          ),
        ),
      ),
    );
  }
}

class _UserProfile extends StatefulWidget {
  const _UserProfile();

  @override
  State<_UserProfile> createState() => _UserProfileState();
}

class _UserProfileState extends State<_UserProfile> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final user = auth.user;
    final userName = user?.email?.split('@')[0] ?? 'Guest User';
    final initials = userName.substring(0, 2).toUpperCase();

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: ZoyaTheme.accent.withValues(alpha: 0.05),
          border: Border.all(
            color: _hover ? ZoyaTheme.accent : ZoyaTheme.accent.withValues(alpha: 0.1),
          ),
          borderRadius: BorderRadius.circular(10),
          boxShadow: _hover ? [
             const BoxShadow(color: Color.fromRGBO(0, 243, 255, 0.1), blurRadius: 15)
          ] : [],
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(
                  colors: [ZoyaTheme.accent, ZoyaTheme.secondaryAccent],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                boxShadow: [
                  BoxShadow(color: ZoyaTheme.accentGlow, blurRadius: 15),
                ],
              ),
              child: Center(
                child: Text(
                  initials,
                  style: ZoyaTheme.fontDisplay.copyWith(
                    color: Colors.black,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    userName,
                    style: ZoyaTheme.fontBody.copyWith(
                      color: ZoyaTheme.textMain,
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    auth.isAuthenticated ? 'Online' : 'Guest',
                    style: ZoyaTheme.fontBody.copyWith(
                      color: auth.isAuthenticated ? ZoyaTheme.success : ZoyaTheme.textMuted,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
