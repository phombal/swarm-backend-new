-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA public;

-- Create simulations table
CREATE TABLE IF NOT EXISTS simulations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    target_phone TEXT NOT NULL,
    concurrent_calls INTEGER NOT NULL,
    scenario JSONB NOT NULL,
    status TEXT NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP WITH TIME ZONE,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create call_records table
CREATE TABLE IF NOT EXISTS voice_conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    simulation_id TEXT NOT NULL,
    call_sid TEXT NOT NULL,
    twilio_call_sid TEXT,
    phone_number TEXT,
    status TEXT NOT NULL,
    duration INTEGER,
    transcript JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Update voice_conversations table
ALTER TABLE voice_conversations
    ADD COLUMN IF NOT EXISTS twilio_call_sid TEXT,
    ADD COLUMN IF NOT EXISTS duration INTEGER,
    ALTER COLUMN transcript SET DEFAULT '[]'::jsonb,
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN simulation_id SET NOT NULL,
    ALTER COLUMN call_sid SET NOT NULL;

-- Add updated_at trigger if it doesn't exist
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_voice_conversations_updated_at ON voice_conversations;
CREATE TRIGGER update_voice_conversations_updated_at
    BEFORE UPDATE ON voice_conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column(); 