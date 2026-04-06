import 'package:flutter/material.dart';

import '../../../ui/theme/app_theme.dart';

class MediaResultBubble extends StatefulWidget {
  final String trackName;
  final String provider;
  final String statusText;
  final String artist;
  final String albumArtUrl;
  final VoidCallback? onDismiss;
  final bool autoDismiss;

  const MediaResultBubble({
    super.key,
    required this.trackName,
    required this.provider,
    required this.statusText,
    this.artist = '',
    this.albumArtUrl = '',
    this.onDismiss,
    this.autoDismiss = true,
  });

  @override
  State<MediaResultBubble> createState() => _MediaResultBubbleState();
}

class _MediaResultBubbleState extends State<MediaResultBubble> {
  bool _visible = true;

  @override
  void initState() {
    super.initState();
    if (widget.autoDismiss) {
      Future<void>.delayed(const Duration(milliseconds: 3000), _dismiss);
    }
  }

  void _dismiss() {
    if (!mounted || !_visible) return;
    setState(() => _visible = false);
    widget.onDismiss?.call();
  }

  @override
  Widget build(BuildContext context) {
    if (!_visible) return const SizedBox.shrink();
    final title = widget.trackName.trim().isEmpty ? 'Media' : widget.trackName.trim();
    final provider = widget.provider.trim().isEmpty ? 'MEDIA' : widget.provider.trim().toUpperCase();

    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: const Key('media_result_bubble'),
        onTap: _dismiss,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          width: 420,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF151824).withValues(alpha: 0.96),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: ZoyaTheme.glassBorder),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.4),
                blurRadius: 18,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _AlbumArt(url: widget.albumArtUrl),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: ZoyaTheme.fontBody.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w500,
                            fontSize: 14,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          'via $provider',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: ZoyaTheme.fontBody.copyWith(
                            color: Colors.white60,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                widget.statusText,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: ZoyaTheme.fontBody.copyWith(
                  color: Colors.white70,
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AlbumArt extends StatelessWidget {
  final String url;

  const _AlbumArt({required this.url});

  @override
  Widget build(BuildContext context) {
    if (url.isEmpty) {
      return Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: Colors.white12,
          borderRadius: BorderRadius.circular(8),
        ),
        child: const Icon(Icons.music_note, color: Colors.white70, size: 18),
      );
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: Image.network(
        url,
        width: 40,
        height: 40,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: Colors.white12,
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Icon(Icons.music_note, color: Colors.white70, size: 18),
        ),
      ),
    );
  }
}
