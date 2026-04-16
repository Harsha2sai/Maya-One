import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:logging/logging.dart';
import 'package:google_sign_in/google_sign_in.dart';

class SupabaseService {
  final Logger _logger = Logger('SupabaseService');
  bool _available = false;
  bool _initialized = false;
  static const List<String> _googleScopes = <String>['email', 'profile', 'openid'];
  static const String _defaultGoogleRedirectUri =
      'io.supabase.flutter://signin-callback';
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
    final url = dotenv.env['SUPABASE_URL'];
    final anonKey = dotenv.env['SUPABASE_ANON_KEY'];

    if (url == null || anonKey == null) {
      _available = false;
      _initialized = optionalMode;
      if (optionalMode) {
        _logger.warning(
          'Supabase optional mode enabled (SUPABASE_OPTIONAL=1) and credentials '
          'are missing; running without Supabase auth/settings sync.',
        );
      } else {
        _logger.severe('Supabase URL or Anon Key not found in environment variables');
      }
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
      if (optionalMode) {
        _available = false;
        _initialized = true;
        _logger.warning(
          'Supabase optional mode enabled (SUPABASE_OPTIONAL=1); '
          'initialization failed, continuing without auth/settings sync: $e',
        );
        return;
      }
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
    try {
      final googleSignIn = await _ensureGoogleSignInInitialized();
      if (googleSignIn.supportsAuthenticate()) {
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
    } catch (e) {
      _logger.warning(
        'Native Google Sign-In unavailable; falling back to browser OAuth flow: $e',
      );
    }

    _logger.info(
      'Using browser-based Google OAuth fallback (desktop/dev compatible).',
    );

    if (!kIsWeb && (Platform.isLinux || Platform.isMacOS || Platform.isWindows)) {
      return _signInWithGoogleViaLoopback();
    }

    final configuredRedirect = dotenv.env['SUPABASE_AUTH_REDIRECT_URI']?.trim();
    final redirectUri = (configuredRedirect != null && configuredRedirect.isNotEmpty)
        ? configuredRedirect
        : _defaultGoogleRedirectUri;
    if (configuredRedirect == null || configuredRedirect.isEmpty) {
      _logger.warning(
        'SUPABASE_AUTH_REDIRECT_URI not set; using default redirect URI: $redirectUri',
      );
    }
    final launched = await client.auth.signInWithOAuth(
      OAuthProvider.google,
      redirectTo: redirectUri,
      authScreenLaunchMode: LaunchMode.externalApplication,
    );
    if (!launched) {
      throw StateError('Failed to launch browser for Google OAuth sign-in.');
    }
    return AuthResponse();
  }

  Future<AuthResponse> _signInWithGoogleViaLoopback() async {
    const loopbackPort = 3000;
    late final HttpServer server;
    try {
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, loopbackPort);
    } on SocketException catch (e) {
      throw StateError(
        'Cannot start OAuth callback listener on localhost:$loopbackPort. '
        'Close the process using this port and retry. ($e)',
      );
    }
    final redirectUri = 'http://localhost:$loopbackPort/auth-callback';
    final callbackCompleter = Completer<Uri>();

    final serverSub = server.listen((request) async {
      final uri = request.uri;
      request.response.statusCode = HttpStatus.ok;
      request.response.headers.contentType = ContentType.html;
      request.response.headers.set('Cache-Control', 'no-store');
      request.response.write('''
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Maya-One Authentication</title>
    <style>
      :root {
        --bg: #071021;
        --card: #0f1a2f;
        --line: rgba(156, 188, 219, 0.28);
        --text: #e7edf6;
        --muted: #a8b5c8;
        --accent: #7dd3fc;
        --accent-soft: rgba(125, 211, 252, 0.3);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: "Georgia", "Times New Roman", serif;
        color: var(--text);
        background:
          radial-gradient(860px 420px at 15% -10%, rgba(125, 211, 252, 0.18), transparent 60%),
          radial-gradient(900px 420px at 90% 120%, rgba(148, 163, 184, 0.13), transparent 60%),
          var(--bg);
        display: grid;
        place-items: center;
      }
      .card {
        width: min(640px, 92vw);
        border: 1px solid var(--line);
        border-radius: 14px;
        background: linear-gradient(180deg, rgba(15, 26, 47, 0.95), rgba(8, 16, 31, 0.95));
        box-shadow: 0 24px 70px rgba(3, 8, 20, 0.55), inset 0 1px 0 rgba(255,255,255,0.03);
        padding: 34px 30px;
        text-align: center;
      }
      .wordmark {
        margin: 0;
        font-size: 30px;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: none;
      }
      .divider {
        width: 120px;
        height: 2px;
        margin: 14px auto 20px;
        background: linear-gradient(90deg, transparent, var(--accent), transparent);
        box-shadow: 0 0 22px var(--accent-soft);
      }
      h1 {
        margin: 0 0 10px;
        font-size: 27px;
        font-family: "Segoe UI", Inter, system-ui, sans-serif;
        letter-spacing: 0.02em;
        font-weight: 600;
      }
      p {
        margin: 0 0 2px;
        color: var(--muted);
        font-size: 15px;
        font-family: "Segoe UI", Inter, system-ui, sans-serif;
        line-height: 1.6;
      }
      .status {
        margin-top: 18px;
        display: inline-flex;
        align-items: center;
        gap: 10px;
        color: #c8d8ea;
        font-size: 13px;
        font-family: "Segoe UI", Inter, system-ui, sans-serif;
      }
      .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 14px var(--accent-soft);
        animation: pulseDot 1.5s ease-in-out infinite;
      }
      @keyframes pulseDot {
        0%, 100% { opacity: 0.45; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.15); }
      }
    </style>
  </head>
  <body>
    <main class="card">
      <p class="wordmark">Maya-One</p>
      <div class="divider" aria-hidden="true"></div>
      <h1>Authentication complete</h1>
      <p>Google sign-in is now linked to your Maya-One session.</p>
      <p>You can close this tab and return to the app.</p>
      <div class="status" aria-hidden="true">
        <span class="status-dot"></span>
        <span>Secure session established</span>
      </div>
    </main>
  </body>
</html>
''');
      await request.response.close();
      if (!callbackCompleter.isCompleted) {
        callbackCompleter.complete(uri);
      }
    });

    try {
      final launched = await client.auth.signInWithOAuth(
        OAuthProvider.google,
        redirectTo: redirectUri,
        authScreenLaunchMode: LaunchMode.externalApplication,
      );
      if (!launched) {
        throw StateError('Failed to launch browser for Google OAuth sign-in.');
      }

      final callbackUri = await callbackCompleter.future.timeout(
        const Duration(minutes: 2),
        onTimeout: () => throw TimeoutException(
          'Timed out waiting for Google OAuth callback on $redirectUri',
        ),
      );

      final error = callbackUri.queryParameters['error']?.trim();
      final errorDescription =
          callbackUri.queryParameters['error_description']?.trim();
      if (error != null && error.isNotEmpty) {
        throw StateError(
          'Google OAuth failed: ${errorDescription ?? error}',
        );
      }

      final code = callbackUri.queryParameters['code']?.trim();
      if (code == null || code.isEmpty) {
        throw StateError('Google OAuth callback missing authorization code.');
      }

      await client.auth.exchangeCodeForSession(code);
      return AuthResponse(
        session: client.auth.currentSession,
        user: client.auth.currentUser,
      );
    } finally {
      await serverSub.cancel();
      await server.close(force: true);
    }
  }

  Future<GoogleSignIn> _ensureGoogleSignInInitialized() async {
    _googleSignInInitialization ??= _googleSignIn.initialize();
    await _googleSignInInitialization;
    return _googleSignIn;
  }
}
