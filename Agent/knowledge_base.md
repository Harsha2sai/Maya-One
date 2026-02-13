# Maya-One Project Knowledge Base

## System Architecture
The Maya-One agent is built on LiveKit Agents and uses a multi-layered orchestration pattern. The core components include the Intent Layer for heuristic routing, the Memory Layer for long-term persistence via Supabase, and the Governance Layer for safety.

## Voice Configuration
The agent currently supports Groq (Llama 3) for the LLM, Deepgram for STT, and Cartesia for TTS. The default voice is "Maya" which is configured in the cartesia provider settings.

## Security Policies
The agent operates with a risk-based execution gate. Critical actions like deleting user profiles or executing shell commands are restricted to users with ADMIN level authority.

## Phase 4 RAG
Phase 4 implements Retrieval Augmented Generation using Supabase pgvector and sentence-transformers. It allows the agent to recall specific project details during conversation.
