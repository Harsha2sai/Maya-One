import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/providers/auth_provider.dart';
import '../ui/zoya_theme.dart';
import '../widgets/zoya_button.dart';
import '../widgets/glass_container.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLoading = false;
  String? _error;

  Future<void> _handleLogin() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final auth = context.read<AuthProvider>();
    final success = await auth.signIn(
      _emailController.text.trim(),
      _passwordController.text.trim(),
    );

    if (!success && mounted) {
      setState(() {
        _isLoading = false;
        _error = 'Invalid email or password';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ZoyaTheme.mainBg,
      body: Row(
        children: [
          // Left Side - Branding
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [ZoyaTheme.orbCore.withValues(alpha: 0.2), Colors.transparent],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      'ZOYA',
                      style: ZoyaTheme.fontDisplay.copyWith(
                        fontSize: 64,
                        color: ZoyaTheme.accent,
                        letterSpacing: 8,
                        shadows: [Shadow(color: ZoyaTheme.accentGlow, blurRadius: 40)],
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      'YOUR PERSONAL AI COMPANION',
                      style: ZoyaTheme.fontBody.copyWith(
                        color: ZoyaTheme.textMuted,
                        letterSpacing: 2,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          
          // Right Side - Form
          Container(
            width: 500,
            padding: const EdgeInsets.all(60),
            color: Colors.black.withValues(alpha: 0.3),
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Log In',
                    style: ZoyaTheme.fontDisplay.copyWith(fontSize: 32, color: ZoyaTheme.textMain),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      const Text('Don\'t have an account? ', style: TextStyle(color: ZoyaTheme.textMuted)),
                      GestureDetector(
                        onTap: () {
                          // Navigate to signup
                        },
                        child: const Text('Sign up', style: TextStyle(color: ZoyaTheme.accent)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 40),
                  if (_error != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 20),
                      decoration: BoxDecoration(
                        color: ZoyaTheme.danger.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: ZoyaTheme.danger.withValues(alpha: 0.2)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: ZoyaTheme.danger, size: 20),
                          const SizedBox(width: 12),
                          Text(_error!, style: const TextStyle(color: ZoyaTheme.danger)),
                        ],
                      ),
                    ),
                  _buildLabel('Email'),
                  _buildTextField(_emailController, 'Enter your email', false),
                  const SizedBox(height: 24),
                  _buildLabel('Password'),
                  _buildTextField(_passwordController, 'Enter your password', true),
                  const SizedBox(height: 40),
                  ZoyaButton(
                    text: _isLoading ? 'SIGNING IN...' : 'LOG IN',
                    onPressed: _handleLogin,
                    isProgressing: _isLoading,
                  ),
                  const SizedBox(height: 24),
                  Center(
                    child: TextButton(
                      onPressed: () {
                        // Guest mode logic - maybe just continue to home if permitted
                        Navigator.pushReplacementNamed(context, '/home');
                      },
                      child: const Text('Continue as Guest', style: TextStyle(color: ZoyaTheme.textMuted)),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLabel(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: const TextStyle(color: ZoyaTheme.textMuted, fontSize: 13, fontWeight: FontWeight.bold),
      ),
    );
  }

  Widget _buildTextField(TextEditingController controller, String hint, bool isPassword) {
    return TextField(
      controller: controller,
      obscureText: isPassword,
      style: const TextStyle(color: Colors.white),
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: const TextStyle(color: Colors.white24),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.05),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      ),
    );
  }
}
