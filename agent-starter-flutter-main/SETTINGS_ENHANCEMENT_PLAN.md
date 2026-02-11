# Flutter Settings Enhancement Plan

Based on the React `settings-modal.tsx` analysis, here are all the features that need to be added to the Flutter app:

## 1. Settings Panels Structure

Current Flutter panels:
- General (partially complete)
- LLM Provider
- STT Provider
- TTS Provider  
- Memory (Mem0 toggle only)
- Account (placeholder)

### Missing/Incomplete Panels:

#### A. **General Panel** (needs enhancement)
Current: Only has interface theme (Zoya/Classic)
Add:
- **Visual Effects** toggles:
  - Quantum Particles (boolean)
  - Orbital Glow Effects (boolean)
  - Sound Effects (boolean)

#### B. **AI Providers Panel** (needs more providers)
Current LLM Providers: Groq, OpenAI
Add:
- Gemini
- Anthropic (Claude)
- DeepSeek
- Mistral
- Perplexity
- Together

#### C. **Voice & Audio Panel** (needs more providers)
Current STT Providers: Deepgram
Add:
- AssemblyAI
- Groq (for STT)
- OpenAI Whisper

Current TTS Providers: Cartesia
Add:
- ElevenLabs
- AWS Polly (special handling needed - requires Access Key + Secret + Region)
- Deepgram (for TTS)
- Groq (for TTS)

Add:
- **STT Language selection** (currently missing)
  - Options: en-US, en-GB, es, fr, de, ja, etc.

#### D. **Dedicated API Keys Panel** (completely missing)
New panel needed with sections:
- **LLM Providers**:
  - Groq, OpenAI, Gemini, Anthropic, DeepSeek, Mistral, Perplexity, Together
- **Speech Providers**:
  - Deepgram, AssemblyAI, Cartesia, ElevenLabs
- **AWS Polly** (special section):
  - Access Key ID (password field)
  - Secret Access Key (password field)
  - Region dropdown (us-east-1, us-east-2, us-west-1, us-west-2, eu-west-1, etc.)
  
Features:
- Show/hide password toggle for each key
- Status indicator (✓ Configured / ⚠️ Not set)
- Secure storage in Supabase

#### E. **Memory Panel** (needs data management)
Current: Only Mem0 enable/disable toggle
Add:
- Mem0 API Key input field
- **Data Management** section:
  - Export Memories button
  - Clear All Memories button (with confirmation)

#### F. **Personalization Panel** (completely missing)
New panel needed:
- **User Profile** section:
  - Your Name (text input)
  - Preferred Language dropdown:
    - en-US (English US)
    - en-GB (English UK)
    - es (Spanish)
    - fr (French)
    - de (German)
    - ja (Japanese)
- **Interaction Style** section:
  - Assistant Personality dropdown:
    - Professional & Concise
    - Friendly & Casual
    - Empathetic & Supportive
    - Witty & Humorous

#### G. **Account Panel** (already exists but needs enhancement)
Current: User profile card + Sign out
Keep as is - this is already good!

---

## 2. Data Model Updates

### SettingsProvider needs new fields:

```dart
class SettingsProvider extends ChangeNotifier {
  // Existing
  String userName;
  String llmProvider;
  String llmModel;
  double llmTemperature;
  String sttProvider;
  String sttModel;
  String ttsProvider;
  String ttsVoice;
  bool mem0Enabled;
  String interfaceTheme;
  
  // NEW FIELDS TO ADD:
  
  // General Panel
  bool quantumParticlesEnabled = true;
  bool orbitalGlowEnabled = true;
  bool soundEffectsEnabled = true;
  
  // Voice & Audio
  String sttLanguage = 'en-US';
  
  // AWS Polly (if ttsProvider == 'aws_polly')
  String awsAccessKey = '';
  String awsSecretKey = '';
  String awsRegion = 'us-east-1';
  
  // API Keys (as Map for flexibility)
  Map<String, String> apiKeys = {};
  Map<String, bool> apiKeyStatus = {};
  
  // Memory
  String mem0ApiKey = '';
  
  // Personalization
  String preferredLanguage = 'en-US';
  String assistantPersonality = 'professional';
  
  // Providers structure
  Map<String, dynamic> providers = {
    'llm': [...],
    'stt': [...],
    'tts': [...]
  };
}
```

---

## 3. Provider Configurations

