import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:logging/logging.dart';
import 'package:google_sign_in/google_sign_in.dart';

class SupabaseService {
  final Logger _logger = Logger('SupabaseService');
  bool _available = false;
  bool _initialized = false;
  static const List<String> _googleScopes = <String>['email', 'profile', 'openid'];
  static final GoogleSignIn _googleSignIn = GoogleSignIn.instance;
  static Future<void>? _googleSignInInitialization;

  static final SupabaseService _instance = SupabaseService._internal();
  factory SupabaseService() => _instance;
  SupabaseService._internal();

  SupabaseClient get client {
    if (!_available) {
      throw StateError(
        'Supabase is unavailable in this runtime. '
        'Set SUPABASE_OPTIONAL=0 and provide valid SUPABASE_URL/SUPABASE_ANON_KEY to enable it.',
      );
    }
    return Supabase.instance.client;
  }

  bool get isAvailable => _available;
  bool get isInitialized => _initialized;

  bool _isTruthy(String? raw) {
    final normalized = (raw ?? '').trim().toLowerCase();
    return normalized == '1' || normalized == 'true' || normalized == 'yes' || normalized == 'on';
  }

  Future<void> initialize() async {
    final optionalMode = _isTruthy(dotenv.env['SUPABASE_OPTIONAL']);
    if (optionalMode) {
      _available = false;
      _initialized = true;
      _logger.warning(
        'Supabase optional mode enabled (SUPABASE_OPTIONAL=1); '
        'running without Supabase auth/settings sync.',
      );
      return;
    }

    final url = dotenv.env['SUPABASE_URL'];
    final anonKey = dotenv.env['SUPABASE_ANON_KEY'];

    if (url == null || anonKey == null) {
      _available = false;
      _initialized = false;
      _logger.severe('Supabase URL or Anon Key not found in environment variables');
      return;
    }

    _logger.info('Initializing Supabase...');
    try {
      await Supabase.initialize(
        url: url,
        anonKey: anonKey,
      );
      _available = true;
      _initialized = true;
      _logger.info('Supabase initialized successfully');
    } catch (e) {
      _available = false;
      _initialized = false;
      _logger.severe('Supabase initialization failed: $e');
      rethrow;
    }
  }

  /// Auth helpers
  User? get currentUser => _available ? client.auth.currentUser : null;
  Session? get currentSession => _available ? client.auth.currentSession : null;
  Stream<AuthState> get authStateChanges =>
      _available ? client.auth.onAuthStateChange : const Stream<AuthState>.empty();

  Future<AuthResponse> signIn(String email, String password) async {
    return await client.auth.signInWithPassword(email: email, password: password);
  }

  Future<AuthResponse> signUp(String email, String password, {String? displayName}) async {
    return await client.auth.signUp(
      email: email,
      password: password,
      data: displayName != null ? {'display_name': displayName} : null,
    );
  }

  Future<void> signOut() async {
    await client.auth.signOut();
  }

  Future<AuthResponse> signInWithGoogle() async {
    final googleSignIn = await _ensureGoogleSignInInitialized();
    if (!googleSignIn.supportsAuthenticate()) {
      throw UnsupportedError(
        'Google Sign-In is not supported on this platform. '
        'Use email/password auth instead.',
      );
    }

    final account = await googleSignIn.authenticate(scopeHint: _googleScopes);
    final idToken = account.authentication.idToken;
    if (idToken == null || idToken.isEmpty) {
      throw StateError('Google authentication did not return an idToken.');
    }

    final headers = await account.authorizationClient.authorizationHeaders(
      _googleScopes,
      promptIfNecessary: true,
    );

    final authorization = headers?['Authorization'] ?? headers?['authorization'];
    String? accessToken;
    if (authorization != null && authorization.startsWith('Bearer ')) {
      accessToken = authorization.substring('Bearer '.length).trim();
    }

    return await client.auth.signInWithIdToken(
      provider: OAuthProvider.google,
      idToken: idToken,
      accessToken: accessToken,
    );
  }

  Future<GoogleSignIn> _ensureGoogleSignInInitialized() async {
    _googleSignInInitialization ??= _googleSignIn.initialize();
    await _googleSignInInitialization;
    return _googleSignIn;
  }
}
