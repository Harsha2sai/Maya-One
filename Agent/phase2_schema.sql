-- Phase 2: Advanced Intelligence Schema Extensions
-- Add this to your existing Supabase schema

-- Conversation History Table
CREATE TABLE IF NOT EXISTS public.conversation_history (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.conversation_history ENABLE ROW LEVEL SECURITY;

-- RLS Policy
CREATE POLICY "Users can manage own conversation history" 
  ON public.conversation_history 
  FOR ALL 
  USING (auth.uid() = user_id);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversation_user_session 
  ON public.conversation_history(user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_conversation_created 
  ON public.conversation_history(created_at DESC);
