import 'package:flutter/material.dart';

import '../../../state/providers/chat_provider.dart';
import '../../../ui/theme/app_theme.dart';
import 'source_card_item.dart';

class SourceCardsPanel extends StatefulWidget {
  final List<Source> sources;

  const SourceCardsPanel({super.key, required this.sources});

  @override
  State<SourceCardsPanel> createState() => _SourceCardsPanelState();
}

class _SourceCardsPanelState extends State<SourceCardsPanel> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    if (widget.sources.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.only(top: 12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        children: [
          InkWell(
            key: const Key('source_cards_toggle'),
            onTap: () => setState(() => _expanded = !_expanded),
            borderRadius: BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                children: [
                  Text(
                    'Sources (${widget.sources.length})',
                    style: ZoyaTheme.fontBody.copyWith(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const Spacer(),
                  Icon(
                    _expanded ? Icons.expand_less : Icons.expand_more,
                    size: 18,
                    color: Colors.white70,
                  ),
                ],
              ),
            ),
          ),
          if (_expanded)
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
              child: Column(
                key: const Key('source_cards_list'),
                children: [
                  for (final source in widget.sources) ...[
                    SourceCardItem(source: source),
                    const SizedBox(height: 8),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}
