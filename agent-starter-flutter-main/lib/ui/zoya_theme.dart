import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class ZoyaTheme {
  // --- Colors (Matched from globals.css) ---
  static const Color mainBg = Color(0xFF050510);
  static const Color sidebarBg = Color(0xFF0A0A14);
  static const Color accent = Color(0xFF00F3FF); // Cyan
  static const Color accentGlow = Color.fromRGBO(0, 243, 255, 0.4);
  static const Color secondaryAccent = Color(0xFFBC13FE); // Purple
  static const Color danger = Color(0xFFFF2A6D);
  static const Color success = Color(0xFF05D5FA);

  static final Color glassBg = const Color(0xFF141423).withValues(alpha: 0.6);
  static final Color glassBorder = const Color(0xFF64C8FF).withValues(alpha: 0.1);

  static const Color textMain = Color(0xFFE0E6ED);
  static const Color textMuted = Color(0xFF6C7A89);

  // --- Gradients ---
  static const RadialGradient bgGradient = RadialGradient(
    center: Alignment(0.2, -0.3), // 20% 30%
    radius: 1.5,
    colors: [
      Color(0xFF0A0A1A),
      Color(0xFF050510), // fade to transparent-ish
    ],
    stops: [0.0, 1.0],
  );

  static const RadialGradient bgGradient2 = RadialGradient(
    center: Alignment(0.6, 0.6), // 80% 70%
    radius: 1.5,
    colors: [
      Color(0xFF0F0F20),
      Colors.transparent,
    ],
    stops: [0.0, 0.5],
  );

  // --- Orb Colors (Matched from CSS) ---
  static const Color orbCore = Color(0xFFA855F7); // Purple 500
  static const Color orbInner = Color(0xFF9333EA); // Purple 600
  static const Color orbOuter = Color(0xFFC084FC); // Purple 400
  
  // --- Text Styles ---
  static TextStyle get fontDisplay => GoogleFonts.orbitron();
  static TextStyle get fontBody => GoogleFonts.roboto();
  
  static TextStyle get statusLabel => fontBody.copyWith(
    fontSize: 12, // 0.85em approx
    color: textMuted,
  );
  
  static TextStyle get statusValue => GoogleFonts.robotoMono(
    fontSize: 12,
    color: textMain,
  );

  static ThemeData get themeData {
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: mainBg,
      brightness: Brightness.dark,
      primaryColor: accent,
      colorScheme: const ColorScheme.dark(
        primary: accent,
        secondary: secondaryAccent,
        surface: sidebarBg,
        error: danger,
        onPrimary: Colors.black,
        onSecondary: Colors.white,
        onSurface: textMain,
      ),
      textTheme: TextTheme(
        displayLarge: fontDisplay.copyWith(fontSize: 32, fontWeight: FontWeight.bold, color: textMain),
        displayMedium: fontDisplay.copyWith(fontSize: 24, fontWeight: FontWeight.w500, color: textMain),
        bodyLarge: fontBody.copyWith(fontSize: 16, color: textMain),
        bodyMedium: fontBody.copyWith(fontSize: 14, color: textMain),
        bodySmall: fontBody.copyWith(fontSize: 12, color: textMuted),
      ),
      iconTheme: const IconThemeData(color: textMain, size: 20),
    );
  }
}
