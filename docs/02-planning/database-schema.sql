-- ============================================================
-- CryptoAnalyzer — Database Schema
-- PostgreSQL with UUID primary keys
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. USERS
-- ============================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);

-- ============================================================
-- 2. WALLETS
-- ============================================================
CREATE TABLE wallets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange VARCHAR(20) NOT NULL CHECK (exchange IN ('binance', 'bybit')),
    api_key_encrypted TEXT NOT NULL,       -- AES-256 encrypted
    api_secret_encrypted TEXT NOT NULL,    -- AES-256 encrypted
    label VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_wallets_user_id ON wallets(user_id);

-- ============================================================
-- 3. WALLET BALANCES
-- ============================================================
CREATE TABLE wallet_balances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    asset VARCHAR(20) NOT NULL,            -- BTC, ETH, USDT, etc.
    free_balance DECIMAL(20, 8) NOT NULL DEFAULT 0,
    locked_balance DECIMAL(20, 8) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(wallet_id, asset)
);

CREATE INDEX idx_wallet_balances_wallet_id ON wallet_balances(wallet_id);

-- ============================================================
-- 4. BOT SETTINGS
-- ============================================================
CREATE TABLE bot_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_auto_trade_enabled BOOLEAN NOT NULL DEFAULT false,
    is_admin_approved BOOLEAN NOT NULL DEFAULT false,
    max_trades_per_day INTEGER NOT NULL DEFAULT 5,
    max_trade_amount DECIMAL(20, 8) NOT NULL DEFAULT 100,   -- بالـ USDT
    max_portfolio_percentage DECIMAL(5, 2) NOT NULL DEFAULT 10.00,
    max_daily_loss DECIMAL(20, 8) NOT NULL DEFAULT 50,       -- حد خسارة يومي
    allowed_symbols TEXT[] DEFAULT '{}',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 5. BOT ANALYSES
-- ============================================================
CREATE TABLE bot_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) DEFAULT '1h',
    news_source VARCHAR(100),
    news_title TEXT,
    news_url TEXT,
    is_momentum_real BOOLEAN,
    price_confirmed_news BOOLEAN,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('buy', 'sell', 'no_opportunity')),
    confidence_score DECIMAL(5, 2),         -- 0.00 to 100.00
    reasoning TEXT NOT NULL,
    technical_indicators JSONB,             -- RSI, MACD, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_bot_analyses_symbol ON bot_analyses(symbol);
CREATE INDEX idx_bot_analyses_decision ON bot_analyses(decision);
CREATE INDEX idx_bot_analyses_created_at ON bot_analyses(created_at DESC);

-- ============================================================
-- 6. TRADES
-- ============================================================
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    analysis_id UUID REFERENCES bot_analyses(id) ON DELETE SET NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('buy', 'sell')),
    order_type VARCHAR(10) NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL,
    fee DECIMAL(20, 8) DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'filled', 'partial', 'cancelled', 'failed')),
    executed_by VARCHAR(10) NOT NULL CHECK (executed_by IN ('bot', 'manual')),
    exchange_order_id VARCHAR(100),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    executed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_trades_user_id ON trades(user_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_created_at ON trades(created_at DESC);
CREATE INDEX idx_trades_status ON trades(status);

-- ============================================================
-- 7. NOTIFICATIONS
-- ============================================================
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL CHECK (type IN ('telegram', 'email', 'web')),
    category VARCHAR(30) DEFAULT 'general' CHECK (category IN ('opportunity', 'trade_executed', 'security', 'daily_summary', 'general')),
    title VARCHAR(255),
    message TEXT NOT NULL,
    is_sent BOOLEAN NOT NULL DEFAULT false,
    is_read BOOLEAN NOT NULL DEFAULT false,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_is_sent ON notifications(is_sent);

-- ============================================================
-- 8. SUPPORTED SYMBOLS
-- ============================================================
CREATE TABLE supported_symbols (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) UNIQUE NOT NULL,    -- BTCUSDT, ETHUSDT, etc.
    base_asset VARCHAR(10) NOT NULL,        -- BTC, ETH
    quote_asset VARCHAR(10) NOT NULL DEFAULT 'USDT',
    is_default BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    min_trade_amount DECIMAL(20, 8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 9. USER NOTIFICATION PREFERENCES
-- ============================================================
CREATE TABLE user_notification_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    telegram_enabled BOOLEAN NOT NULL DEFAULT true,
    telegram_chat_id VARCHAR(50),
    email_enabled BOOLEAN NOT NULL DEFAULT true,
    web_enabled BOOLEAN NOT NULL DEFAULT true,
    notify_opportunities BOOLEAN NOT NULL DEFAULT true,
    notify_trades BOOLEAN NOT NULL DEFAULT true,
    notify_daily_summary BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 10. REFRESH TOKENS
-- ============================================================
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

-- ============================================================
-- DEFAULT DATA
-- ============================================================
INSERT INTO supported_symbols (symbol, base_asset, quote_asset, is_default) VALUES
    ('BTCUSDT', 'BTC', 'USDT', true),
    ('ETHUSDT', 'ETH', 'USDT', true),
    ('BNBUSDT', 'BNB', 'USDT', false),
    ('SOLUSDT', 'SOL', 'USDT', false),
    ('XRPUSDT', 'XRP', 'USDT', false),
    ('ADAUSDT', 'ADA', 'USDT', false),
    ('DOGEUSDT', 'DOGE', 'USDT', false),
    ('AVAXUSDT', 'AVAX', 'USDT', false);
