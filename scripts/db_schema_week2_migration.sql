-- Week 2, Task 2.3: Database Schema Updates for Hybrid Pipeline
--
-- Changes:
-- 1. Add extraction_flags to receipts (track method, risk level, etc.)
-- 2. Add verified_by_human to receipt_lines (track manual reviews)
-- 3. Add verification_timestamp to receipt_lines
-- 4. Add hybrid_method column to track which method was used
-- 5. Create extraction_queue table for async LLaVA tasks

-- Table: receipts
-- Add extraction metadata columns
ALTER TABLE receipts ADD COLUMN IF NOT EXISTS extraction_flags TEXT DEFAULT NULL;
-- Example: "verified_llava_low_risk,llava_confidence_0.75"

ALTER TABLE receipts ADD COLUMN IF NOT EXISTS hybrid_method TEXT DEFAULT 'geometric';
-- Values: 'geometric', 'llava_fallback', 'manual_review', etc.

ALTER TABLE receipts ADD COLUMN IF NOT EXISTS extraction_risk_level TEXT DEFAULT 'low';
-- Values: 'low', 'medium', 'high'

ALTER TABLE receipts ADD COLUMN IF NOT EXISTS extraction_confidence REAL DEFAULT 0.0;
-- Confidence score from extraction method (0.0 - 1.0)

ALTER TABLE receipts ADD COLUMN IF NOT EXISTS extraction_latency_ms INTEGER DEFAULT NULL;
-- Latency of extraction in milliseconds (for monitoring)

-- Table: receipt_lines
-- Add human verification tracking
ALTER TABLE receipt_lines ADD COLUMN IF NOT EXISTS verified_by_human BOOLEAN DEFAULT FALSE;
-- True if manually reviewed and approved/corrected by human

ALTER TABLE receipt_lines ADD COLUMN IF NOT EXISTS verification_timestamp TIMESTAMP DEFAULT NULL;
-- When was this line verified

ALTER TABLE receipt_lines ADD COLUMN IF NOT EXISTS verified_by_user TEXT DEFAULT NULL;
-- Email/ID of user who verified

ALTER TABLE receipt_lines ADD COLUMN IF NOT EXISTS verification_notes TEXT DEFAULT NULL;
-- Comments from human review (e.g., "corrected typo: Lactea -> Latte")

ALTER TABLE receipt_lines ADD COLUMN IF NOT EXISTS is_hallucinated BOOLEAN DEFAULT FALSE;
-- True if validator flagged this as likely hallucination

-- New table: extraction_queue (for Celery async tasks)
CREATE TABLE IF NOT EXISTS extraction_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL,
    task_id TEXT UNIQUE NOT NULL,  -- Celery task UUID
    method TEXT NOT NULL,  -- 'llava_async'
    status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP DEFAULT NULL,
    completed_at TIMESTAMP DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    result_json TEXT DEFAULT NULL,  -- Extracted items as JSON

    FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE,
    INDEX idx_receipt_id (receipt_id),
    INDEX idx_task_id (task_id),
    INDEX idx_status (status)
);

-- New table: manual_review_queue (for high-risk extractions)
CREATE TABLE IF NOT EXISTS manual_review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL,
    reason TEXT NOT NULL,  -- 'llava_high_risk_hallucination', 'validation_error', etc.
    extraction_method TEXT,  -- Which method flagged it
    errors TEXT,  -- JSON array of validation errors
    priority INTEGER DEFAULT 0,  -- Higher = more urgent
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP DEFAULT NULL,
    completed_at TIMESTAMP DEFAULT NULL,
    reviewed_by TEXT DEFAULT NULL,
    review_notes TEXT DEFAULT NULL,
    action_taken TEXT,  -- 'approved', 'corrected', 'rejected'

    FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE,
    INDEX idx_created_at (created_at),
    INDEX idx_priority (priority),
    INDEX idx_receipt_id (receipt_id)
);

-- New table: extraction_metrics (for monitoring/alerting)
CREATE TABLE IF NOT EXISTS extraction_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    method TEXT NOT NULL,  -- 'geometric', 'llava_fallback', 'manual_review'
    count INTEGER DEFAULT 0,
    avg_accuracy REAL DEFAULT 0.0,
    avg_latency_ms INTEGER DEFAULT 0,
    hallucination_rate REAL DEFAULT 0.0,  -- Percentage

    UNIQUE(date, method),
    INDEX idx_date (date)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_receipts_hybrid_method
    ON receipts(hybrid_method);

CREATE INDEX IF NOT EXISTS idx_receipts_risk_level
    ON receipts(extraction_risk_level);

CREATE INDEX IF NOT EXISTS idx_receipt_lines_verified
    ON receipt_lines(verified_by_human);

CREATE INDEX IF NOT EXISTS idx_receipt_lines_hallucinated
    ON receipt_lines(is_hallucinated);

-- View: extraction_summary (for dashboards)
CREATE VIEW IF NOT EXISTS v_extraction_summary AS
SELECT
    r.date,
    r.hybrid_method,
    r.extraction_risk_level,
    COUNT(*) as count,
    AVG(r.extraction_confidence) as avg_confidence,
    AVG(r.extraction_latency_ms) as avg_latency_ms,
    ROUND(100.0 * SUM(CASE WHEN rl.is_hallucinated THEN 1 ELSE 0 END) /
          NULLIF(COUNT(DISTINCT r.id), 0), 2) as hallucination_rate
FROM receipts r
LEFT JOIN receipt_lines rl ON r.id = rl.receipt_id
GROUP BY r.date, r.hybrid_method, r.extraction_risk_level
ORDER BY r.date DESC, r.hybrid_method;

-- View: manual_review_status (for queue monitoring)
CREATE VIEW IF NOT EXISTS v_manual_review_status AS
SELECT
    'pending' as status,
    COUNT(*) as count,
    MIN(created_at) as oldest,
    MAX(priority) as max_priority
FROM manual_review_queue
WHERE completed_at IS NULL
UNION ALL
SELECT
    'completed' as status,
    COUNT(*) as count,
    NULL as oldest,
    NULL as max_priority
FROM manual_review_queue
WHERE completed_at IS NOT NULL AND DATE(completed_at) = DATE('now');

-- Permissions (if using user-based access control)
-- GRANT SELECT, UPDATE ON receipts TO extraction_service;
-- GRANT INSERT ON receipt_lines TO extraction_service;
-- GRANT ALL ON extraction_queue TO celery_worker;
-- GRANT SELECT ON manual_review_queue TO review_team;
