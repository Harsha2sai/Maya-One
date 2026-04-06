import 'package:flutter/material.dart';
import '../../ui/zoya_theme.dart';

class ZoyaButton extends StatelessWidget {
  final String text;
  final VoidCallback onPressed;
  final bool isSecondary;
  final bool isProgressing;

  const ZoyaButton({
    super.key,
    required this.text,
    required this.onPressed,
    this.isSecondary = false,
    this.isProgressing = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: isProgressing ? null : onPressed,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 32),
        decoration: BoxDecoration(
          color: isSecondary ? Colors.transparent : ZoyaTheme.accent,
          border: isSecondary ? Border.all(color: ZoyaTheme.accent) : null,
          borderRadius: BorderRadius.circular(30),
          boxShadow: isSecondary
              ? null
              : [
                  BoxShadow(
                    color: ZoyaTheme.accentGlow,
                    blurRadius: 20,
                    offset: const Offset(0, 0),
                  ),
                ],
        ),
        child: isProgressing 
          ? const SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(color: Colors.black, strokeWidth: 2),
            )
          : Text(
            text.toUpperCase(),
            style: ZoyaTheme.fontDisplay.copyWith(
              color: isSecondary ? ZoyaTheme.accent : Colors.black,
              fontSize: 16,
              fontWeight: FontWeight.bold,
              letterSpacing: 1.5,
            ),
          ),
      ),
    );
  }
}
