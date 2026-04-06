class SharedConfig {
  static const List<Map<String, String>> awsRegions = [
    {'id': 'us-east-1', 'name': 'US East (N. Virginia)'},
    {'id': 'us-east-2', 'name': 'US East (Ohio)'},
    {'id': 'us-west-1', 'name': 'US West (N. California)'},
    {'id': 'us-west-2', 'name': 'US West (Oregon)'},
    {'id': 'eu-west-1', 'name': 'EU (Ireland)'},
    {'id': 'eu-west-2', 'name': 'EU (London)'},
    {'id': 'eu-central-1', 'name': 'EU (Frankfurt)'},
    {'id': 'ap-south-1', 'name': 'Asia Pacific (Mumbai)'},
    {'id': 'ap-northeast-1', 'name': 'Asia Pacific (Tokyo)'},
    {'id': 'ap-northeast-2', 'name': 'Asia Pacific (Seoul)'},
    {'id': 'ap-southeast-1', 'name': 'Asia Pacific (Singapore)'},
    {'id': 'ap-southeast-2', 'name': 'Asia Pacific (Sydney)'},
  ];

  static const List<Map<String, String>> preferredLanguages = [
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

  static const List<Map<String, String>> assistantPersonalities = [
    {'id': 'professional', 'name': 'Professional & Concise'},
    {'id': 'friendly', 'name': 'Friendly & Casual'},
    {'id': 'empathetic', 'name': 'Empathetic & Supportive'},
    {'id': 'humorous', 'name': 'Witty & Humorous'},
  ];
}
