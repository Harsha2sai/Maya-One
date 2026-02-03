class TTSProviderModel {
  final String id;
  final String name;
  final List<String> voices;

  const TTSProviderModel({
    required this.id,
    required this.name,
    required this.voices,
  });

  Map<String, dynamic> toMap() => {
    'id': id,
    'name': name,
    'voices': voices,
  };
}

class TTSConfig {
  static const List<TTSProviderModel> providers = [
    TTSProviderModel(
      id: 'cartesia',
      name: 'Cartesia',
      voices: [
        '79a125e8-cd45-4c13-8a67-188112f4dd22', // Default voice
        'a0e99841-438c-4a64-b679-ae510a5b2f69',
        '248be419-c632-4f23-adf1-5324ed7dbf1d',
      ],
    ),
    TTSProviderModel(
      id: 'elevenlabs',
      name: 'ElevenLabs',
      voices: [
        '21m00Tcm4TlvDq8ikWAM', // Rachel
        'AZnzlk1XvdvUeBnXmlld', // Domi
        'EXAVITQu4vr4xnSDxMaL', // Sarah
        'ErXwobaYiN019PkySvjV', // Antoni
        'MF3mGyEYCl7XYWbV9V6O', // Elli
      ],
    ),
    TTSProviderModel(
      id: 'deepgram',
      name: 'Deepgram Aura',
      voices: [
        'aura-asteria-en',
        'aura-luna-en',
        'aura-stella-en',
        'aura-athena-en',
        'aura-hera-en',
        'aura-orion-en',
        'aura-arcas-en',
        'aura-perseus-en',
        'aura-angus-en',
        'aura-orpheus-en',
      ],
    ),
    TTSProviderModel(
      id: 'openai',
      name: 'OpenAI TTS',
      voices: [
        'alloy',
        'echo',
        'fable',
        'onyx',
        'nova',
        'shimmer',
      ],
    ),
    TTSProviderModel(
      id: 'groq',
      name: 'Groq TTS',
      voices: [
        'default',
      ],
    ),
    TTSProviderModel(
      id: 'aws_polly',
      name: 'AWS Polly',
      voices: [
        'Joanna',
        'Matthew',
        'Ivy',
        'Justin',
        'Kendra',
        'Kimberly',
        'Salli',
        'Joey',
        'Emma',
        'Brian',
        'Amy',
        'Raveena',
        'Aditi',
      ],
    ),
    TTSProviderModel(
      id: 'edge_tts',
      name: 'Microsoft Edge TTS',
      voices: [
        'en-IN-NeerjaNeural',
        'en-IN-PrabhatNeural',
        'hi-IN-MadhurNeural',
        'hi-IN-SwaraNeural',
        'te-IN-MohanNeural',
        'te-IN-ShrutiNeural',
        'ta-IN-PallaviNeural',
        'ta-IN-ValluvarNeural',
        'en-US-AriaNeural',
        'en-US-GuyNeural',
        'en-US-JennyNeural',
        'en-GB-SoniaNeural',
        'en-GB-RyanNeural',
      ],
    ),
  ];

  static List<Map<String, dynamic>> get providersAsMaps => 
      providers.map((p) => p.toMap()).toList();
}
