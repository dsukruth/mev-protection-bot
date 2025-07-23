import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional
from config import Config

class Database:
    def __init__(self, db_path: str = Config.DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                wallet_addresses TEXT,
                alert_threshold REAL DEFAULT 50.0,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detected_attacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash TEXT NOT NULL,
                victim_address TEXT,
                token_pair TEXT,
                estimated_loss REAL,
                attack_type TEXT DEFAULT 'sandwich',
                block_number INTEGER,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                alerted BOOLEAN DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attack_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                total_attacks INTEGER DEFAULT 0,
                total_saved_amount REAL DEFAULT 0.0,
                top_targeted_tokens TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, telegram_id: int, username: str = None, wallet_addresses: List[str] = None) -> bool:
        """Add new user to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            wallet_json = json.dumps(wallet_addresses) if wallet_addresses else None
            
            cursor.execute('''
                INSERT OR REPLACE INTO users (telegram_id, username, wallet_addresses)
                VALUES (?, ?, ?)
            ''', (telegram_id, username, wallet_json))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding user: {e}")
            return False
    
    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Get user by telegram ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'telegram_id': row[1],
                'username': row[2],
                'wallet_addresses': json.loads(row[3]) if row[3] else [],
                'alert_threshold': row[4],
                'is_active': bool(row[5]),
                'created_at': row[6]
            }
        return None
    
    def update_user_threshold(self, telegram_id: int, threshold: float) -> bool:
        """Update user's alert threshold"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users SET alert_threshold = ? WHERE telegram_id = ?
            ''', (threshold, telegram_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating threshold: {e}")
            return False
    
    def add_detected_attack(self, tx_hash: str, victim_address: str, token_pair: str, 
                          estimated_loss: float, block_number: int = None) -> bool:
        """Add detected attack to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO detected_attacks 
                (tx_hash, victim_address, token_pair, estimated_loss, block_number)
                VALUES (?, ?, ?, ?, ?)
            ''', (tx_hash, victim_address, token_pair, estimated_loss, block_number))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding attack: {e}")
            return False
    
    def get_recent_attacks(self, limit: int = 50) -> List[Dict]:
        """Get recent detected attacks"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM detected_attacks 
            ORDER BY detected_at DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        attacks = []
        for row in rows:
            attacks.append({
                'id': row[0],
                'tx_hash': row[1],
                'victim_address': row[2],
                'token_pair': row[3],
                'estimated_loss': row[4],
                'attack_type': row[5],
                'block_number': row[6],
                'detected_at': row[7],
                'alerted': bool(row[8])
            })
        
        return attacks
    
    def get_daily_stats(self) -> Dict:
        """Get daily attack statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT COUNT(*), SUM(estimated_loss) 
            FROM detected_attacks 
            WHERE DATE(detected_at) = ?
        ''', (today,))
        
        result = cursor.fetchone()
        conn.close()
        
        return {
            'attacks_today': result[0] or 0,
            'total_saved_today': result[1] or 0.0,
            'date': today
        }
