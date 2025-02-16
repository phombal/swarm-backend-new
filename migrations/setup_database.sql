-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA public;

-- Drop dependent objects first
DROP VIEW IF EXISTS public.active_simulations;

-- Drop tables if they exist (useful for resetting the database)
DROP TABLE IF EXISTS public.call_records;
DROP TABLE IF EXISTS public.simulations;

-- Create enum for simulation status
DO $$ BEGIN
    CREATE TYPE simulation_status AS ENUM (
        'initiated',
        'running',
        'completed',
        'failed',
        'stopped'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create enum for call status
DO $$ BEGIN
    CREATE TYPE call_status AS ENUM (
        'initiated',
        'ringing',
        'in-progress',
        'completed',
        'failed',
        'no-answer'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create simulations table
CREATE TABLE public.simulations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    target_phone TEXT NOT NULL,
    concurrent_calls INTEGER NOT NULL CHECK (concurrent_calls > 0 AND concurrent_calls <= 100),
    scenario JSONB NOT NULL,
    status simulation_status NOT NULL DEFAULT 'initiated',
    start_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP WITH TIME ZONE,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create call_records table
CREATE TABLE public.call_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    simulation_id UUID NOT NULL REFERENCES public.simulations(id) ON DELETE CASCADE,
    call_sid TEXT NOT NULL,
    status call_status NOT NULL DEFAULT 'initiated',
    duration INTEGER CHECK (duration >= 0),
    transcript JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(simulation_id, call_sid)
);

-- Create indexes for better query performance
CREATE INDEX idx_simulations_user_id ON public.simulations(user_id);
CREATE INDEX idx_simulations_status ON public.simulations(status);
CREATE INDEX idx_call_records_simulation_id ON public.call_records(simulation_id);
CREATE INDEX idx_call_records_call_sid ON public.call_records(call_sid);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers to automatically update updated_at
CREATE TRIGGER update_simulations_updated_at
    BEFORE UPDATE ON public.simulations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_call_records_updated_at
    BEFORE UPDATE ON public.call_records
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create view for active simulations with call counts
CREATE OR REPLACE VIEW public.active_simulations AS
SELECT 
    s.*,
    COUNT(cr.id) as active_calls,
    COUNT(CASE WHEN cr.status = 'completed' THEN 1 END) as completed_calls,
    COUNT(CASE WHEN cr.status = 'failed' THEN 1 END) as failed_calls
FROM public.simulations s
LEFT JOIN public.call_records cr ON s.id = cr.simulation_id
WHERE s.status IN ('initiated', 'running')
GROUP BY s.id;

-- Grant necessary permissions
ALTER TABLE public.simulations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.call_records ENABLE ROW LEVEL SECURITY;

-- Create policies for simulations table
DROP POLICY IF EXISTS "Enable read access for all users" ON public.simulations;
DROP POLICY IF EXISTS "Enable insert for all users" ON public.simulations;
DROP POLICY IF EXISTS "Enable update for all users" ON public.simulations;

CREATE POLICY "Enable read access for all users" ON public.simulations
    FOR SELECT USING (true);

CREATE POLICY "Enable insert for all users" ON public.simulations
    FOR INSERT WITH CHECK (
        auth.role() = 'authenticated' OR 
        user_id ILIKE 'test%'
    );

CREATE POLICY "Enable update for all users" ON public.simulations
    FOR UPDATE USING (
        auth.role() = 'authenticated' OR 
        user_id ILIKE 'test%'
    );

-- Create policies for call_records table
DROP POLICY IF EXISTS "Enable read access for all users" ON public.call_records;
DROP POLICY IF EXISTS "Enable insert for all users" ON public.call_records;
DROP POLICY IF EXISTS "Enable update for all users" ON public.call_records;

CREATE POLICY "Enable read access for all users" ON public.call_records
    FOR SELECT USING (true);

CREATE POLICY "Enable insert for all users" ON public.call_records
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.simulations s 
            WHERE s.id = simulation_id AND (
                auth.role() = 'authenticated' OR 
                s.user_id ILIKE 'test%'
            )
        )
    );

CREATE POLICY "Enable update for all users" ON public.call_records
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM public.simulations s 
            WHERE s.id = simulation_id AND (
                auth.role() = 'authenticated' OR 
                s.user_id ILIKE 'test%'
            )
        )
    );

-- Create function to clean up test data
CREATE OR REPLACE FUNCTION cleanup_test_data()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    DELETE FROM public.simulations WHERE user_id ILIKE 'test%';
END;
$$; 