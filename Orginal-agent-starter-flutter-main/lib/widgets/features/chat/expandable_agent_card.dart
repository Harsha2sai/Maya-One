import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../../../ui/theme/app_theme.dart';

class ExpandableAgentCard extends StatefulWidget {
  final String content;
  final String? title;

  const ExpandableAgentCard({
    super.key,
    required this.content,
    this.title,
  });

  @override
  State<ExpandableAgentCard> createState() => _ExpandableAgentCardState();
}

class _ExpandableAgentCardState extends State<ExpandableAgentCard> with SingleTickerProviderStateMixin {
  bool _isExpanded = false;
  late AnimationController _controller;
  late Animation<double> _heightFactor;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _heightFactor = _controller.drive(CurveTween(curve: Curves.easeIn));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _toggleExpand() {
    setState(() {
      _isExpanded = !_isExpanded;
      if (_isExpanded) {
        _controller.forward();
      } else {
        _controller.reverse();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E2E).withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          InkWell(
            onTap: _toggleExpand,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Icon(
                    Icons.auto_awesome,
                    size: 18,
                    color: ZoyaTheme.accent.withValues(alpha: 0.8),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      widget.title ?? 'Analysis Result',
                      style: ZoyaTheme.fontDisplay.copyWith(
                        fontSize: 14,
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  Icon(
                    _isExpanded ? Icons.expand_less : Icons.expand_more,
                    color: Colors.white70,
                  ),
                ],
              ),
            ),
          ),

          // Preview or Expanded Content
          AnimatedBuilder(
            animation: _heightFactor,
            builder: (context, child) {
              return ClipRect(
                child: Align(
                  alignment: Alignment.topCenter,
                  heightFactor: _heightFactor.value,
                  child: child,
                ),
              );
            },
            child: Container(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              constraints: const BoxConstraints(maxHeight: 500),
              child: SingleChildScrollView(
                physics: const NeverScrollableScrollPhysics(),
                child: MarkdownBody(
                  data: widget.content,
                  styleSheet: MarkdownStyleSheet(
                    p: ZoyaTheme.fontBody.copyWith(color: Colors.white70, height: 1.5),
                    code: const TextStyle(backgroundColor: Colors.black26, fontFamily: 'monospace'),
                  ),
                ),
              ),
            ),
          ),

          if (!_isExpanded)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Text(
                widget.content.length > 100
                    ? "${widget.content.substring(0, 100).replaceAll("\n", " ")}..."
                    : widget.content,
                style: ZoyaTheme.fontBody.copyWith(
                  color: Colors.white54,
                  fontSize: 13,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
