class LLMProviderModel {
  final String id;
  final String name;
  final List<String> models;

  const LLMProviderModel({
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

class LLMConfig {
  static const List<LLMProviderModel> providers = [
    LLMProviderModel(
      id: 'groq',
      name: 'Groq',
      models: [
        'llama-3.1-8b-instant',
        'llama-3.3-70b-versatile',
        'llama-3.2-90b-vision-preview',
        'mixtral-8x7b-32768',
      ],
    ),
    LLMProviderModel(
      id: 'openai',
      name: 'OpenAI',
      models: [
        'gpt-4',
        'gpt-4-turbo',
        'gpt-3.5-turbo',
        'gpt-4o',
        'gpt-4o-mini',
      ],
    ),
    LLMProviderModel(
      id: 'gemini',
      name: 'Google Gemini',
      models: [
        'gemini-pro',
        'gemini-pro-vision',
        'gemini-ultra',
        'gemini-1.5-pro',
        'gemini-1.5-flash',
      ],
    ),
    LLMProviderModel(
      id: 'anthropic',
      name: 'Anthropic (Claude)',
      models: [
        'claude-3-opus-20240229',
        'claude-3-sonnet-20240229',
        'claude-3-haiku-20240307',
        'claude-3-5-sonnet-20241022',
      ],
    ),
    LLMProviderModel(
      id: 'deepseek',
      name: 'DeepSeek',
      models: [
        'deepseek-chat',
        'deepseek-coder',
      ],
    ),
    LLMProviderModel(
      id: 'mistral',
      name: 'Mistral AI',
      models: [
        'mistral-large-latest',
        'mistral-medium-latest',
        'mistral-small-latest',
        'open-mistral-7b',
      ],
    ),
    LLMProviderModel(
      id: 'perplexity',
      name: 'Perplexity',
      models: [
        'sonar-small-32k-online',
        'sonar-medium-32k-online',
        'sonar-small-128k-chat',
      ],
    ),
    LLMProviderModel(
      id: 'together',
      name: 'Together AI',
      models: [
        'mixtral-8x7b-instruct',
        'llama-2-70b-chat',
        'mistral-7b-instruct',
      ],
    ),
    LLMProviderModel(
      id: 'ollama',
      name: 'Ollama (Local)',
      models: [
        'llama2',
        'mistral',
        'codellama',
        'neural-chat',
      ],
    ),
    LLMProviderModel(
      id: 'vllm',
      name: 'vLLM (Local)',
      models: [],
    ),
  ];

  static List<Map<String, dynamic>> get providersAsMaps => 
      providers.map((p) => p.toMap()).toList();
}
