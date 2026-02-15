-- =====================================================
-- Mail Classifier v3.0 - Migration Rules to Database
-- Extends schema with constraints, inference rules, definitions, colors
-- =====================================================

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- =====================================================
-- Table: axis_constraints
-- Stores validation constraints per axis
-- =====================================================
CREATE TABLE IF NOT EXISTS axis_constraints (
    constraint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    axis_name TEXT NOT NULL,
    constraint_text TEXT NOT NULL,
    constraint_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_axis_constraints_axis ON axis_constraints(axis_name);

-- =====================================================
-- Table: inference_rules
-- Stores inference rules (if X present -> add Y)
-- =====================================================
CREATE TABLE IF NOT EXISTS inference_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT,
    condition_prefix TEXT NOT NULL,
    condition_type TEXT DEFAULT 'present',  -- 'present', 'equals', 'contains'
    action_type TEXT NOT NULL,              -- 'add', 'remove', 'require'
    action_value TEXT NOT NULL,
    description TEXT,
    priority INTEGER DEFAULT 100,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inference_rules_prefix ON inference_rules(condition_prefix);

-- =====================================================
-- Table: definitions
-- Stores business glossary/definitions
-- =====================================================
CREATE TABLE IF NOT EXISTS definitions (
    definition_id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE,
    definition TEXT NOT NULL,
    category TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_definitions_term ON definitions(term);

-- =====================================================
-- Table: color_palette
-- Stores Outlook category colors by prefix/tag
-- =====================================================
CREATE TABLE IF NOT EXISTS color_palette (
    color_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prefix_or_tag TEXT NOT NULL UNIQUE,
    color_name TEXT NOT NULL,
    axis_name TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_color_palette_prefix ON color_palette(prefix_or_tag);

-- =====================================================
-- Extend tags table with multiplicity info if not exists
-- =====================================================
-- Note: tags table already exists from 001_initial_schema.sql

-- =====================================================
-- Extend classification_axes if needed
-- =====================================================
-- Add columns if they don't exist (SQLite doesn't support IF NOT EXISTS for ALTER)
-- These will be handled in Python migration script
