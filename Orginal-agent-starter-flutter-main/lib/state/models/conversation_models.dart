import 'dart:convert';

enum ConversationMessageRole {
  user,
  assistant,
  system,
}

enum ConversationMessageType {
  text,
  researchResult,
  confirmationRequired,
  systemResult,
  mediaResult,
  error,
  status,
}

enum ConversationSourceChannel {
  typed,
  voice,
  structured,
}

class ConversationSourceItem {
  final String title;
  final String url;
  final String domain;
  final String snippet;
  final String provider;

  const ConversationSourceItem({
    required this.title,
    required this.url,
    this.domain = '',
    this.snippet = '',
    this.provider = '',
  });

  Map<String, dynamic> toJson() => {
        'title': title,
        'url': url,
        'domain': domain,
        'snippet': snippet,
        'provider': provider,
      };

  factory ConversationSourceItem.fromJson(Map<String, dynamic> json) {
    return ConversationSourceItem(
      title: json['title']?.toString() ?? 'Source',
      url: json['url']?.toString() ?? '',
      domain: json['domain']?.toString() ?? '',
      snippet: json['snippet']?.toString() ?? '',
      provider: json['provider']?.toString() ?? '',
    );
  }
}

class ConversationToolResultSummary {
  final String toolName;
  final String summary;
  final DateTime timestamp;
  final String? taskId;

  const ConversationToolResultSummary({
    required this.toolName,
    required this.summary,
    required this.timestamp,
    this.taskId,
  });

  Map<String, dynamic> toJson() => {
        'toolName': toolName,
        'summary': summary,
        'timestamp': timestamp.toIso8601String(),
        'taskId': taskId,
      };

  factory ConversationToolResultSummary.fromJson(Map<String, dynamic> json) {
    return ConversationToolResultSummary(
      toolName: json['toolName']?.toString() ?? '',
      summary: json['summary']?.toString() ?? '',
      timestamp: DateTime.tryParse(json['timestamp']?.toString() ?? '') ?? DateTime.now(),
      taskId: json['taskId']?.toString(),
    );
  }
}

class ConversationMessageSnapshot {
  static const int currentSchemaVersion = 1;

  final int schemaVersion;
  final String id;
  final ConversationMessageRole role;
  final ConversationMessageType messageType;
  final String content;
  final DateTime timestamp;
  final List<String> attachmentUrls;
  final List<ConversationSourceItem> sources;
  final String? turnId;
  final Map<String, dynamic> payload;
  final ConversationSourceChannel sourceChannel;
  final String originSessionId;

  const ConversationMessageSnapshot({
    required this.id,
    required this.role,
    required this.messageType,
    required this.content,
    required this.timestamp,
    this.attachmentUrls = const [],
    this.sources = const [],
    this.turnId,
    this.payload = const {},
    this.sourceChannel = ConversationSourceChannel.typed,
    this.originSessionId = '',
    this.schemaVersion = currentSchemaVersion,
  });

  ConversationMessageSnapshot copyWith({
    int? schemaVersion,
    String? id,
    ConversationMessageRole? role,
    ConversationMessageType? messageType,
    String? content,
    DateTime? timestamp,
    List<String>? attachmentUrls,
    List<ConversationSourceItem>? sources,
    String? turnId,
    Map<String, dynamic>? payload,
    ConversationSourceChannel? sourceChannel,
    String? originSessionId,
  }) {
    return ConversationMessageSnapshot(
      schemaVersion: schemaVersion ?? this.schemaVersion,
      id: id ?? this.id,
      role: role ?? this.role,
      messageType: messageType ?? this.messageType,
      content: content ?? this.content,
      timestamp: timestamp ?? this.timestamp,
      attachmentUrls: attachmentUrls ?? this.attachmentUrls,
      sources: sources ?? this.sources,
      turnId: turnId ?? this.turnId,
      payload: payload ?? this.payload,
      sourceChannel: sourceChannel ?? this.sourceChannel,
      originSessionId: originSessionId ?? this.originSessionId,
    );
  }

  Map<String, dynamic> toJson() => {
        'schemaVersion': schemaVersion,
        'id': id,
        'role': role.name,
        'messageType': messageType.name,
        'content': content,
        'timestamp': timestamp.toIso8601String(),
        'attachmentUrls': attachmentUrls,
        'sources': sources.map((source) => source.toJson()).toList(),
        'turnId': turnId,
        'payload': payload,
        'sourceChannel': sourceChannel.name,
        'originSessionId': originSessionId,
      };

