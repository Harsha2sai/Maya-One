import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../state/providers/chat_provider.dart';
import '../../../ui/theme/app_theme.dart';

class SourceCardItem extends StatelessWidget {
  final Source source;

  const SourceCardItem({super.key, required this.source});

  String _domainLabel() {
    if (source.domain.trim().isNotEmpty) {
      return source.domain.trim();
    }
    final uri = Uri.tryParse(source.url);
    if (uri != null && uri.host.trim().isNotEmpty) {
      return uri.host.replaceFirst('www.', '');
    }
    return 'source';
  }

  @override
  Widget build(BuildContext context) {
    final domain = _domainLabel();
    final favicon = 'https://www.google.com/s2/favicons?domain=$domain&sz=32';
    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: Key('source_card_${source.title}'),
        borderRadius: BorderRadius.circular(12),
        onTap: () async {
          final uri = Uri.tryParse(source.url);
          if (uri == null) {
            return;
          }
          await launchUrl(uri, mode: LaunchMode.externalApplication);
        },
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: ZoyaTheme.sidebarBg.withValues(alpha: 0.55),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.network(
                  favicon,
                  width: 18,
                  height: 18,
                  errorBuilder: (_, __, ___) => const Icon(Icons.language, size: 18),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      domain,
                      style: ZoyaTheme.fontBody.copyWith(
                        color: Colors.white54,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      source.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: ZoyaTheme.fontBody.copyWith(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if ((source.snippet ?? '').trim().isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        source.snippet!.trim(),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: ZoyaTheme.fontBody.copyWith(
                          color: Colors.white70,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
