import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../core/services/assistant_content_normalizer.dart';
import '../../../ui/theme/app_theme.dart';
import '../../../state/providers/chat_provider.dart' show Source;

class AssistantMessagePanel extends StatelessWidget {
  final String content;
  final bool isLive;
  final bool canExpand;
  final List<Source> sources;

  const AssistantMessagePanel({
    super.key,
    required this.content,
    required this.isLive,
    required this.canExpand,
    this.sources = const [],
  });

  List<Source> _extractSourcesFromContent(String text) {
    final urls = <String>{};
    final markdownLink = RegExp(r'\[[^\]]+\]\((https?://[^\s)]+)\)');
    for (final match in markdownLink.allMatches(text)) {
      urls.add(match.group(1) ?? '');
    }
    final rawUrl = RegExp(r'https?://\S+');
    for (final match in rawUrl.allMatches(text)) {
      urls.add(match.group(0) ?? '');
    }
    urls.removeWhere((u) => u.isEmpty);
    return urls.map((u) => Source(title: u, url: u)).toList();
  }

  Future<void> _copyToClipboard(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: normalizeAssistantContent(content)));
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Copied to clipboard')),
      );
    }
  }

  void _showSources(BuildContext context, List<Source> sources) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: ZoyaTheme.sidebarBg,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: sources.length + 1,
            separatorBuilder: (_, __) => Divider(color: Colors.white.withValues(alpha: 0.1)),
            itemBuilder: (context, index) {
              if (index == 0) {
                return Text(
                  'Sources',
                  style: ZoyaTheme.fontDisplay.copyWith(fontSize: 16, color: ZoyaTheme.textMain),
                );
              }
              final source = sources[index - 1];
              final url = source.url;
              return ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(
                  source.title.isNotEmpty ? source.title : url,
                  style: ZoyaTheme.fontBody.copyWith(color: Colors.white70, fontSize: 13),
                ),
                subtitle: source.snippet != null
                    ? Text(
                        source.snippet!,
                        style: ZoyaTheme.fontBody.copyWith(color: Colors.white54, fontSize: 12),
                      )
                    : null,
                trailing: const Icon(Icons.open_in_new, size: 18),
                onTap: () async {
                  final uri = Uri.tryParse(url);
                  if (uri != null) {
                    await launchUrl(uri, mode: LaunchMode.externalApplication);
                  }
                },
              );
            },
          ),
        );
      },
    );
  }

  void _openFullScreen(BuildContext context) {
    showDialog(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.6),
      builder: (ctx) {
        return Dialog(
          insetPadding: EdgeInsets.zero,
          backgroundColor: Colors.transparent,
          child: Scaffold(
            backgroundColor: ZoyaTheme.mainBg,
            appBar: AppBar(
              backgroundColor: ZoyaTheme.sidebarBg,
              title: Text(
                'Response',
                style: ZoyaTheme.fontDisplay.copyWith(fontSize: 16, color: ZoyaTheme.textMain),
              ),
              leading: IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.of(ctx).pop(),
              ),
            ),
            body: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: MarkdownBody(
                data: normalizeAssistantContent(content),
                selectable: true,
                styleSheet: MarkdownStyleSheet(
                  p: ZoyaTheme.fontBody.copyWith(color: Colors.white70, height: 1.6, fontSize: 15),
                  code: const TextStyle(backgroundColor: Colors.black26, fontFamily: 'monospace'),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final normalizedContent = normalizeAssistantContent(content);
    final effectiveSources = sources.isNotEmpty ? sources : _extractSourcesFromContent(normalizedContent);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ZoyaTheme.glassBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isLive ? ZoyaTheme.accent.withValues(alpha: 0.3) : ZoyaTheme.glassBorder,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.25),
            blurRadius: 12,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Stack(
        children: [
          Padding(
            padding: EdgeInsets.only(right: (canExpand || effectiveSources.isNotEmpty) ? 72 : 0),
            child: MarkdownBody(
              data: normalizedContent,
              selectable: true,
              styleSheet: MarkdownStyleSheet(
                p: ZoyaTheme.fontBody.copyWith(color: Colors.white70, height: 1.6, fontSize: 15),
                code: const TextStyle(backgroundColor: Colors.black26, fontFamily: 'monospace'),
              ),
            ),
          ),
          Positioned(
            right: 0,
            top: 0,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  icon: const Icon(Icons.copy, size: 18),
                  color: Colors.white70,
                  tooltip: 'Copy',
                  onPressed: () => _copyToClipboard(context),
                ),
                if (effectiveSources.isNotEmpty)
                  IconButton(
                    icon: const Icon(Icons.link, size: 18),
                    color: Colors.white70,
                    tooltip: 'Sources',
                    onPressed: () => _showSources(context, effectiveSources),
                  ),
                PopupMenuButton<String>(
                  icon: const Icon(Icons.more_horiz, size: 18),
                  color: Colors.white70,
                  onSelected: (value) {
                    if (value == 'copy') {
                      _copyToClipboard(context);
                    } else if (value == 'sources') {
                      _showSources(context, effectiveSources);
                    } else if (value == 'expand') {
                      _openFullScreen(context);
                    }
                  },
                  itemBuilder: (ctx) => [
                    const PopupMenuItem(value: 'copy', child: Text('Copy')),
                    if (effectiveSources.isNotEmpty) const PopupMenuItem(value: 'sources', child: Text('Show Sources')),
                    if (canExpand) const PopupMenuItem(value: 'expand', child: Text('Expand')),
                  ],
                ),
                if (canExpand)
                  IconButton(
                    icon: const Icon(Icons.open_in_full, size: 18),
                    color: Colors.white70,
                    tooltip: 'Expand',
                    onPressed: () => _openFullScreen(context),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
