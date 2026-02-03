class STTProviderModel {
  final String id;
  final String name;
  final List<String> models;

  const STTProviderModel({
    required this.id,
    required this.name,
    required this.models,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'name': name,
    'models': models,
  };
}

class STTConfig {
  static const List<STTProviderModel> providers = [
    STTProviderModel(
      id: 'deepgram',
      name: 'Deepgram',
      models: [
        'nova-2',
        'nova-2-general',
        'nova-2-meeting',
        'nova-2-phonecall',
      ],
    ),
    STTProviderModel(
      id: 'assemblyai',
      name: 'AssemblyAI',
      models: [
        'best',
        'nano',
      ],
    ),
    STTProviderModel(
      id: 'groq',
      name: 'Groq Whisper',
      models: [
        'whisper-large-v3',
        'whisper-large-v3-turbo',
      ],
    ),
    STTProviderModel(
      id: 'openai',
      name: 'OpenAI Whisper',
      models: [
        'whisper-1',
      ],
    ),
  ];

  static List<Map<String, dynamic>> get providersAsMaps => 
      providers.map((p) => p.toMap()).toList();

  static const List<Map<String, String>> languages = [
    {'id': 'en-US', 'name': 'English (United States)'},
    {'id': 'en-GB', 'name': 'English (United Kingdom)'},
    {'id': 'en-IN', 'name': 'English (India)'},
    {'id': 'hi', 'name': 'Hindi (हिन्दी)'},
    {'id': 'te', 'name': 'Telugu (తెలుగు)'},
    {'id': 'ta', 'name': 'Tamil (தமிழ்)'},
    {'id': 'es', 'name': 'Spanish (Español)'},
    {'id': 'fr', 'name': 'French (Français)'},
    {'id': 'de', 'name': 'German (Deutsch)'},
    {'id': 'it', 'name': 'Italian (Italiano)'},
    {'id': 'pt', 'name': 'Portuguese (Português)'},
    {'id': 'ja', 'name': 'Japanese (日本語)'},
    {'id': 'ko', 'name': 'Korean (한국어)'},
    {'id': 'zh', 'name': 'Chinese (中文)'},
    {'id': 'ar', 'name': 'Arabic (العربية)'},
    {'id': 'ru', 'name': 'Russian (Русский)'},
  ];
}
