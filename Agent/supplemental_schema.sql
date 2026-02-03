-- Supplemental Schema for Zoya Agent Tools
-- Run this in your Supabase SQL Editor

-- 1. Alarms Table
CREATE TABLE IF NOT EXISTS public.user_alarms (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  alarm_time TIMESTAMPTZ NOT NULL,
  label TEXT DEFAULT 'Alarm',
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Reminders Table
CREATE TABLE IF NOT EXISTS public.user_reminders (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  remind_at TIMESTAMPTZ NOT NULL,
  is_completed BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Notes Table
CREATE TABLE IF NOT EXISTS public.user_notes (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  content TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Calendar Events Table
CREATE TABLE IF NOT EXISTS public.user_calendar_events (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);


-- Enable RLS
ALTER TABLE public.user_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_notes ENABLE ROW LEVEL SECURITY;

-- RLS Policies (Simple UID check)
CREATE POLICY "Users can manage own alarms" ON public.user_alarms FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can manage own reminders" ON public.user_reminders FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users can manage own notes" ON public.user_notes FOR ALL USING (auth.uid() = user_id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_alarms_user ON public.user_alarms(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON public.user_reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_user ON public.user_notes(user_id);

-- Calendar Events RLS & Index
ALTER TABLE public.user_calendar_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own calendar events" ON public.user_calendar_events FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_calendar_events_user ON public.user_calendar_events(user_id);

