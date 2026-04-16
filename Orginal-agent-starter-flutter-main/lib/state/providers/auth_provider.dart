import 'package:supabase_flutter/supabase_flutter.dart';
import '../base_provider.dart';
import '../../core/services/supabase_service.dart';

class AuthProvider extends BaseProvider {
  final SupabaseService _supabaseService;
  static const User _guestUser = User(
    id: 'guest-local',
    appMetadata: {'mode': 'optional'},
    userMetadata: {'display_name': 'Guest'},
    aud: 'authenticated',
    createdAt: '1970-01-01T00:00:00.000Z',
    email: 'guest@local.dev',
  );

  User? _user;
  Session? _session;
  bool _initialized = false;

  AuthProvider(this._supabaseService) : super('AuthProvider') {
    _init();
  }

  User? get user => _user;
  Session? get session => _session;
  bool get isAuthenticated => _user != null;
  bool get isInitialized => _initialized;
  bool get isGuestSession => _user?.id == _guestUser.id;

  void _init() {
    if (!_supabaseService.isAvailable) {
      _user = _guestUser;
      _session = null;
      _initialized = true;
      log('Supabase unavailable; AuthProvider running in guest mode (guest-local)');
      notifyListeners();
      return;
    }

    _user = _supabaseService.currentUser;
    _session = _supabaseService.currentSession;
    _initialized = true;
    notifyListeners();

    _supabaseService.authStateChanges.listen((data) {
      _user = data.session?.user;
      _session = data.session;
      log('Auth state changed: ${data.event}');
      notifyListeners();
    });
  }

  Future<bool> signIn(String email, String password) async {
    if (!_supabaseService.isAvailable) {
      log('Supabase unavailable; sign-in is disabled in optional mode');
      return false;
    }
    return await safeExecute(() async {
          await _supabaseService.signIn(email, password);
          return true;
        }) ??
        false;
  }

  Future<bool> signUp(String email, String password, {String? displayName}) async {
    if (!_supabaseService.isAvailable) {
      log('Supabase unavailable; sign-up is disabled in optional mode');
      return false;
    }
    return await safeExecute(() async {
          await _supabaseService.signUp(email, password, displayName: displayName);
          return true;
        }) ??
        false;
  }

  Future<bool> signInWithGoogle() async {
    if (!_supabaseService.isAvailable) {
      log('Supabase unavailable; Google sign-in is disabled in optional mode');
      return false;
    }
    return await safeExecute(() async {
          await _supabaseService.signInWithGoogle();
          return true;
        }) ??
        false;
  }

  void continueAsGuest() {
    _user = _guestUser;
    _session = null;
    _initialized = true;
    log('Guest session enabled');
    notifyListeners();
  }

  Future<void> signOut() async {
    if (!_supabaseService.isAvailable) {
      _user = null;
      _session = null;
      log('Supabase unavailable; cleared guest/optional auth session');
      notifyListeners();
      return;
    }
    await safeExecute(() async {
      await _supabaseService.signOut();
    });
    _user = null;
    _session = null;
    notifyListeners();
  }
}
