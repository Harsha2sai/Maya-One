String normalizeAssistantContent(String raw) {
  if (raw.isEmpty) {
    return raw;
  }

  var normalized = raw;
  if (!normalized.contains('\n') && normalized.contains(r'\n')) {
    normalized = normalized.replaceAll(r'\n', '\n');
  }
  if (!normalized.contains('\t') && normalized.contains(r'\t')) {
    normalized = normalized.replaceAll(r'\t', '\t');
  }
  if (!normalized.contains('\r') && normalized.contains(r'\r')) {
    normalized = normalized.replaceAll(r'\r', '\r');
  }
  return normalized;
}
