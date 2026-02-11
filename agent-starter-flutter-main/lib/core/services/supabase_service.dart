import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:logging/logging.dart';

class SupabaseService {
  final Logger _logger = Logger('SupabaseService');

  static final SupabaseService _instance = SupabaseService._internal();
  factory SupabaseService() => _instance;
  SupabaseService._internal();

  SupabaseClient get client => Supabase.instance.client;

  Future<void> initialize() async {
    final url = dotenv.env['SUPABASE_URL'];
    final anonKey = dotenv.env['SUPABASE_ANON_KEY'];

    if (url == null || anonKey == null) {
      _logger.severe('Supabase URL or Anon Key not found in environment variables');
      return;
    }

    _logger.info('Initializing Supabase...');
    await Supabase.initialize(
      url: url,
      anonKey: anonKey,
    );
    _logger.info('Supabase initialized successfully');
  }

  /// Auth helpers
  User? get currentUser => client.auth.currentUser;
  Session? get currentSession => client.auth.currentSession;
  Stream<AuthState> get authStateChanges => client.auth.onAuthStateChange;

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
}
