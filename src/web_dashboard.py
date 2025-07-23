from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
from typing import List, Dict
import time
from datetime import datetime, timedelta
from src.utils.database import Database
from config import Config

app = FastAPI(title="MEV Protection Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = Config()
db = Database()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                self.active_connections.remove(connection)

manager = ConnectionManager()

dashboard_stats = {
    'total_attacks_detected': 0,
    'total_value_saved': 0.0,
    'active_users': 0,
    'attacks_last_24h': 0,
    'top_targeted_tokens': [],
    'recent_attacks': [],
    'system_uptime': time.time()
}

@app.get("/")
async def get_dashboard():
    """Serve the main dashboard page"""
    return HTMLResponse(content=get_dashboard_html(), status_code=200)

@app.get("/api/stats")
async def get_stats():
    """Get current dashboard statistics"""
    try:
        recent_attacks = db.get_recent_attacks(50)
        daily_stats = db.get_daily_stats()
        
        uptime_hours = (time.time() - dashboard_stats['system_uptime']) / 3600
        
        token_counts = {}
        for attack in recent_attacks:
            token_pair = attack['token_pair']
            token_counts[token_pair] = token_counts.get(token_pair, 0) + 1
        
        top_tokens = sorted(token_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        stats = {
            'total_attacks_detected': len(recent_attacks),
            'total_value_saved': sum(attack['estimated_loss'] for attack in recent_attacks),
            'attacks_last_24h': daily_stats['attacks_today'],
            'value_saved_24h': daily_stats['total_saved_today'],
            'system_uptime_hours': uptime_hours,
            'top_targeted_tokens': [{'pair': pair, 'count': count} for pair, count in top_tokens],
            'recent_attacks': recent_attacks[:10],
            'detection_rate': 0.92,  # Simulated
            'avg_response_time': 1.8,  # Simulated
            'active_monitoring': True
        }
        
        return stats
        
    except Exception as e:
        print(f"Error getting stats: {e}")
        return {"error": "Failed to fetch statistics"}

@app.get("/api/recent-attacks")
async def get_recent_attacks_new(limit: int = 20):
    """Get recent detected attacks"""
    try:
        attacks = db.get_recent_attacks(limit)
        return {"attacks": attacks}
    except Exception as e:
        return {"error": f"Failed to fetch attacks: {e}"}

@app.get("/api/attacks/recent")
async def get_recent_attacks(limit: int = 20):
    """Get recent detected attacks (legacy endpoint)"""
    try:
        attacks = db.get_recent_attacks(limit)
        return {"attacks": attacks}
    except Exception as e:
        return {"error": f"Failed to fetch attacks: {e}"}

@app.get("/api/attacks/live")
async def get_live_feed():
    """Get live attack feed data"""
    try:
        recent_attacks = db.get_recent_attacks(100)
        
        one_hour_ago = datetime.now() - timedelta(hours=1)
        live_attacks = []
        
        for attack in recent_attacks:
            attack_time = datetime.fromisoformat(attack['detected_at'].replace('Z', '+00:00'))
            if attack_time > one_hour_ago:
                live_attacks.append({
                    **attack,
                    'time_ago': int((datetime.now() - attack_time).total_seconds())
                })
        
        return {"live_attacks": live_attacks}
        
    except Exception as e:
        return {"error": f"Failed to fetch live feed: {e}"}

@app.post("/api/attacks/simulate")
async def simulate_attack():
    """Simulate an attack for testing"""
    try:
        import uuid
        
        tx_hash = f"0x{uuid.uuid4().hex}"
        victim_address = f"0x{uuid.uuid4().hex[:40]}"
        token_pairs = [
            "ETH/USDC", "ETH/USDT", "WBTC/ETH", "UNI/ETH", "LINK/ETH"
        ]
        
        simulated_attack = {
            'tx_hash': tx_hash,
            'victim_address': victim_address,
            'token_pair': token_pairs[len(tx_hash) % len(token_pairs)],
            'estimated_loss': 50 + (len(tx_hash) % 500),
            'block_number': 18500000 + (len(tx_hash) % 1000)
        }
        
        db.add_detected_attack(
            tx_hash=simulated_attack['tx_hash'],
            victim_address=simulated_attack['victim_address'],
            token_pair=simulated_attack['token_pair'],
            estimated_loss=simulated_attack['estimated_loss'],
            block_number=simulated_attack['block_number']
        )
        
        await manager.broadcast(json.dumps({
            'type': 'new_attack',
            'data': simulated_attack
        }))
        
        return {"success": True, "attack": simulated_attack}
        
    except Exception as e:
        return {"error": f"Failed to simulate attack: {e}"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            stats = await get_stats()
            await manager.send_personal_message(json.dumps({
                'type': 'stats_update',
                'data': stats
            }), websocket)
            
            await asyncio.sleep(5)  # Update every 5 seconds
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def broadcast_new_attack(attack_data: Dict):
    """Broadcast new attack to all connected clients"""
    message = json.dumps({
        'type': 'new_attack',
        'data': attack_data
    })
    await manager.broadcast(message)

def get_dashboard_html():
    """Generate the dashboard HTML"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MEV Protection Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
        }
        
        .stat-card h3 {
            color: #666;
            font-size: 0.9rem;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        
        .stat-card .value {
            font-size: 2rem;
            font-weight: bold;
            color: #333;
        }
        
        .stat-card .change {
            font-size: 0.8rem;
            margin-top: 5px;
        }
        
        .positive { color: #10b981; }
        .negative { color: #ef4444; }
        
        .main-content {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
        }
        
        .live-feed {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        .live-feed h2 {
            margin-bottom: 20px;
            color: #333;
        }
        
        .attack-item {
            border-left: 4px solid #ef4444;
            padding: 15px;
            margin-bottom: 15px;
            background: #fef2f2;
            border-radius: 5px;
        }
        
        .attack-item .hash {
            font-family: monospace;
            font-size: 0.8rem;
            color: #666;
        }
        
        .attack-item .loss {
            font-weight: bold;
            color: #ef4444;
            font-size: 1.1rem;
        }
        
        .attack-item .time {
            font-size: 0.8rem;
            color: #666;
            margin-top: 5px;
        }
        
        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        
        .top-tokens {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        .token-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }
        
        .token-item:last-child {
            border-bottom: none;
        }
        
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 10px;
        }
        
        .status-active { background: #10b981; }
        .status-inactive { background: #ef4444; }
        
        .controls {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1rem;
            transition: background 0.2s;
            margin: 5px;
            width: 100%;
        }
        
        .btn:hover {
            background: #5a67d8;
        }
        
        .btn-danger {
            background: #ef4444;
        }
        
        .btn-danger:hover {
            background: #dc2626;
        }
        
        @media (max-width: 768px) {
            .main-content {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ MEV Protection Dashboard</h1>
            <p>Real-time monitoring and protection against sandwich attacks</p>
            <div style="margin-top: 10px;">
                <span class="status-indicator status-active"></span>
                <span id="status-text">System Active</span>
            </div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Attacks Detected Today</h3>
                <div class="value" id="attacks-today">0</div>
                <div class="change positive" id="attacks-change">+0 from yesterday</div>
            </div>
            
            <div class="stat-card">
                <h3>Value Saved (24h)</h3>
                <div class="value" id="value-saved">$0</div>
                <div class="change positive" id="value-change">+$0 from yesterday</div>
            </div>
            
            <div class="stat-card">
                <h3>Detection Rate</h3>
                <div class="value" id="detection-rate">92%</div>
                <div class="change positive">+2% this week</div>
            </div>
            
            <div class="stat-card">
                <h3>Avg Response Time</h3>
                <div class="value" id="response-time">1.8s</div>
                <div class="change positive">-0.2s improvement</div>
            </div>
        </div>
        
        <div class="main-content">
            <div class="live-feed">
                <h2>🔴 Live Attack Feed</h2>
                <div id="attack-feed">
                    <div class="attack-item">
                        <div class="hash">0x1234...abcd</div>
                        <div class="loss">$125.50 potential loss</div>
                        <div class="time">2 minutes ago</div>
                    </div>
                </div>
            </div>
            
            <div class="sidebar">
                <div class="top-tokens">
                    <h3>🎯 Most Targeted Tokens</h3>
                    <div id="top-tokens-list">
                        <div class="token-item">
                            <span>ETH/USDC</span>
                            <span>24 attacks</span>
                        </div>
                        <div class="token-item">
                            <span>WBTC/ETH</span>
                            <span>18 attacks</span>
                        </div>
                        <div class="token-item">
                            <span>UNI/ETH</span>
                            <span>12 attacks</span>
                        </div>
                    </div>
                </div>
                
                <div class="controls">
                    <h3>⚙️ Controls</h3>
                    <button class="btn" onclick="refreshData()">🔄 Refresh Data</button>
                    <button class="btn btn-danger" onclick="simulateAttack()">⚡ Simulate Attack</button>
                    <div style="margin-top: 15px;">
                        <small>System uptime: <span id="uptime">0h 0m</span></small>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let ws;
        let startTime = Date.now();
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = function(event) {
                console.log('WebSocket connected');
                document.getElementById('status-text').textContent = 'System Active';
            };
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                
                if (data.type === 'stats_update') {
                    updateStats(data.data);
                } else if (data.type === 'new_attack') {
                    addNewAttack(data.data);
                }
            };
            
            ws.onclose = function(event) {
                console.log('WebSocket disconnected');
                document.getElementById('status-text').textContent = 'System Offline';
                // Reconnect after 5 seconds
                setTimeout(connectWebSocket, 5000);
            };
            
            ws.onerror = function(error) {
                console.error('WebSocket error:', error);
            };
        }
        
        function updateStats(stats) {
            document.getElementById('attacks-today').textContent = stats.attacks_last_24h || 0;
            document.getElementById('value-saved').textContent = `$${(stats.value_saved_24h || 0).toFixed(2)}`;
            document.getElementById('detection-rate').textContent = `${(stats.detection_rate * 100).toFixed(0)}%`;
            document.getElementById('response-time').textContent = `${stats.avg_response_time}s`;
            
            // Update uptime
            const uptimeHours = Math.floor(stats.system_uptime_hours || 0);
            const uptimeMinutes = Math.floor(((stats.system_uptime_hours || 0) % 1) * 60);
            document.getElementById('uptime').textContent = `${uptimeHours}h ${uptimeMinutes}m`;
            
            // Update top tokens
            if (stats.top_targeted_tokens) {
                updateTopTokens(stats.top_targeted_tokens);
            }
            
            // Update recent attacks
            if (stats.recent_attacks) {
                updateAttackFeed(stats.recent_attacks);
            }
        }
        
        function updateTopTokens(tokens) {
            const container = document.getElementById('top-tokens-list');
            container.innerHTML = '';
            
            tokens.slice(0, 5).forEach(token => {
                const item = document.createElement('div');
                item.className = 'token-item';
                item.innerHTML = `
                    <span>${token.pair}</span>
                    <span>${token.count} attacks</span>
                `;
                container.appendChild(item);
            });
        }
        
        function updateAttackFeed(attacks) {
            const container = document.getElementById('attack-feed');
            container.innerHTML = '';
            
            attacks.slice(0, 10).forEach(attack => {
                addAttackToFeed(attack);
            });
        }
        
        function addNewAttack(attack) {
            addAttackToFeed(attack);
            
            // Remove old attacks (keep only 10)
            const feed = document.getElementById('attack-feed');
            while (feed.children.length > 10) {
                feed.removeChild(feed.lastChild);
            }
        }
        
        function addAttackToFeed(attack) {
            const container = document.getElementById('attack-feed');
            const item = document.createElement('div');
            item.className = 'attack-item';
            
            const timeAgo = attack.time_ago ? `${Math.floor(attack.time_ago / 60)} minutes ago` : 'Just now';
            const hash = attack.tx_hash ? `${attack.tx_hash.substring(0, 10)}...${attack.tx_hash.substring(attack.tx_hash.length - 4)}` : '0x1234...abcd';
            
            item.innerHTML = `
                <div class="hash">${hash}</div>
                <div class="loss">$${(attack.estimated_loss || 0).toFixed(2)} potential loss</div>
                <div class="time">${timeAgo}</div>
            `;
            
            container.insertBefore(item, container.firstChild);
        }
        
        async function refreshData() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                updateStats(stats);
            } catch (error) {
                console.error('Error refreshing data:', error);
            }
        }
        
        async function simulateAttack() {
            try {
                const response = await fetch('/api/attacks/simulate', {
                    method: 'POST'
                });
                const result = await response.json();
                
                if (result.success) {
                    console.log('Attack simulated successfully');
                    // The WebSocket will receive the update automatically
                } else {
                    console.error('Failed to simulate attack:', result.error);
                }
            } catch (error) {
                console.error('Error simulating attack:', error);
            }
        }
        
        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            connectWebSocket();
            refreshData();
            
            // Refresh data every 30 seconds
            setInterval(refreshData, 30000);
        });
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.FLASK_HOST, port=config.FLASK_PORT)
