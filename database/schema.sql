-- database/schema.sql

-- Table to store detected tokens before and after filtering
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_mint TEXT NOT NULL UNIQUE,
    lp_address TEXT NOT NULL,
    base_mint TEXT NOT NULL,
    creator_address TEXT, -- Optional, attempt to identify
    detected_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'PENDING_FILTER', -- e.g., PENDING_FILTER, PASSED_FILTER, FAILED_FILTER, FILTER_ERROR, BUY_PENDING, BUY_FAILED
    filter_fail_reason TEXT, -- Reason if status is FAILED_FILTER or FILTER_ERROR
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Table to store active positions after successful buys
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_mint TEXT NOT NULL UNIQUE, -- Foreign key reference to detections(token_mint) can be added
    lp_address TEXT NOT NULL,
    buy_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    buy_amount_sol REAL NOT NULL,
    buy_amount_tokens REAL, -- Amount of tokens received
    buy_price REAL, -- Price in SOL per token at time of buy
    buy_tx_signature TEXT UNIQUE, -- Signature of the buy transaction
    buy_provider_identifier TEXT, -- e.g., Sniperoo trade ID if applicable
    status TEXT NOT NULL DEFAULT 'ACTIVE', -- e.g., ACTIVE, SELL_PENDING, SELL_FAILED
    last_price_check_timestamp DATETIME,
    highest_price_since_buy REAL,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
    -- FOREIGN KEY (token_mint) REFERENCES detections (token_mint) -- Optional constraint
);

-- Table to store completed/closed trades (moved from positions)
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_mint TEXT NOT NULL,
    lp_address TEXT NOT NULL,
    buy_timestamp DATETIME NOT NULL,
    buy_amount_sol REAL NOT NULL,
    buy_amount_tokens REAL,
    buy_price REAL,
    buy_tx_signature TEXT,
    buy_provider_identifier TEXT,
    sell_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    sell_amount_tokens REAL, -- Amount of tokens sold
    sell_amount_sol REAL, -- Amount of SOL received
    sell_price REAL, -- Price in SOL per token at time of sell
    sell_tx_signature TEXT UNIQUE, -- Signature of the sell transaction
    sell_provider_identifier TEXT,
    sell_reason TEXT NOT NULL, -- e.g., TP, SL, TIME, MANUAL
    pnl_sol REAL, -- Profit or Loss in SOL (sell_amount_sol - buy_amount_sol)
    pnl_percentage REAL -- Profit or Loss percentage
);

-- Indexes for faster querying
CREATE INDEX IF NOT EXISTS idx_detections_status ON detections (status);
CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections (detected_timestamp);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions (status);
CREATE INDEX IF NOT EXISTS idx_trades_token_mint ON trades (token_mint);
CREATE INDEX IF NOT EXISTS idx_trades_buy_timestamp ON trades (buy_timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_sell_timestamp ON trades (sell_timestamp);

-- Trigger to update 'last_updated' timestamp on detections table update
CREATE TRIGGER IF NOT EXISTS update_detections_last_updated
AFTER UPDATE ON detections
FOR EACH ROW
BEGIN
    UPDATE detections SET last_updated = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

-- Trigger to update 'last_updated' timestamp on positions table update
CREATE TRIGGER IF NOT EXISTS update_positions_last_updated
AFTER UPDATE ON positions
FOR EACH ROW
BEGIN
    UPDATE positions SET last_updated = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;