  factory ConversationMessageSnapshot.fromJson(Map<String, dynamic> json) {
    final attachmentUrls = (json['attachmentUrls'] as List?)
            ?.map((item) => item.toString())
            .toList() ??
        const <String>[];
    final sources = (json['sources'] as List?)
            ?.whereType<Map>()
            .map((item) => ConversationSourceItem.fromJson(item.cast<String, dynamic>()))
            .toList() ??
        const <ConversationSourceItem>[];
    return ConversationMessageSnapshot(
      schemaVersion: json['schemaVersion'] is int ? json['schemaVersion'] as int : currentSchemaVersion,
      id: json['id']?.toString() ?? '',
      role: _parseMessageRole(json['role']?.toString()),
      messageType: _parseMessageType(json['messageType']?.toString()),
      content: json['content']?.toString() ?? '',
      timestamp: DateTime.tryParse(json['timestamp']?.toString() ?? '') ?? DateTime.now(),
      attachmentUrls: attachmentUrls,
      sources: sources,
      turnId: json['turnId']?.toString(),
      payload: (json['payload'] as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{},
      sourceChannel: _parseSourceChannel(json['sourceChannel']?.toString()),
      originSessionId: json['originSessionId']?.toString() ?? '',
    );
  }

  static ConversationMessageRole _parseMessageRole(String? raw) {
    return ConversationMessageRole.values.firstWhere(
      (value) => value.name == raw,
      orElse: () => ConversationMessageRole.assistant,
    );
  }

  static ConversationMessageType _parseMessageType(String? raw) {
    return ConversationMessageType.values.firstWhere(
      (value) => value.name == raw,
      orElse: () => ConversationMessageType.text,
    );
  }

  static ConversationSourceChannel _parseSourceChannel(String? raw) {
    return ConversationSourceChannel.values.firstWhere(
      (value) => value.name == raw,
      orElse: () => ConversationSourceChannel.typed,
    );
  }
}

class ConversationResumeEvent {
  final ConversationMessageRole role;
  final ConversationMessageType messageType;
  final String content;
  final DateTime timestamp;

  const ConversationResumeEvent({
    required this.role,
    required this.messageType,
    required this.content,
    required this.timestamp,
  });

  Map<String, dynamic> toJson() => {
        'role': role.name,
        'messageType': messageType.name,
        'content': content,
        'timestamp': timestamp.toIso8601String(),
      };

  factory ConversationResumeEvent.fromJson(Map<String, dynamic> json) {
    return ConversationResumeEvent(
      role: ConversationMessageSnapshot._parseMessageRole(json['role']?.toString()),
      messageType: ConversationMessageSnapshot._parseMessageType(json['messageType']?.toString()),
      content: json['content']?.toString() ?? '',
      timestamp: DateTime.tryParse(json['timestamp']?.toString() ?? '') ?? DateTime.now(),
    );
  }
}

class ConversationResumeContext {
  static const int currentSchemaVersion = 1;

  final int schemaVersion;
  final String topicSummary;
  final List<ConversationResumeEvent> recentEvents;
  final List<ConversationToolResultSummary> lastToolResults;
  final DateTime updatedAt;

  const ConversationResumeContext({
    this.schemaVersion = currentSchemaVersion,
    this.topicSummary = '',
    this.recentEvents = const [],
    this.lastToolResults = const [],
    required this.updatedAt,
  });

  Map<String, dynamic> toJson() => {
        'schemaVersion': schemaVersion,
        'topicSummary': topicSummary,
        'recentEvents': recentEvents.map((event) => event.toJson()).toList(),
        'lastToolResults': lastToolResults.map((result) => result.toJson()).toList(),
        'updatedAt': updatedAt.toIso8601String(),
      };

  factory ConversationResumeContext.fromJson(Map<String, dynamic> json) {
    final recentEvents = (json['recentEvents'] as List?)
            ?.whereType<Map>()
            .map((item) => ConversationResumeEvent.fromJson(item.cast<String, dynamic>()))
            .toList() ??
        const <ConversationResumeEvent>[];
    final lastToolResults = (json['lastToolResults'] as List?)
            ?.whereType<Map>()
            .map((item) => ConversationToolResultSummary.fromJson(item.cast<String, dynamic>()))
            .toList() ??
        const <ConversationToolResultSummary>[];
    return ConversationResumeContext(
      schemaVersion: json['schemaVersion'] is int ? json['schemaVersion'] as int : currentSchemaVersion,
      topicSummary: json['topicSummary']?.toString() ?? '',
      recentEvents: recentEvents,
      lastToolResults: lastToolResults,
      updatedAt: DateTime.tryParse(json['updatedAt']?.toString() ?? '') ?? DateTime.now(),
    );
  }
}

class ConversationRecord {
  final String id;
  final String title;
  final String preview;
  final DateTime createdAt;
  final DateTime updatedAt;
  final bool archived;
  final String? projectId;
  final List<ConversationMessageSnapshot> messages;
  final ConversationResumeContext resumeContext;
  final bool autoTitleLocked;

  const ConversationRecord({
    required this.id,
    required this.title,
    required this.preview,
    required this.createdAt,
    required this.updatedAt,
    required this.archived,
    this.projectId,
    this.messages = const [],
    required this.resumeContext,
    this.autoTitleLocked = false,
  });

