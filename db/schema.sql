-- vest SQLite Schema

-- 1. 交易明细表
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT CHECK(side IN ('LONG', 'SHORT')) DEFAULT 'LONG',
    status TEXT DEFAULT 'PLANNING',
    
    -- 投前记录
    plan_buy_logic TEXT,
    target_price REAL,
    stop_loss REAL,
    
    -- 执行数据
    entry_price REAL,
    quantity INTEGER,
    entry_at DATETIME,
    
    -- 结算数据
    exit_price REAL,
    exit_at DATETIME,
    net_pnl REAL,
    pnl_ratio REAL,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. 复盘日志表
CREATE TABLE IF NOT EXISTS journals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    content TEXT NOT NULL,
    tags TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(trade_id) REFERENCES trades(id)
);

-- 3. 交易统计视图
CREATE VIEW IF NOT EXISTS trade_stats AS
SELECT 
    symbol,
    COUNT(*) as total_trades,
    SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) as closed_trades,
    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open_positions,
    SUM(CASE WHEN status = 'CLOSED' THEN net_pnl ELSE 0 END) as total_pnl,
    ROUND(AVG(CASE WHEN status = 'CLOSED' THEN pnl_ratio ELSE NULL END), 2) as avg_pnl_ratio
FROM trades
GROUP BY symbol;