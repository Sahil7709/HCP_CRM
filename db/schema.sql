-- AI-First HCP CRM — Log Interaction schema (PostgreSQL)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE interaction_type AS ENUM (
    'IN_PERSON_VISIT', 'VIRTUAL_MEETING', 'PHONE_CALL', 'EMAIL', 'CONFERENCE_BOOTH', 'SPEAKER_PROGRAM'
);
CREATE TYPE interaction_status AS ENUM ('DRAFT', 'PENDING_REVIEW', 'SUBMITTED');
CREATE TYPE entry_mode AS ENUM ('STRUCTURED_FORM', 'CONVERSATIONAL');
CREATE TYPE follow_up_status AS ENUM ('OPEN', 'DONE');

CREATE TABLE hcps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_name VARCHAR(120) NOT NULL,
    last_name VARCHAR(120) NOT NULL,
    npi_number VARCHAR(20) UNIQUE,
    specialty VARCHAR(120),
    institution VARCHAR(255),
    tier VARCHAR(20),
    email VARCHAR(255),
    phone VARCHAR(50)
);
CREATE INDEX idx_hcps_npi ON hcps (npi_number);
CREATE INDEX idx_hcps_name ON hcps (last_name, first_name);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    brand_code VARCHAR(50),
    is_sample_eligible BOOLEAN DEFAULT FALSE
);

CREATE TABLE interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hcp_id UUID NOT NULL REFERENCES hcps(id),
    -- Not a UUID FK on purpose: there's no IAM/users table in this deliverable,
    -- so rep_id is whatever opaque id the auth layer hands us.
    rep_id VARCHAR(64) NOT NULL,
    interaction_type interaction_type NOT NULL,
    interaction_datetime TIMESTAMP NOT NULL,
    duration_minutes INTEGER,
    channel_location VARCHAR(255),
    key_message_notes TEXT,
    hcp_sentiment VARCHAR(20),
    interest_level INTEGER CHECK (interest_level BETWEEN 1 AND 5),
    follow_up_required BOOLEAN DEFAULT FALSE,
    follow_up_action TEXT,
    follow_up_due_date TIMESTAMP,
    entry_mode entry_mode NOT NULL DEFAULT 'STRUCTURED_FORM',
    status interaction_status NOT NULL DEFAULT 'DRAFT',
    compliance_flags JSONB DEFAULT '[]',
    source_transcript TEXT,
    ai_confidence_score NUMERIC(3,2),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_interactions_hcp ON interactions (hcp_id);
CREATE INDEX idx_interactions_rep ON interactions (rep_id);
CREATE INDEX idx_interactions_status ON interactions (status);

CREATE TABLE interaction_products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interaction_id UUID NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    detailing_sequence INTEGER,
    reaction_notes TEXT
);

CREATE TABLE sample_drops (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interaction_id UUID NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    lot_number VARCHAR(50),
    hcp_signature_captured BOOLEAN DEFAULT FALSE
);

CREATE TABLE materials_shared (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interaction_id UUID NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    material_name VARCHAR(255) NOT NULL,
    material_type VARCHAR(50)
);

-- Created by the schedule_follow_up LangGraph tool; a commitment tied to an HCP
-- that isn't itself an interaction (e.g. "send updated efficacy data next week").
CREATE TABLE follow_ups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hcp_id UUID NOT NULL REFERENCES hcps(id),
    rep_id VARCHAR(64) NOT NULL,
    interaction_id UUID REFERENCES interactions(id),
    action TEXT NOT NULL,
    due_date TIMESTAMP,
    status follow_up_status NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_follow_ups_hcp ON follow_ups (hcp_id);
CREATE INDEX idx_follow_ups_rep ON follow_ups (rep_id);
