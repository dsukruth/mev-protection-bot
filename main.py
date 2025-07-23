import asyncio
import signal
import sys
from typing import Optional
from src.mempool_monitor import MempoolMonitor
from src.attack_detector import AttackDetector
from src.telegram_bot import MEVProtectionBot
from src.web_dashboard import app as dashboard_app
from config import Config
import uvicorn
import threading
import time

class MEVProtectionSystem:
    def __init__(self, demo_mode=False):
        self.config = Config()
        self.is_running = False
        self.demo_mode = demo_mode
        
        self.attack_detector = AttackDetector(alert_callback=self.on_attack_detected)
        
        if not demo_mode:
            self.mempool_monitor = MempoolMonitor(on_transaction_callback=self.on_transaction)
            self.telegram_bot = MEVProtectionBot(attack_detector=self.attack_detector)
        else:
            self.mempool_monitor = None
            self.telegram_bot = None
        
        self.dashboard_server = None
        self.dashboard_thread = None
        
        mode_text = "DEMO MODE" if demo_mode else ""
        print(f"MEV Protection System initialized {mode_text}")
    
    async def on_transaction(self, decoded_tx: dict, estimated_value: float, slippage: float):
        """Callback for new transactions from mempool monitor"""
        try:
            await self.attack_detector.analyze_transaction(decoded_tx, estimated_value, slippage)
        except Exception as e:
            print(f"Error processing transaction: {e}")
    
    async def on_attack_detected(self, attack):
        """Callback for detected attacks"""
        try:
            print(f"🚨 Attack detected! Sending alerts...")
            
            if not self.demo_mode and self.telegram_bot:
                await self.telegram_bot.send_attack_alert(attack)
            else:
                print(f"📱 Demo mode: Would send Telegram alert for attack {attack.tx_hash}")
            
        except Exception as e:
            print(f"Error handling attack alert: {e}")
    
    def start_dashboard_server(self):
        """Start the web dashboard server in a separate thread"""
        def run_dashboard():
            uvicorn.run(
                dashboard_app, 
                host=self.config.FLASK_HOST, 
                port=self.config.FLASK_PORT,
                log_level="info"
            )
        
        self.dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
        self.dashboard_thread.start()
        print(f"Dashboard server started on http://{self.config.FLASK_HOST}:{self.config.FLASK_PORT}")
    
    async def start(self):
        """Start the MEV protection system"""
        mode_text = "DEMO MODE" if self.demo_mode else ""
        print(f"🛡️ Starting MEV Protection System {mode_text}...")
        self.is_running = True
        
        try:
            self.start_dashboard_server()
            await asyncio.sleep(2)
            
            if self.demo_mode:
                tasks = [
                    asyncio.create_task(self.demo_attack_simulation()),
                    asyncio.create_task(self.status_reporter())
                ]
                
                print("✅ Demo system operational!")
                print(f"📊 Dashboard: http://localhost:{self.config.FLASK_PORT}")
                print(f"🤖 Telegram bot: Simulated")
                print(f"🔍 Mempool monitoring: Simulated")
                print(f"🛡️ Attack detection: Active")
                
            else:
                await self.telegram_bot.initialize()
                
                tasks = [
                    asyncio.create_task(self.mempool_monitor.start_monitoring()),
                    asyncio.create_task(self.telegram_bot.start_bot()),
                    asyncio.create_task(self.status_reporter())
                ]
                
                print("✅ All systems operational!")
                print(f"📊 Dashboard: http://localhost:{self.config.FLASK_PORT}")
                print(f"🤖 Telegram bot: Active")
                print(f"🔍 Mempool monitoring: Active")
                print(f"🛡️ Attack detection: Active")
            
            await asyncio.gather(*tasks)
            
        except Exception as e:
            print(f"Error starting system: {e}")
            await self.stop()
    
    async def stop(self):
        """Stop the MEV protection system"""
        print("🛑 Stopping MEV Protection System...")
        self.is_running = False
        
        try:
            if not self.demo_mode:
                if self.mempool_monitor:
                    await self.mempool_monitor.stop_monitoring()
                
                if self.telegram_bot:
                    await self.telegram_bot.stop_bot()
            
            print("✅ System stopped successfully")
            
        except Exception as e:
            print(f"Error stopping system: {e}")
    
    async def status_reporter(self):
        """Periodically report system status"""
        while self.is_running:
            try:
                detector_stats = self.attack_detector.get_stats()
                
                print(f"\n📊 System Status Report:")
                if not self.demo_mode and self.mempool_monitor:
                    monitor_stats = self.mempool_monitor.get_stats()
                    print(f"  Mempool: {monitor_stats['total_transactions']} txs processed")
                    print(f"  DEX txs: {monitor_stats['dex_transactions']}")
                else:
                    print(f"  Mempool: Demo mode - simulated")
                    print(f"  DEX txs: Demo mode - simulated")
                
                print(f"  Attacks detected: {detector_stats['attacks_detected']}")
                print(f"  Alerts sent: {detector_stats['alerts_sent']}")
                print(f"  Detection rate: {detector_stats['detection_rate']:.2%}")
                
                await asyncio.sleep(60)  # Report every minute in demo mode
                
            except Exception as e:
                print(f"Error in status reporter: {e}")
                await asyncio.sleep(60)
    
    async def demo_attack_simulation(self):
        """Simulate attack detection for demo purposes"""
        await asyncio.sleep(5)  # Wait before starting simulation
        
        while self.is_running:
            try:
                print("🔍 Simulating mempool monitoring...")
                await self.attack_detector.simulate_attack_detection()
                
                await asyncio.sleep(30)  # Simulate attack every 30 seconds
                
            except Exception as e:
                print(f"Error in demo simulation: {e}")
                await asyncio.sleep(10)
    
    async def test_system(self):
        """Test the system with simulated data"""
        print("🧪 Testing MEV Protection System...")
        
        try:
            print("Testing attack detector...")
            await self.attack_detector.simulate_attack_detection()
            
            print("✅ Attack detector test completed")
            
            detector_stats = self.attack_detector.get_stats()
            print(f"\nTest Results:")
            print(f"  Attacks detected: {detector_stats['attacks_detected']}")
            print(f"  Alerts sent: {detector_stats['alerts_sent']}")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")

async def main():
    """Main entry point"""
    demo_mode = len(sys.argv) > 1 and sys.argv[1] == "demo"
    test_mode = len(sys.argv) > 1 and sys.argv[1] == "test"
    
    system = MEVProtectionSystem(demo_mode=demo_mode)
    
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        asyncio.create_task(system.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if test_mode:
        await system.test_system()
    else:
        await system.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
