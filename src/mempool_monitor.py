import asyncio
import json
import time
from web3 import Web3
from typing import Dict, List, Optional, Callable
import aiohttp
import websockets
from config import Config
from src.utils.decoders import TransactionDecoder
from src.utils.price_feeds import PriceFeed

class MempoolMonitor:
    def __init__(self, on_transaction_callback: Callable = None):
        self.config = Config()
        self.decoder = TransactionDecoder()
        self.price_feed = PriceFeed()
        self.on_transaction_callback = on_transaction_callback
        
        self.w3 = Web3(Web3.HTTPProvider(self.config.ETHEREUM_RPC_URL))
        
        self.transaction_queue = asyncio.Queue()
        self.is_running = False
        
        self.stats = {
            'total_transactions': 0,
            'dex_transactions': 0,
            'high_value_transactions': 0,
            'start_time': time.time()
        }
    
    async def start_monitoring(self):
        """Start monitoring the mempool"""
        print("Starting mempool monitoring...")
        self.is_running = True
        
        tasks = [
            asyncio.create_task(self._monitor_flashbots()),
            asyncio.create_task(self._monitor_alchemy_pending()),
            asyncio.create_task(self._process_transaction_queue())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error in monitoring: {e}")
        finally:
            self.is_running = False
    
    async def stop_monitoring(self):
        """Stop monitoring"""
        print("Stopping mempool monitoring...")
        self.is_running = False
    
    async def _monitor_flashbots(self):
        """Monitor pending transactions via Flashbots Protect"""
        try:
            while self.is_running:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "jsonrpc": "2.0",
                        "method": "eth_subscribe",
                        "params": ["newPendingTransactions"],
                        "id": 1
                    }
                    
                    async with session.post(
                        self.config.FLASHBOTS_PROTECT_RPC,
                        json=payload,
                        headers={'Content-Type': 'application/json'}
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            print(f"Flashbots subscription response: {data}")
                        
                        await self._poll_pending_transactions(session)
                        
        except Exception as e:
            print(f"Error monitoring Flashbots: {e}")
            await asyncio.sleep(5)
    
    async def _monitor_alchemy_pending(self):
        """Monitor pending transactions via Alchemy WebSocket"""
        try:
            if not self.config.ALCHEMY_API_KEY:
                print("No Alchemy API key provided, skipping Alchemy monitoring")
                return
            
            ws_url = f"wss://eth-mainnet.g.alchemy.com/v2/{self.config.ALCHEMY_API_KEY}"
            
            while self.is_running:
                try:
                    async with websockets.connect(ws_url) as websocket:
                        subscribe_msg = {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "eth_subscribe",
                            "params": ["alchemy_pendingTransactions"]
                        }
                        
                        await websocket.send(json.dumps(subscribe_msg))
                        
                        while self.is_running:
                            try:
                                message = await asyncio.wait_for(websocket.recv(), timeout=30)
                                data = json.loads(message)
                                
                                if 'params' in data and 'result' in data['params']:
                                    tx_hash = data['params']['result']
                                    await self._fetch_and_process_transaction(tx_hash)
                                    
                            except asyncio.TimeoutError:
                                await websocket.ping()
                                
                except Exception as e:
                    print(f"WebSocket error: {e}")
                    await asyncio.sleep(5)
                    
        except Exception as e:
            print(f"Error monitoring Alchemy: {e}")
    
    async def _poll_pending_transactions(self, session: aiohttp.ClientSession):
        """Poll for pending transactions (fallback method)"""
        try:
            while self.is_running:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_getBlockByNumber",
                    "params": ["pending", True],
                    "id": 1
                }
                
                async with session.post(
                    self.config.ETHEREUM_RPC_URL,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        block = data.get('result')
                        
                        if block and block.get('transactions'):
                            for tx in block['transactions']:
                                if isinstance(tx, dict):
                                    await self.transaction_queue.put(tx)
                
                await asyncio.sleep(2)  # Poll every 2 seconds
                
        except Exception as e:
            print(f"Error polling transactions: {e}")
    
    async def _fetch_and_process_transaction(self, tx_hash: str):
        """Fetch transaction details and add to queue"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_getTransactionByHash",
                "params": [tx_hash],
                "id": 1
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.ETHEREUM_RPC_URL,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        tx = data.get('result')
                        
                        if tx:
                            await self.transaction_queue.put(tx)
                            
        except Exception as e:
            print(f"Error fetching transaction {tx_hash}: {e}")
    
    async def _process_transaction_queue(self):
        """Process transactions from the queue"""
        print("Starting transaction processor...")
        
        while self.is_running:
            try:
                tx = await asyncio.wait_for(self.transaction_queue.get(), timeout=1.0)
                await self._analyze_transaction(tx)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Error processing transaction: {e}")
    
    async def _analyze_transaction(self, tx: Dict):
        """Analyze a single transaction"""
        try:
            self.stats['total_transactions'] += 1
            
            if not self.decoder.is_dex_transaction(tx):
                return
            
            self.stats['dex_transactions'] += 1
            
            decoded_tx = self.decoder.decode_swap_transaction(tx)
            if not decoded_tx:
                return
            
            tx_value = self.price_feed.estimate_transaction_value(decoded_tx)
            if tx_value and tx_value > 1000:  # Only process transactions > $1000
                self.stats['high_value_transactions'] += 1
                
                params = decoded_tx.get('decoded_params', {})
                slippage = params.get('slippage', 0)
                
                if slippage > self.config.MIN_SLIPPAGE_THRESHOLD:
                    print(f"High slippage transaction detected: {tx['hash']}")
                    print(f"  Value: ${tx_value:.2f}")
                    print(f"  Slippage: {slippage:.2f}%")
                    print(f"  Router: {decoded_tx['router']}")
                    
                    if self.on_transaction_callback:
                        await self.on_transaction_callback(decoded_tx, tx_value, slippage)
            
            if self.stats['total_transactions'] % 100 == 0:
                self._print_stats()
                
        except Exception as e:
            print(f"Error analyzing transaction: {e}")
    
    def _print_stats(self):
        """Print monitoring statistics"""
        runtime = time.time() - self.stats['start_time']
        print(f"\n--- Mempool Monitor Stats ---")
        print(f"Runtime: {runtime:.1f}s")
        print(f"Total transactions: {self.stats['total_transactions']}")
        print(f"DEX transactions: {self.stats['dex_transactions']}")
        print(f"High-value transactions: {self.stats['high_value_transactions']}")
        print(f"Rate: {self.stats['total_transactions']/runtime:.1f} tx/s")
        print("----------------------------\n")
    
    def get_stats(self) -> Dict:
        """Get current monitoring statistics"""
        runtime = time.time() - self.stats['start_time']
        return {
            **self.stats,
            'runtime': runtime,
            'tx_per_second': self.stats['total_transactions'] / runtime if runtime > 0 else 0
        }

async def test_mempool_monitor():
    """Test the mempool monitor"""
    async def on_transaction(decoded_tx, value, slippage):
        print(f"Callback: Transaction {decoded_tx['tx_hash']} - ${value:.2f} - {slippage:.2f}%")
    
    monitor = MempoolMonitor(on_transaction_callback=on_transaction)
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        print("Stopping monitor...")
        await monitor.stop_monitoring()

if __name__ == "__main__":
    asyncio.run(test_mempool_monitor())
