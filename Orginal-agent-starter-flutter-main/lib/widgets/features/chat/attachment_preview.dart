import 'dart:io';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class AttachmentPreview extends StatelessWidget {
  final File file;
  final VoidCallback onRemove;

  const AttachmentPreview({
    super.key,
    required this.file,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    final isImage = ['.jpg', '.jpeg', '.png', '.gif', '.webp'].any((ext) => file.path.toLowerCase().endsWith(ext));

    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: 70,
            height: 70,
            decoration: BoxDecoration(
              color: const Color(0xFF2A2A35),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.white12),
              image: isImage
                  ? DecorationImage(
                      image: FileImage(file),
                      fit: BoxFit.cover,
                    )
                  : null,
            ),
            child: isImage
                ? null
                : Center(
                    child: FaIcon(
                      _getFileIcon(),
                      color: Colors.white70,
                      size: 24,
                    ),
                  ),
          ),
          Positioned(
            top: -6,
            right: -6,
            child: GestureDetector(
              onTap: onRemove,
              child: Container(
                padding: const EdgeInsets.all(4),
                decoration: const BoxDecoration(
                  color: Colors.redAccent,
                  shape: BoxShape.circle,
                ),
                child: const FaIcon(
                  FontAwesomeIcons.xmark,
                  size: 10,
                  color: Colors.white,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  FaIconData _getFileIcon() {
    final ext = file.path.split('.').last.toLowerCase();
    switch (ext) {
      case 'pdf':
        return FontAwesomeIcons.filePdf;
      case 'doc':
      case 'docx':
        return FontAwesomeIcons.fileWord;
      case 'csv':
      case 'xls':
      case 'xlsx':
        return FontAwesomeIcons.fileExcel;
      case 'txt':
      case 'md':
        return FontAwesomeIcons.fileLines;
      default:
        return FontAwesomeIcons.file;
    }
  }
}
