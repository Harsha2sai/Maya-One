-- Phase 2: Supabase Schema Updates for Enhanced Settings
-- Run this SQL in your Supabase SQL Editor

-- Add new columns to user_settings table
ALTER TABLE user_settings 
  ADD COLUMN IF NOT EXISTS stt_model TEXT DEFAULT 'nova-2',
  ADD COLUMN IF NOT EXISTS stt_language TEXT DEFAULT 'en-US',
  ADD COLUMN IF NOT EXISTS quantum_particles_enabled BOOLEAN DEFAULT true,
  ADD COLUMN IF NOT EXISTS orbital_glow_enabled BOOLEAN DEFAULT true,
  ADD COLUMN IF NOT EXISTS sound_effects_enabled BOOLEAN DEFAULT true,
  ADD COLUMN IF NOT EXISTS preferred_language TEXT DEFAULT 'en-US',
  ADD COLUMN IF NOT EXISTS assistant_personality TEXT DEFAULT 'professional',
  ADD COLUMN IF NOT EXISTS mem0_api_key TEXT,
  ADD COLUMN IF NOT EXISTS aws_access_key TEXT,
  ADD COLUMN IF NOT EXISTS aws_secret_key TEXT,
  ADD COLUMN IF NOT EXISTS aws_region TEXT DEFAULT 'us-east-1',
  ADD COLUMN IF NOT EXISTS api_keys JSONB DEFAULT '{}'::jsonb;

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);
CREATE INDEX IF NOT EXISTS idx_user_settings_updated_at ON user_settings(updated_at);

-- Add RLS (Row Level Security) policies if not already present
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own settings
CREATE POLICY IF NOT EXISTS "Users can view own settings"
  ON user_settings FOR SELECT
  USING (auth.uid() = user_id);

-- Policy: Users can insert their own settings
CREATE POLICY IF NOT EXISTS "Users can insert own settings"
  ON user_settings FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Policy: Users can update their own settings
CREATE POLICY IF NOT EXISTS "Users can update own settings"
  ON user_settings FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Policy: Users can delete their own settings
CREATE POLICY IF NOT EXISTS "Users can delete own settings"
  ON user_settings FOR DELETE
  USING (auth.uid() = user_id);

-- Optional: Add trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_user_settings_updated_at ON user_settings;
CREATE TRIGGER update_user_settings_updated_at
  BEFORE UPDATE ON user_settings
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Verify the schema
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'user_settings' 
ORDER BY ordinal_position;
