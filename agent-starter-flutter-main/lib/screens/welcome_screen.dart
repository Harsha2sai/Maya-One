import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../ui/zoya_theme.dart';
import '../widgets/zoya_button.dart';
import '../widgets/glass_container.dart';
import '../state/providers/session_provider.dart';
import '../state/providers/settings_provider.dart';
import '../state/providers/auth_provider.dart';
import '../widgets/cosmic_orb.dart';

class WelcomeScreen extends StatelessWidget {
  final bool showSidebar;
  const WelcomeScreen({super.key, this.showSidebar = false});

  @override
  Widget build(BuildContext ctx) {
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          color: ZoyaTheme.mainBg,
          gradient: ZoyaTheme.bgGradient,
        ),
        child: Center(
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
              // Logo Area - Replaced with Orb for brand consistency
              SizedBox(
                width: 200,
                height: 200,
                child: Center(
                  child: CosmicOrb(
                    state: OrbState.idle,
                    isMicEnabled: false,
                    size: 120,
                    showStatus: false,
                  ),
                ),
              ),
              const SizedBox(height: 40),
              
              // Title
              Text(
                'ZOYA AGENT',
                style: ZoyaTheme.fontDisplay.copyWith(
                  fontSize: 32,
                  letterSpacing: 4,
                  shadows: [
                    Shadow(color: ZoyaTheme.accent, blurRadius: 20),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Voice Interface System v2.0',
                style: ZoyaTheme.fontBody.copyWith(
                  color: ZoyaTheme.textMuted,
                  letterSpacing: 1.5,
                ),
              ),
              
              const SizedBox(height: 60),

              // Glass Panel for Controls
              GlassContainer(
                width: 400,
                padding: const EdgeInsets.all(40),
                child: Column(
                  children: [
                    // Status Indicator
                    Consumer<SessionProvider>(
                      builder: (context, session, _) {
                        final isReady = session.connectionState == SessionConnectionState.disconnected 
                            && !session.loading;
                        final isConnecting = session.isConnecting;
                        
                        return Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Container(
                              width: 8,
                              height: 8,
                              decoration: BoxDecoration(
                                color: isConnecting 
                                    ? Colors.orange 
                                    : (isReady ? ZoyaTheme.success : ZoyaTheme.textMuted),
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              isConnecting 
                                  ? session.loadingStatus.toUpperCase() 
                                  : (isReady ? 'SYSTEM READY' : 'INITIALIZING...'),
                              style: ZoyaTheme.fontDisplay.copyWith(
                                fontSize: 12, 
                                color: isConnecting 
                                    ? Colors.orange 
                                    : (isReady ? ZoyaTheme.success : ZoyaTheme.textMuted),
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                    const SizedBox(height: 30),

                    // Connect Button
                    Consumer<SessionProvider>(
                      builder: (context, session, _) {
                        return ZoyaButton(
                          text: session.isConnecting 
                              ? 'CONNECTING...' 
                              : (session.isConnected ? 'CONNECTED' : 'INITIATE LINK'),
                          isProgressing: session.loading,
                          onPressed: session.isConnected 
                              ? () {} 
                              : () => _handleConnect(context),
                        );
                      },
                    ),
                    
                    // Error message if any
                    Consumer<SessionProvider>(
                      builder: (context, session, _) {
                        if (session.hasError) {
                          return Padding(
                            padding: const EdgeInsets.only(top: 16),
                            child: Text(
                              session.error ?? 'Connection failed',
                              style: ZoyaTheme.fontBody.copyWith(
                                color: ZoyaTheme.danger,
                                fontSize: 12,
                              ),
                              textAlign: TextAlign.center,
                            ),
                          );
                        }
                        return const SizedBox.shrink();
                      },
                    ),
                  ],
                ),
              ),
            ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _handleConnect(BuildContext context) async {
    final session = context.read<SessionProvider>();
    final auth = context.read<AuthProvider>();
    final settings = context.read<SettingsProvider>();

    //  Extract provider configuration
    final config = {
      'llm_provider': settings.llmProvider,
      'llm_model': settings.llmModel,
      'llm_temperature': settings.llmTemperature,
      'stt_provider': settings.sttProvider,
      'stt_model': settings.sttModel,
      'stt_language': settings.sttLanguage,
      'tts_provider': settings.ttsProvider,
      'tts_voice': settings.ttsVoice,
      'tts_model': settings.preferences['ttsModel'] ?? 'aura-asteria-en', 
    };
    
    // Pass the persistent Supabase User ID to ensure Mem0 memory is saved correctly
    final success = await session.connect(
      userId: auth.user?.id,
      clientConfig: config,
    );
    
    if (success && context.mounted) {
      // Connection successful - navigate to session screen
      // For now, we'll just show a message since routing isn't fully set up
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Connected successfully!'),
          backgroundColor: ZoyaTheme.success,
        ),
      );
    }
  }
}
