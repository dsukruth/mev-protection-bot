import asyncio
import aiohttp
import json
from typing import Dict, List, Optional, Callable
from web3 import Web3
import logging
from datetime import datetime
from dataclasses import dataclass

@dataclass
class ChainConfig:
    name: str
    rpc_url: str
    chain_id: int
    native_token: str
    dex_routers: List[str]
    block_time: float
    gas_token: str

class MultiChainMonitor:
    def __init__(self, on_transaction_callback: Optional[Callable] = None):
        self.chains = {
            'ethereum': ChainConfig(
                name='Ethereum',
                rpc_url='https://rpc.flashbots.net',
                chain_id=1,
                native_token='ETH',
                dex_routers=[
                    '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',  # Uniswap V2
                    '0xE592427A0AEce92De3Edee1F18E0157C05861564',  # Uniswap V3
                    '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F'   # SushiSwap
                ],
                block_time=12.0,
                gas_token='ETH'
            ),
            'polygon': ChainConfig(
                name='Polygon',
                rpc_url='https://polygon-rpc.com',
                chain_id=137,
                native_token='MATIC',
                dex_routers=[
                    '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff',  # QuickSwap
                    '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506',  # SushiSwap Polygon
                    '0xE592427A0AEce92De3Edee1F18E0157C05861564'   # Uniswap V3 Polygon
                ],
                block_time=2.0,
                gas_token='MATIC'
            ),
            'bsc': ChainConfig(
                name='BSC',
                rpc_url='https://bsc-dataseed1.binance.org',
                chain_id=56,
                native_token='BNB',
                dex_routers=[
                    '0x10ED43C718714eb63d5aA57B78B54704E256024E',  # PancakeSwap V2
                    '0x13f4EA83D0bd40E75C8222255bc855a974568Dd4',  # PancakeSwap V3
                    '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506'   # SushiSwap BSC
                ],
                block_time=3.0,
                gas_token='BNB'
            )
        }
        
        self.web3_instances = {}
        self.monitoring_tasks = {}
        self.is_monitoring = {}
        self.on_transaction_callback = on_transaction_callback
        self.setup_logging()
        
        for chain_name in self.chains:
            self.is_monitoring[chain_name] = False
    
    def setup_logging(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    async def initialize_chain_connections(self):
        """Initialize Web3 connections for all chains"""
        try:
            for chain_name, config in self.chains.items():
                try:
                    if chain_name == 'ethereum':
                        rpc_url = config.rpc_url
                    else:
                        rpc_url = config.rpc_url
                    
                    web3 = Web3(Web3.HTTPProvider(rpc_url))
                    
                    if await self.test_connection(web3, chain_name):
                        self.web3_instances[chain_name] = web3
                        self.logger.info(f"✅ {config.name} connection established")
                    else:
                        self.logger.warning(f"❌ Failed to connect to {config.name}")
                        
                except Exception as e:
                    self.logger.error(f"Error connecting to {chain_name}: {e}")
            
            return len(self.web3_instances) > 0
            
        except Exception as e:
            self.logger.error(f"Error initializing chain connections: {e}")
            return False
    
    async def test_connection(self, web3: Web3, chain_name: str) -> bool:
        """Test if Web3 connection is working"""
        try:
            loop = asyncio.get_event_loop()
            latest_block = await loop.run_in_executor(None, web3.eth.get_block, 'latest')
            
            expected_chain_id = self.chains[chain_name].chain_id
            actual_chain_id = await loop.run_in_executor(None, web3.eth.chain_id)
            
            if actual_chain_id != expected_chain_id:
                self.logger.warning(f"Chain ID mismatch for {chain_name}: expected {expected_chain_id}, got {actual_chain_id}")
                return False
            
            return latest_block is not None
            
        except Exception as e:
            self.logger.error(f"Connection test failed for {chain_name}: {e}")
            return False
    
    async def start_monitoring_all_chains(self):
        """Start monitoring all configured chains"""
        try:
            await self.initialize_chain_connections()
            
            for chain_name in self.web3_instances:
                if not self.is_monitoring[chain_name]:
                    task = asyncio.create_task(self.monitor_chain(chain_name))
                    self.monitoring_tasks[chain_name] = task
                    self.is_monitoring[chain_name] = True
                    self.logger.info(f"🔍 Started monitoring {self.chains[chain_name].name}")
            
            self.logger.info(f"✅ Multi-chain monitoring active on {len(self.monitoring_tasks)} chains")
            
        except Exception as e:
            self.logger.error(f"Error starting multi-chain monitoring: {e}")
    
    async def monitor_chain(self, chain_name: str):
        """Monitor a specific blockchain for MEV attacks"""
        try:
            web3 = self.web3_instances[chain_name]
            config = self.chains[chain_name]
            
            self.logger.info(f"🔍 Monitoring {config.name} for MEV attacks...")
            
            last_block = await asyncio.get_event_loop().run_in_executor(
                None, web3.eth.get_block, 'latest'
            )
            last_block_number = last_block['number']
            
            while self.is_monitoring[chain_name]:
                try:
                    current_block = await asyncio.get_event_loop().run_in_executor(
                        None, web3.eth.get_block, 'latest'
                    )
                    current_block_number = current_block['number']
                    
                    if current_block_number > last_block_number:
                        for block_num in range(last_block_number + 1, current_block_number + 1):
                            await self.process_block(chain_name, block_num)
                        
                        last_block_number = current_block_number
                    
                    await asyncio.sleep(config.block_time)
                    
                except Exception as e:
                    self.logger.error(f"Error monitoring {chain_name}: {e}")
                    await asyncio.sleep(config.block_time * 2)
                    
        except Exception as e:
            self.logger.error(f"Fatal error monitoring {chain_name}: {e}")
            self.is_monitoring[chain_name] = False
    
    async def process_block(self, chain_name: str, block_number: int):
        """Process a block for potential MEV attacks"""
        try:
            web3 = self.web3_instances[chain_name]
            config = self.chains[chain_name]
            
            block = await asyncio.get_event_loop().run_in_executor(
                None, web3.eth.get_block, block_number, True
            )
            
            dex_transactions = []
            
            for tx in block['transactions']:
                if self.is_dex_transaction(tx, config):
                    decoded_tx = await self.decode_transaction(tx, chain_name)
                    if decoded_tx:
                        dex_transactions.append(decoded_tx)
            
            if len(dex_transactions) > 1:
                await self.analyze_block_for_attacks(dex_transactions, chain_name, block_number)
                
        except Exception as e:
            self.logger.error(f"Error processing block {block_number} on {chain_name}: {e}")
    
    def is_dex_transaction(self, tx: Dict, config: ChainConfig) -> bool:
        """Check if transaction is a DEX transaction"""
        try:
            to_address = tx.get('to', '').lower()
            return to_address in [router.lower() for router in config.dex_routers]
            
        except Exception:
            return False
    
    async def decode_transaction(self, tx: Dict, chain_name: str) -> Optional[Dict]:
        """Decode transaction data for the specific chain"""
        try:
            config = self.chains[chain_name]
            
            decoded = {
                'hash': tx['hash'].hex(),
                'from': tx['from'],
                'to': tx['to'],
                'value': int(tx['value']),
                'gas': int(tx['gas']),
                'gasPrice': int(tx['gasPrice']),
                'nonce': int(tx['nonce']),
                'input': tx['input'].hex(),
                'chain': chain_name,
                'chain_id': config.chain_id,
                'native_token': config.native_token,
                'block_number': tx.get('blockNumber', 0),
                'transaction_index': tx.get('transactionIndex', 0),
                'timestamp': datetime.now().isoformat()
            }
            
            decoded['estimated_value'] = await self.estimate_transaction_value(decoded, chain_name)
            decoded['slippage'] = await self.estimate_slippage(decoded, chain_name)
            
            return decoded
            
        except Exception as e:
            self.logger.error(f"Error decoding transaction on {chain_name}: {e}")
            return None
    
    async def estimate_transaction_value(self, tx: Dict, chain_name: str) -> float:
        """Estimate USD value of transaction"""
        try:
            config = self.chains[chain_name]
            
            native_value = int(tx['value']) / 1e18
            
            price_mapping = {
                'ethereum': 2000,  # ETH price
                'polygon': 0.8,    # MATIC price
                'bsc': 300         # BNB price
            }
            
            native_price = price_mapping.get(chain_name, 1.0)
            usd_value = native_value * native_price
            
            if usd_value < 100:
                usd_value = await self.estimate_token_swap_value(tx, chain_name)
            
            return usd_value
            
        except Exception as e:
            self.logger.error(f"Error estimating transaction value: {e}")
            return 0.0
    
    async def estimate_token_swap_value(self, tx: Dict, chain_name: str) -> float:
        """Estimate value of token swap"""
        try:
            input_data = tx.get('input', '')
            
            if len(input_data) < 10:
                return 0.0
            
            method_id = input_data[:10]
            
            swap_methods = [
                '0x7ff36ab5',  # swapExactETHForTokens
                '0x18cbafe5',  # swapExactTokensForETH
                '0x38ed1739',  # swapExactTokensForTokens
                '0x8803dbee',  # swapTokensForExactTokens
            ]
            
            if method_id in swap_methods:
                return max(1000.0, int(tx['value']) / 1e18 * 2000)
            
            return 0.0
            
        except Exception:
            return 0.0
    
    async def estimate_slippage(self, tx: Dict, chain_name: str) -> float:
        """Estimate transaction slippage"""
        try:
            gas_price = int(tx['gasPrice'])
            
            config = self.chains[chain_name]
            
            if chain_name == 'ethereum':
                base_gas = 20e9
            elif chain_name == 'polygon':
                base_gas = 30e9
            else:  # BSC
                base_gas = 5e9
            
            if gas_price > base_gas * 2:
                return min(5.0, (gas_price / base_gas - 1) * 2)
            
            return 0.5
            
        except Exception:
            return 0.5
    
    async def analyze_block_for_attacks(self, transactions: List[Dict], chain_name: str, block_number: int):
        """Analyze block transactions for sandwich attacks"""
        try:
            config = self.chains[chain_name]
            
            for i, tx in enumerate(transactions):
                if tx['estimated_value'] > 1000:  # Focus on high-value transactions
                    
                    potential_sandwich = await self.detect_sandwich_pattern(
                        transactions, i, chain_name
                    )
                    
                    if potential_sandwich:
                        attack_data = {
                            'victim_tx': tx,
                            'chain': chain_name,
                            'block_number': block_number,
                            'attack_type': 'sandwich',
                            'confidence': potential_sandwich['confidence'],
                            'estimated_loss': potential_sandwich['estimated_loss']
                        }
                        
                        if self.on_transaction_callback:
                            await self.on_transaction_callback(
                                tx, tx['estimated_value'], tx['slippage']
                            )
                        
                        self.logger.warning(
                            f"🚨 Potential sandwich attack detected on {config.name} "
                            f"(Block: {block_number}, Loss: ${potential_sandwich['estimated_loss']:.2f})"
                        )
                        
        except Exception as e:
            self.logger.error(f"Error analyzing block for attacks: {e}")
    
    async def detect_sandwich_pattern(self, transactions: List[Dict], victim_index: int, chain_name: str) -> Optional[Dict]:
        """Detect sandwich attack pattern in block transactions"""
        try:
            victim_tx = transactions[victim_index]
            
            front_run_candidates = []
            back_run_candidates = []
            
            for i, tx in enumerate(transactions):
                if i < victim_index and tx['gasPrice'] > victim_tx['gasPrice']:
                    front_run_candidates.append(tx)
                elif i > victim_index and tx['from'] in [candidate['from'] for candidate in front_run_candidates]:
                    back_run_candidates.append(tx)
            
            if front_run_candidates and back_run_candidates:
                estimated_loss = victim_tx['estimated_value'] * 0.02  # 2% typical sandwich loss
                
                confidence = min(0.9, len(front_run_candidates) * 0.3 + len(back_run_candidates) * 0.3)
                
                return {
                    'confidence': confidence,
                    'estimated_loss': estimated_loss,
                    'front_runs': len(front_run_candidates),
                    'back_runs': len(back_run_candidates)
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error detecting sandwich pattern: {e}")
            return None
    
    async def stop_monitoring_all_chains(self):
        """Stop monitoring all chains"""
        try:
            for chain_name in self.chains:
                self.is_monitoring[chain_name] = False
            
            for chain_name, task in self.monitoring_tasks.items():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            self.monitoring_tasks.clear()
            self.logger.info("🛑 Multi-chain monitoring stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping multi-chain monitoring: {e}")
    
    def get_chain_stats(self) -> Dict:
        """Get monitoring statistics for all chains"""
        try:
            stats = {
                'total_chains': len(self.chains),
                'active_chains': len([name for name, active in self.is_monitoring.items() if active]),
                'connected_chains': len(self.web3_instances),
                'chains': {}
            }
            
            for chain_name, config in self.chains.items():
                stats['chains'][chain_name] = {
                    'name': config.name,
                    'chain_id': config.chain_id,
                    'native_token': config.native_token,
                    'is_monitoring': self.is_monitoring[chain_name],
                    'is_connected': chain_name in self.web3_instances,
                    'dex_routers_count': len(config.dex_routers)
                }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting chain stats: {e}")
            return {'error': str(e)}
    
    async def simulate_multichain_attack(self):
        """Simulate a cross-chain MEV attack for testing"""
        try:
            chains = ['ethereum', 'polygon', 'bsc']
            
            for chain in chains:
                if chain in self.web3_instances:
                    config = self.chains[chain]
                    
                    simulated_tx = {
                        'hash': f'0x{"0" * 63}1',
                        'from': '0x' + '1' * 40,
                        'to': config.dex_routers[0],
                        'value': 5000 * 10**18,  # 5000 native tokens
                        'gas': 200000,
                        'gasPrice': 50 * 10**9,
                        'nonce': 1,
                        'input': '0x7ff36ab5',
                        'chain': chain,
                        'chain_id': config.chain_id,
                        'native_token': config.native_token,
                        'block_number': 12345,
                        'transaction_index': 1,
                        'timestamp': datetime.now().isoformat(),
                        'estimated_value': 10000.0,
                        'slippage': 2.5
                    }
                    
                    if self.on_transaction_callback:
                        await self.on_transaction_callback(
                            simulated_tx, simulated_tx['estimated_value'], simulated_tx['slippage']
                        )
                    
                    self.logger.info(f"🎭 Simulated attack on {config.name}")
                    await asyncio.sleep(1)
            
        except Exception as e:
            self.logger.error(f"Error simulating multichain attack: {e}")
