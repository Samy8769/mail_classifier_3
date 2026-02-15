-- =====================================================
-- Mail Classifier v2.0 - Initial Database Schema
-- SQLite standard (no extensions required)
-- =====================================================

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- =====================================================
-- Table: emails
-- Stores email metadata with full text
-- =====================================================
CREATE TABLE IF NOT EXISTS emails (
    email_id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    subject TEXT,
    sender_email TEXT,
    sender_name TEXT,
    recipients TEXT,
    body TEXT NOT NULL,
    received_time TIMESTAMP,
    conversation_topic TEXT,
    outlook_categories TEXT,
    processed_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_emails_conversation_id ON emails(conversation_id);
CREATE INDEX IF NOT EXISTS idx_emails_received_time ON emails(received_time);
CREATE INDEX IF NOT EXISTS idx_emails_sender_email ON emails(sender_email);

-- =====================================================
-- Table: email_chunks
-- Stores chunked email content with token counts
-- =====================================================
CREATE TABLE IF NOT EXISTS email_chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    chunk_type TEXT CHECK(chunk_type IN ('full', 'paragraph_group', 'sentence_group')),
    previous_chunk_overlap TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (email_id) REFERENCES emails(email_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_email_chunks_email_id ON email_chunks(email_id, chunk_index);

-- =====================================================
-- Table: embeddings
-- Stores embedding metadata (arrays on filesystem)
-- =====================================================
CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id INTEGER UNIQUE NOT NULL,
    embedding_path TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (chunk_id) REFERENCES email_chunks(chunk_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_embeddings_chunk_id ON embeddings(chunk_id);

-- =====================================================
-- Table: tags
-- Centralized tag repository (replaces regles_mail_*.txt)
-- =====================================================
CREATE TABLE IF NOT EXISTS tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name TEXT UNIQUE NOT NULL,
    axis_name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    description TEXT,
    tag_metadata TEXT,  -- JSON string
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tags_axis_name ON tags(axis_name);
CREATE INDEX IF NOT EXISTS idx_tags_prefix ON tags(prefix);
CREATE INDEX IF NOT EXISTS idx_tags_active ON tags(is_active);

-- =====================================================
-- Table: tag_classifications
-- Links emails/chunks to tags (many-to-many)
-- =====================================================
CREATE TABLE IF NOT EXISTS tag_classifications (
    classification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER NOT NULL,
    chunk_id INTEGER,
    tag_id INTEGER NOT NULL,
    confidence_score REAL,
    classified_by TEXT CHECK(classified_by IN ('llm', 'human', 'rule', 'search')),
    llm_model TEXT,
    validated INTEGER DEFAULT 0,
    validation_timestamp TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (email_id) REFERENCES emails(email_id) ON DELETE CASCADE,
    FOREIGN KEY (chunk_id) REFERENCES email_chunks(chunk_id) ON DELETE SET NULL,
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tag_classifications_email_id ON tag_classifications(email_id);
CREATE INDEX IF NOT EXISTS idx_tag_classifications_chunk_id ON tag_classifications(chunk_id);
CREATE INDEX IF NOT EXISTS idx_tag_classifications_tag_id ON tag_classifications(tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_classifications_validated ON tag_classifications(validated);

-- =====================================================
-- Table: classification_axes
-- Stores axis definitions
-- =====================================================
CREATE TABLE IF NOT EXISTS classification_axes (
    axis_id INTEGER PRIMARY KEY AUTOINCREMENT,
    axis_name TEXT UNIQUE NOT NULL,
    prompt_template TEXT NOT NULL,
    rules_template TEXT,
    execution_order INTEGER NOT NULL,
    dependencies TEXT,  -- JSON array of dependent axis names
    multiplicity TEXT,
    list_type TEXT CHECK(list_type IN ('closed', 'open')),
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_classification_axes_execution_order ON classification_axes(execution_order);

-- =====================================================
-- Table: search_history
-- Tracks semantic searches for analytics
-- =====================================================
CREATE TABLE IF NOT EXISTS search_history (
    search_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    top_k INTEGER,
    results TEXT,  -- JSON array of {chunk_id, email_id, score}
    search_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_search_history_timestamp ON search_history(search_timestamp);

-- =====================================================
-- Table: processing_log
-- Audit trail for all processing operations
-- =====================================================
CREATE TABLE IF NOT EXISTS processing_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT CHECK(operation_type IN ('classify', 'chunk', 'embed', 'search', 'validate')),
    email_id INTEGER,
    status TEXT CHECK(status IN ('success', 'failure', 'partial')),
    error_message TEXT,
    execution_time_ms INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (email_id) REFERENCES emails(email_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_processing_log_timestamp ON processing_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_processing_log_operation ON processing_log(operation_type);
