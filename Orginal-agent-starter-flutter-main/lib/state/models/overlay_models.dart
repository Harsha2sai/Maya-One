/// Overlay DTO models.
/// These are the data classes used by [OverlayController] for transient
/// UI state that exists outside of the conversation history.
library;

class SystemActionToastData {
  final String actionType;
  final String message;
  final String detail;
  final bool success;
  final bool rollbackAvailable;
  final String traceId;

  const SystemActionToastData({
    required this.actionType,
    required this.message,
    required this.detail,
    required this.success,
    required this.rollbackAvailable,
    required this.traceId,
  });
}

class MediaResultToastData {
  final String trackName;
  final String provider;
  final String statusText;
  final String artist;
  final String albumArtUrl;
  final String eventId;

  const MediaResultToastData({
    required this.trackName,
    required this.provider,
    required this.statusText,
    required this.artist,
    required this.albumArtUrl,
    required this.eventId,
  });
}

class ConfirmationPromptData {
  final String actionType;
  final String description;
  final bool destructive;
  final int timeoutSeconds;
  final String traceId;

  const ConfirmationPromptData({
    required this.actionType,
    required this.description,
    required this.destructive,
    required this.timeoutSeconds,
    required this.traceId,
  });
}