  ConversationRecord copyWith({
    String? id,
    String? title,
    String? preview,
    DateTime? createdAt,
    DateTime? updatedAt,
    bool? archived,
    String? projectId,
    bool clearProjectId = false,
    List<ConversationMessageSnapshot>? messages,
    ConversationResumeContext? resumeContext,
    bool? autoTitleLocked,
  }) {
    return ConversationRecord(
      id: id ?? this.id,
      title: title ?? this.title,
      preview: preview ?? this.preview,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      archived: archived ?? this.archived,
      projectId: clearProjectId ? null : (projectId ?? this.projectId),
      messages: messages ?? this.messages,
      resumeContext: resumeContext ?? this.resumeContext,
      autoTitleLocked: autoTitleLocked ?? this.autoTitleLocked,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'preview': preview,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
        'archived': archived,
        'projectId': projectId,
        'messages': messages.map((message) => message.toJson()).toList(),
        'resumeContext': resumeContext.toJson(),
        'autoTitleLocked': autoTitleLocked,
      };

  factory ConversationRecord.fromJson(Map<String, dynamic> json) {
    final messages = (json['messages'] as List?)
            ?.whereType<Map>()
            .map((item) => ConversationMessageSnapshot.fromJson(item.cast<String, dynamic>()))
            .toList() ??
        const <ConversationMessageSnapshot>[];
    final resumeContextRaw = (json['resumeContext'] as Map?)?.cast<String, dynamic>();
    return ConversationRecord(
      id: json['id']?.toString() ?? '',
      title: json['title']?.toString() ?? 'New chat',
      preview: json['preview']?.toString() ?? '',
      createdAt: DateTime.tryParse(json['createdAt']?.toString() ?? '') ?? DateTime.now(),
      updatedAt: DateTime.tryParse(json['updatedAt']?.toString() ?? '') ?? DateTime.now(),
      archived: json['archived'] == true,
      projectId: json['projectId']?.toString(),
      messages: messages,
      resumeContext: resumeContextRaw != null
          ? ConversationResumeContext.fromJson(resumeContextRaw)
          : ConversationResumeContext(updatedAt: DateTime.now()),
      autoTitleLocked: json['autoTitleLocked'] == true,
    );
  }
}

class ProjectRecord {
  final String id;
  final String name;
  final String description;
  final DateTime createdAt;
  final DateTime updatedAt;
  final Map<String, dynamic> metadata;

  const ProjectRecord({
    required this.id,
    required this.name,
    this.description = '',
    required this.createdAt,
    required this.updatedAt,
    this.metadata = const {},
  });

  ProjectRecord copyWith({
    String? id,
    String? name,
    String? description,
    DateTime? createdAt,
    DateTime? updatedAt,
    Map<String, dynamic>? metadata,
  }) {
    return ProjectRecord(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      metadata: metadata ?? this.metadata,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'description': description,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
        'metadata': metadata,
      };

  factory ProjectRecord.fromJson(Map<String, dynamic> json) {
    return ProjectRecord(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? 'Project',
      description: json['description']?.toString() ?? '',
      createdAt: DateTime.tryParse(json['createdAt']?.toString() ?? '') ?? DateTime.now(),
      updatedAt: DateTime.tryParse(json['updatedAt']?.toString() ?? '') ?? DateTime.now(),
      metadata: (json['metadata'] as Map?)?.cast<String, dynamic>() ?? const <String, dynamic>{},
    );
  }
}

class ConversationStoreSnapshot {
  static const int currentSchemaVersion = 1;

  final int schemaVersion;
  final String activeConversationId;
  final List<ConversationRecord> conversations;
  final List<ProjectRecord> projects;

  const ConversationStoreSnapshot({
    this.schemaVersion = currentSchemaVersion,
    required this.activeConversationId,
    this.conversations = const [],
    this.projects = const [],
  });

  Map<String, dynamic> toJson() => {
        'schemaVersion': schemaVersion,
        'activeConversationId': activeConversationId,
        'conversations': conversations.map((conversation) => conversation.toJson()).toList(),
        'projects': projects.map((project) => project.toJson()).toList(),
      };

  String toJsonString() => jsonEncode(toJson());

  factory ConversationStoreSnapshot.fromJson(Map<String, dynamic> json) {
    final conversations = (json['conversations'] as List?)
            ?.whereType<Map>()
            .map((item) => ConversationRecord.fromJson(item.cast<String, dynamic>()))
            .toList() ??
        const <ConversationRecord>[];
    final projects = (json['projects'] as List?)
            ?.whereType<Map>()
            .map((item) => ProjectRecord.fromJson(item.cast<String, dynamic>()))
            .toList() ??
        const <ProjectRecord>[];
    return ConversationStoreSnapshot(
      schemaVersion: json['schemaVersion'] is int ? json['schemaVersion'] as int : currentSchemaVersion,
      activeConversationId: json['activeConversationId']?.toString() ?? '',
      conversations: conversations,
      projects: projects,
    );
  }
}