### LLM Providers List:
```dart
final llmProviders = [
  {'id': 'groq', 'name': 'Groq', 'models': ['llama-3.1-8b-instant', '...']},
  {'id': 'openai', 'name': 'OpenAI', 'models': ['gpt-4', 'gpt-3.5-turbo']},
  {'id': 'gemini', 'name': 'Google Gemini', 'models': ['gemini-pro', 'gemini-ultra']},
  {'id': 'anthropic', 'name': 'Anthropic', 'models': ['claude-3-opus', 'claude-3-sonnet']},
  {'id': 'deepseek', 'name': 'DeepSeek', 'models': ['deepseek-coder', 'deepseek-chat']},
  {'id': 'mistral', 'name': 'Mistral AI', 'models': ['mistral-large', 'mistral-medium']},
  {'id': 'perplexity', 'name': 'Perplexity', 'models': ['sonar-small-32k', 'sonar-medium']},
  {'id': 'together', 'name': 'Together AI', 'models': ['mixtral-8x7b', 'llama-2-70b']},
  {'id': 'ollama', 'name': 'Ollama (Local)', 'models': ['llama2', 'mistral']},
  {'id': 'vllm', 'name': 'vLLM (Local)', 'models': []},
];
```

### STT Providers List:
```dart
final sttProviders = [
  {'id': 'deepgram', 'name': 'Deepgram', 'models': ['nova-2', 'nova-2-general']},
  {'id': 'assemblyai', 'name': 'AssemblyAI', 'models': ['best', 'nano']},
  {'id': 'groq', 'name': 'Groq', 'models': ['whisper-large-v3']},
  {'id': 'openai', 'name': 'OpenAI Whisper', 'models': ['whisper-1']},
];
```

### TTS Providers List:
```dart
final ttsProviders = [
  {'id': 'cartesia', 'name': 'Cartesia', 'voices': ['79a125e8-cd45-4c13-8a67-188112f4dd22', '...']},
  {'id': 'elevenlabs', 'name': 'ElevenLabs', 'voices': ['21m00Tcm4TlvDq8ikWAM', '...']},
  {'id': 'deepgram', 'name': 'Deepgram Aura', 'voices': ['aura-asteria-en', 'aura-luna-en']},
  {'id': 'openai', 'name': 'OpenAI TTS', 'voices': ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']},
  {'id': 'groq', 'name': 'Groq TTS', 'voices': []},
  {'id': 'aws_polly', 'name': 'AWS Polly', 'voices': ['Joanna', 'Matthew', 'Salli', 'Joey', '...']},
];
```

---

## 4. UI Components to Create

### New Widgets Needed:

1. **`VisualEffectsSection`** - For General panel toggles
2. **`ApiKeyInputField`** - Reusable password field with show/hide toggle
3. **`ProviderStatusBadge`** - Show ✓ Configured or ⚠️ Not set
4. **`AwsCredentialsSection`** - Special section for AWS inputs
5. **`DataManagementSection`** - Export/Clear buttons for Memory
6. **`PersonalitySelector`** - Dropdown for assistant personality

---

## 5. Implementation Priority

### Phase 1 (High Priority):
1. Add API Keys panel with all providers
2. Add AWS Polly support (TTS)
3. Add missing LLM providers (Gemini, Anthropic, etc.)
4. Add STT language selection

### Phase 2 (Medium Priority):
5. Add Personalization panel
6. Add Visual Effects toggles to General panel
7. Add Memory data management (Export/Clear)

### Phase 3 (Nice to Have):
8. Add more STT/TTS providers with proper voice/model lists
9. Add Reset to Defaults button
10. Add provider-specific help text/documentation links

---

## 6. Supabase Schema Update

The `user_settings` table needs new columns:

```sql
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS quantum_particles_enabled BOOLEAN DEFAULT true;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS orbital_glow_enabled BOOLEAN DEFAULT true;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS sound_effects_enabled BOOLEAN DEFAULT true;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS stt_language TEXT DEFAULT 'en-US';
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS preferred_language TEXT DEFAULT 'en-US';
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS assistant_personality TEXT DEFAULT 'professional';
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS api_keys JSONB DEFAULT '{}'::jsonb;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS mem0_api_key TEXT;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS aws_access_key TEXT;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS aws_secret_key TEXT;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS aws_region TEXT DEFAULT 'us-east-1';
```

---

## 7. Next Steps

1. Review this plan
2. Decide on implementation phases
3. Start with Phase 1 (API Keys panel + AWS Polly)
4. Test thoroughly with Supabase integration
5. Move to Phases 2 & 3

---

## Notes:
- All API keys should be encrypted/stored securely in Supabase
- Provider lists should be fetched from backend API `/api/settings` like in React
- Need to implement proper validation for API key inputs
- AWS credentials need special handling (3 fields instead of 1)
- Memory export/clear needs backend endpoints
