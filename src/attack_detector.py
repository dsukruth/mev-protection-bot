import asyncio
import time
from typing import Dict, List, Optional, Tuple, Callable
from collections import defaultdict, deque
from dataclasses import dataclass
from src.utils.database import Database
from src.utils.price_feeds import PriceFeed
from config import Config
from src.ml_detector import MLAttackDetector

@dataclass
class PendingTransaction:
    tx_hash: str
    from_address: str
    to_address: str
    gas_price: int
    decoded_data: Dict
    timestamp: float
    token_pair: Tuple[str, str]
    estimated_value: float
    slippage: float

@dataclass
class SandwichAttack:
    victim_tx: PendingTransaction
    front_run_tx: Optional[PendingTransaction]
    back_run_tx: Optional[PendingTransaction]
    estimated_profit: float
    estimated_victim_loss: float
    confidence_score: float
    attack_type: str = "sandwich"
    chain: str = "ethereum"
    ml_score: float = 0.0
    risk_level: str = "UNKNOWN"

class AttackDetector:
    def __init__(self, alert_callback: Optional[Callable] = None):
        self.config = Config()
        self.db = Database()
        self.price_feed = PriceFeed()
        self.alert_callback = alert_callback
        self.ml_detector = MLAttackDetector()
        
        self.pending_transactions = deque(maxlen=1000)  # Keep last 1000 transactions
        self.token_pair_transactions = defaultdict(list)  # Group by token pair
        self.suspicious_addresses = set()
        self.known_mev_bots = set()
        
        self.detection_window = 30  # seconds
        self.min_profit_threshold = 100  # $100 minimum profit
        self.confidence_threshold = 0.7
        
        self.stats = {
            'total_analyzed': 0,
            'attacks_detected': 0,
            'false_positives': 0,
            'alerts_sent': 0
        }
        
        self._load_known_mev_bots()
    
    def _load_known_mev_bots(self):
        """Load known MEV bot addresses"""
        known_bots = [
            '0x000000000000084e91743124a982076c59f10084',  # MEV Bot
            '0x0000000000007f150bd6f54c40a34d7c3d5e9f56',  # Flashbots
            '0x00000000003b3cc22af3ae1eac0440bcee416b40',  # MEV Searcher
        ]
        
        self.known_mev_bots.update(known_bots)
        print(f"Loaded {len(self.known_mev_bots)} known MEV bot addresses")
    
    async def analyze_transaction(self, decoded_tx: Dict, estimated_value: float, slippage: float):
        """Analyze a transaction for potential sandwich attacks"""
        try:
            self.stats['total_analyzed'] += 1
            
            token_pair = self._extract_token_pair(decoded_tx)
            if not token_pair:
                return
            
            pending_tx = PendingTransaction(
                tx_hash=decoded_tx.get('tx_hash', ''),
                from_address=decoded_tx.get('from', ''),
                to_address=decoded_tx.get('to', ''),
                gas_price=decoded_tx.get('gas_price', 0),
                decoded_data=decoded_tx,
                timestamp=time.time(),
                token_pair=token_pair,
                estimated_value=estimated_value,
                slippage=slippage
            )
            
            self.pending_transactions.append(pending_tx)
            self.token_pair_transactions[token_pair].append(pending_tx)
            
            self._cleanup_old_transactions()
            
            attacks = await self._detect_sandwich_attacks(pending_tx)
            
            for attack in attacks:
                await self._process_detected_attack(attack)
                
        except Exception as e:
            print(f"Error analyzing transaction: {e}")
    
    def _extract_token_pair(self, decoded_tx: Dict) -> Optional[Tuple[str, str]]:
        """Extract token pair from decoded transaction"""
        try:
            params = decoded_tx.get('decoded_params', {})
            path = params.get('path', [])
            
            if len(path) >= 2:
                return (path[0].lower(), path[-1].lower())
            
            return None
        except Exception:
            return None
    
    def _cleanup_old_transactions(self):
        """Remove old transactions from tracking"""
        current_time = time.time()
        cutoff_time = current_time - self.detection_window
        
        for token_pair in list(self.token_pair_transactions.keys()):
            transactions = self.token_pair_transactions[token_pair]
            recent_txs = [tx for tx in transactions if tx.timestamp > cutoff_time]
            
            if recent_txs:
                self.token_pair_transactions[token_pair] = recent_txs
            else:
                del self.token_pair_transactions[token_pair]
    
    async def _detect_sandwich_attacks(self, target_tx: PendingTransaction) -> List[SandwichAttack]:
        """Detect potential sandwich attacks targeting the given transaction"""
        attacks = []
        
        try:
            pair_transactions = self.token_pair_transactions.get(target_tx.token_pair, [])
            
            if len(pair_transactions) < 2:
                return attacks
            
            for i, tx in enumerate(pair_transactions):
                if tx.tx_hash == target_tx.tx_hash:
                    continue
                
                if self._is_potential_front_run(tx, target_tx):
                    back_run = self._find_back_run_transaction(tx, target_tx, pair_transactions)
                    
                    if back_run:
                        attack = await self._analyze_sandwich_pattern(tx, target_tx, back_run)
                        if attack and attack.confidence_score > self.confidence_threshold:
                            attacks.append(attack)
            
            return attacks
            
        except Exception as e:
            print(f"Error detecting sandwich attacks: {e}")
            return []
    
    def _is_potential_front_run(self, potential_front: PendingTransaction, target: PendingTransaction) -> bool:
        """Check if a transaction could be a front-run"""
        try:
            time_diff = target.timestamp - potential_front.timestamp
            if time_diff < -5 or time_diff > 30:  # Within 30 seconds
                return False
            
            if potential_front.gas_price <= target.gas_price:
                return False
            
            if potential_front.from_address.lower() in self.known_mev_bots:
                return True
            
            front_params = potential_front.decoded_data.get('decoded_params', {})
            target_params = target.decoded_data.get('decoded_params', {})
            
            front_path = front_params.get('path', [])
            target_path = target_params.get('path', [])
            
            if len(front_path) >= 2 and len(target_path) >= 2:
                if (front_path[0].lower() == target_path[-1].lower() and 
                    front_path[-1].lower() == target_path[0].lower()):
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error checking front-run: {e}")
            return False
    
    def _find_back_run_transaction(self, front_run: PendingTransaction, target: PendingTransaction, 
                                 all_transactions: List[PendingTransaction]) -> Optional[PendingTransaction]:
        """Find potential back-run transaction"""
        try:
            for tx in all_transactions:
                if tx.tx_hash in [front_run.tx_hash, target.tx_hash]:
                    continue
                
                if tx.timestamp <= target.timestamp:
                    continue
                
                if tx.from_address.lower() != front_run.from_address.lower():
                    continue
                
                front_params = front_run.decoded_data.get('decoded_params', {})
                back_params = tx.decoded_data.get('decoded_params', {})
                
                front_path = front_params.get('path', [])
                back_path = back_params.get('path', [])
                
                if len(front_path) >= 2 and len(back_path) >= 2:
                    if (front_path[-1].lower() == back_path[0].lower() and 
                        front_path[0].lower() == back_path[-1].lower()):
                        return tx
            
            return None
            
        except Exception as e:
            print(f"Error finding back-run: {e}")
            return None
    
    async def _analyze_sandwich_pattern(self, front_run: PendingTransaction, victim: PendingTransaction, 
                                      back_run: PendingTransaction) -> Optional[SandwichAttack]:
        """Analyze a potential sandwich attack pattern"""
        try:
            profit = await self._estimate_sandwich_profit(front_run, victim, back_run)
            victim_loss = await self._estimate_victim_loss(victim, front_run, back_run)
            
            confidence = self._calculate_confidence_score(front_run, victim, back_run, profit)
            
            ml_analysis = self.ml_detector.analyze_transaction_ml(victim.decoded_data)
            
            if profit > self.min_profit_threshold and victim_loss > 50:
                return SandwichAttack(
                    victim_tx=victim,
                    front_run_tx=front_run,
                    back_run_tx=back_run,
                    estimated_profit=profit,
                    estimated_victim_loss=victim_loss,
                    confidence_score=confidence,
                    chain="ethereum",
                    ml_score=ml_analysis['ml_score'],
                    risk_level=ml_analysis['risk_level']
                )
            
            return None
            
        except Exception as e:
            print(f"Error analyzing sandwich pattern: {e}")
            return None
    
    async def _estimate_sandwich_profit(self, front_run: PendingTransaction, victim: PendingTransaction, 
                                      back_run: PendingTransaction) -> float:
        """Estimate profit from sandwich attack"""
        try:
            
            front_params = front_run.decoded_data.get('decoded_params', {})
            back_params = back_run.decoded_data.get('decoded_params', {})
            
            front_amount_in = front_params.get('amount_in', 0)
            back_amount_out = back_params.get('amount_out_min', 0)
            
            estimated_profit = victim.estimated_value * 0.02  # 2% estimate
            
            return max(0, estimated_profit)
            
        except Exception as e:
            print(f"Error estimating profit: {e}")
            return 0
    
    async def _estimate_victim_loss(self, victim: PendingTransaction, front_run: PendingTransaction, 
                                  back_run: PendingTransaction) -> float:
        """Estimate victim's loss from sandwich attack"""
        try:
            base_loss = victim.estimated_value * 0.01  # 1% base loss
            
            slippage_multiplier = max(1, victim.slippage / 2)
            
            estimated_loss = base_loss * slippage_multiplier
            
            return estimated_loss
            
        except Exception as e:
            print(f"Error estimating victim loss: {e}")
            return 0
    
    def _calculate_confidence_score(self, front_run: PendingTransaction, victim: PendingTransaction, 
                                  back_run: PendingTransaction, profit: float) -> float:
        """Calculate confidence score for attack detection"""
        try:
            score = 0.0
            
            if front_run.gas_price > victim.gas_price * 1.1:
                score += 0.3
            
            front_time_diff = abs(victim.timestamp - front_run.timestamp)
            back_time_diff = abs(back_run.timestamp - victim.timestamp)
            
            if front_time_diff < 10 and back_time_diff < 10:  # Within 10 seconds
                score += 0.2
            
            if front_run.from_address.lower() in self.known_mev_bots:
                score += 0.25
            
            if profit > self.min_profit_threshold * 2:
                score += 0.15
            
            if self._check_transaction_pattern(front_run, victim, back_run):
                score += 0.1
            
            return min(1.0, score)
            
        except Exception as e:
            print(f"Error calculating confidence: {e}")
            return 0.0
    
    def _check_transaction_pattern(self, front_run: PendingTransaction, victim: PendingTransaction, 
                                 back_run: PendingTransaction) -> bool:
        """Check if transactions follow sandwich pattern"""
        try:
            front_params = front_run.decoded_data.get('decoded_params', {})
            victim_params = victim.decoded_data.get('decoded_params', {})
            back_params = back_run.decoded_data.get('decoded_params', {})
            
            front_path = front_params.get('path', [])
            victim_path = victim_params.get('path', [])
            back_path = back_params.get('path', [])
            
            if len(front_path) < 2 or len(victim_path) < 2 or len(back_path) < 2:
                return False
            
            front_in, front_out = front_path[0].lower(), front_path[-1].lower()
            back_in, back_out = back_path[0].lower(), back_path[-1].lower()
            
            return front_in == back_out and front_out == back_in
            
        except Exception:
            return False
    
    async def _process_detected_attack(self, attack: SandwichAttack):
        """Process a detected sandwich attack"""
        try:
            self.stats['attacks_detected'] += 1
            
            print(f"\n🚨 SANDWICH ATTACK DETECTED!")
            print(f"Victim TX: {attack.victim_tx.tx_hash}")
            print(f"Estimated Loss: ${attack.estimated_victim_loss:.2f}")
            print(f"Attacker Profit: ${attack.estimated_profit:.2f}")
            print(f"Confidence: {attack.confidence_score:.2%}")
            print(f"Token Pair: {attack.victim_tx.token_pair}")
            
            token_pair_str = f"{attack.victim_tx.token_pair[0]}/{attack.victim_tx.token_pair[1]}"
            self.db.add_detected_attack(
                tx_hash=attack.victim_tx.tx_hash,
                victim_address=attack.victim_tx.from_address,
                token_pair=token_pair_str,
                estimated_loss=attack.estimated_victim_loss
            )
            
            if self.alert_callback and attack.estimated_victim_loss > self.config.MIN_LOSS_THRESHOLD:
                await self.alert_callback(attack)
                self.stats['alerts_sent'] += 1
            
        except Exception as e:
            print(f"Error processing attack: {e}")
    
    def add_suspicious_address(self, address: str):
        """Add address to suspicious list"""
        self.suspicious_addresses.add(address.lower())
    
    def is_suspicious_address(self, address: str) -> bool:
        """Check if address is suspicious"""
        return address.lower() in self.suspicious_addresses or address.lower() in self.known_mev_bots
    
    def get_stats(self) -> Dict:
        """Get detection statistics"""
        return {
            **self.stats,
            'detection_rate': self.stats['attacks_detected'] / max(1, self.stats['total_analyzed']),
            'alert_rate': self.stats['alerts_sent'] / max(1, self.stats['attacks_detected'])
        }
    
    async def simulate_attack_detection(self):
        """Simulate attack detection for testing"""
        print("Simulating sandwich attack detection...")
        
        import uuid
        
        front_run = PendingTransaction(
            tx_hash=f"0x{uuid.uuid4().hex}",
            from_address="0x000000000000084e91743124a982076c59f10084",  # Known MEV bot
            to_address="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2
            gas_price=50000000000,  # 50 Gwei
            decoded_data={
                'decoded_params': {
                    'path': ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86a33E6441c8C0E6C9b8C4C5C1B8C8C8C8C8C'],
                    'amount_in': 1000000000000000000,  # 1 ETH
                    'amount_out_min': 1500000000  # 1500 USDC
                }
            },
            timestamp=time.time(),
            token_pair=('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86a33E6441c8C0E6C9b8C4C5C1B8C8C8C8C8C'),
            estimated_value=2000,
            slippage=1.0
        )
        
        victim = PendingTransaction(
            tx_hash=f"0x{uuid.uuid4().hex}",
            from_address="0x1234567890123456789012345678901234567890",  # Regular user
            to_address="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2
            gas_price=30000000000,  # 30 Gwei
            decoded_data={
                'decoded_params': {
                    'path': ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86a33E6441c8C0E6C9b8C4C5C1B8C8C8C8C8C'],
                    'amount_in': 5000000000000000000,  # 5 ETH
                    'amount_out_min': 7000000000  # 7000 USDC
                }
            },
            timestamp=time.time() + 1,
            token_pair=('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86a33E6441c8C0E6C9b8C4C5C1B8C8C8C8C8C'),
            estimated_value=10000,
            slippage=2.5
        )
        
        back_run = PendingTransaction(
            tx_hash=f"0x{uuid.uuid4().hex}",
            from_address="0x000000000000084e91743124a982076c59f10084",  # Same MEV bot
            to_address="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",  # Uniswap V2
            gas_price=45000000000,  # 45 Gwei
            decoded_data={
                'decoded_params': {
                    'path': ['0xA0b86a33E6441c8C0E6C9b8C4C5C1B8C8C8C8C8C', '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'],
                    'amount_in': 1500000000,  # 1500 USDC
                    'amount_out_min': 900000000000000000  # 0.9 ETH
                }
            },
            timestamp=time.time() + 2,
            token_pair=('0xA0b86a33E6441c8C0E6C9b8C4C5C1B8C8C8C8C8C', '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'),
            estimated_value=1800,
            slippage=1.0
        )
        
        self.pending_transactions.extend([front_run, victim, back_run])
        self.token_pair_transactions[victim.token_pair].extend([front_run, victim, back_run])
        
        attacks = await self._detect_sandwich_attacks(victim)
        
        print(f"Detected {len(attacks)} potential attacks")
        for attack in attacks:
            await self._process_detected_attack(attack)

async def test_attack_detector():
    """Test the attack detector"""
    async def alert_callback(attack):
        print(f"ALERT: Attack detected with ${attack.estimated_victim_loss:.2f} loss")
    
    detector = AttackDetector(alert_callback=alert_callback)
    await detector.simulate_attack_detection()
    
    print("\nDetection Stats:")
    stats = detector.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    asyncio.run(test_attack_detector())
