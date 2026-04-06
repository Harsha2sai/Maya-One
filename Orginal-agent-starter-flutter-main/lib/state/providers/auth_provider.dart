import 'package:supabase_flutter/supabase_flutter.dart';
import '../base_provider.dart';
import '../../core/services/supabase_service.dart';

class AuthProvider extends BaseProvider {
  final SupabaseService _supabaseService;
  
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

  void _init() {
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
    return await safeExecute(() async {
      await _supabaseService.signIn(email, password);
      return true;
    }) ?? false;
  }

  Future<bool> signUp(String email, String password, {String? displayName}) async {
    return await safeExecute(() async {
      await _supabaseService.signUp(email, password, displayName: displayName);
      return true;
    }) ?? false;
  }

  Future<void> signOut() async {
    await safeExecute(() async {
      await _supabaseService.signOut();
    });
  }
}
