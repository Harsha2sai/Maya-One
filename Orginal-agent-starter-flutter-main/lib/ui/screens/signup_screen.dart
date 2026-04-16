import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../state/providers/auth_provider.dart';
import '../theme/app_theme.dart';
import '../../widgets/common/zoya_button.dart';

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  bool _isLoading = false;
  String? _error;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _handleSignup() async {
    final password = _passwordController.text.trim();
    final confirm = _confirmPasswordController.text.trim();
    if (password != confirm) {
      setState(() => _error = 'Passwords do not match');
      return;
    }
    if (password.length < 6) {
      setState(() => _error = 'Password must be at least 6 characters');
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
    });

    final auth = context.read<AuthProvider>();
    final success = await auth.signUp(
      _emailController.text.trim(),
      password,
      displayName: _nameController.text.trim().isEmpty ? null : _nameController.text.trim(),
    );

    if (!mounted) return;
    if (success) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Account created successfully. Please log in.')),
      );
    } else {
      setState(() {
        _isLoading = false;
        _error = 'Unable to create account. Please check your details.';
      });
    }
  }

  Future<void> _handleGoogleSignIn() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final auth = context.read<AuthProvider>();
    final success = await auth.signInWithGoogle();
    if (!success && mounted) {
      setState(() {
        _isLoading = false;
        _error = 'Google sign-in failed. Please try again.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ZoyaTheme.mainBg,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: const IconThemeData(color: ZoyaTheme.textMain),
      ),
      body: Center(
        child: Container(
          width: 520,
          padding: const EdgeInsets.all(40),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.30),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Create Account',
                style: ZoyaTheme.fontDisplay.copyWith(fontSize: 30, color: ZoyaTheme.textMain),
              ),
              const SizedBox(height: 8),
              Text(
                'Sign up with email or continue with Google.',
                style: ZoyaTheme.fontBody.copyWith(color: ZoyaTheme.textMuted),
              ),
              const SizedBox(height: 28),
              if (_error != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  margin: const EdgeInsets.only(bottom: 18),
                  decoration: BoxDecoration(
                    color: ZoyaTheme.danger.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: ZoyaTheme.danger.withValues(alpha: 0.25)),
                  ),
                  child: Text(_error!, style: const TextStyle(color: ZoyaTheme.danger)),
                ),
              _buildLabel('Name'),
              _buildTextField(_nameController, 'Enter your name'),
              const SizedBox(height: 16),
              _buildLabel('Email'),
              _buildTextField(_emailController, 'Enter your email'),
              const SizedBox(height: 16),
              _buildLabel('Password'),
              _buildTextField(_passwordController, 'Create a password', obscure: true),
              const SizedBox(height: 16),
              _buildLabel('Confirm Password'),
              _buildTextField(_confirmPasswordController, 'Re-enter password', obscure: true),
              const SizedBox(height: 28),
              ZoyaButton(
                text: _isLoading ? 'CREATING ACCOUNT...' : 'SIGN UP',
                onPressed: _handleSignup,
                isProgressing: _isLoading,
              ),
              const SizedBox(height: 14),
              _GoogleAuthButton(
                text: _isLoading ? 'PLEASE WAIT...' : 'CONTINUE WITH GOOGLE',
                onPressed: _isLoading ? null : _handleGoogleSignIn,
              ),
            ],
          ),
        ),
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

  Widget _buildTextField(
    TextEditingController controller,
    String hint, {
    bool obscure = false,
  }) {
    return TextField(
      controller: controller,
      obscureText: obscure,
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

class _GoogleAuthButton extends StatelessWidget {
  final String text;
  final VoidCallback? onPressed;

  const _GoogleAuthButton({
    required this.text,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton.icon(
        onPressed: onPressed,
        icon: const Icon(Icons.g_mobiledata, size: 28, color: ZoyaTheme.textMain),
        label: Text(
          text,
          style: ZoyaTheme.fontBody.copyWith(
            color: ZoyaTheme.textMain,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.6,
          ),
        ),
        style: OutlinedButton.styleFrom(
          side: BorderSide(color: Colors.white.withValues(alpha: 0.22)),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          backgroundColor: Colors.white.withValues(alpha: 0.04),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      ),
    );
  }
}
