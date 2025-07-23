from web3 import Web3
from eth_abi import decode
from eth_utils import to_checksum_address
import json
from typing import Dict, Optional, Tuple, List

class TransactionDecoder:
    def __init__(self):
        self.uniswap_v2_abi = [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForTokens",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactETHForTokens",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForETH",
                "type": "function"
            }
        ]
        
        self.function_signatures = {
            '0x38ed1739': 'swapExactTokensForTokens',
            '0x7ff36ab5': 'swapExactETHForTokens', 
            '0x18cbafe5': 'swapExactTokensForETH',
            '0x8803dbee': 'swapTokensForExactTokens',
            '0x4a25d94a': 'swapTokensForExactETH',
            '0xfb3bdb41': 'swapETHForExactTokens'
        }
        
        self.router_addresses = {
            '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D': 'Uniswap V2',
            '0xE592427A0AEce92De3Edee1F18E0157C05861564': 'Uniswap V3',
            '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F': 'SushiSwap'
        }
    
    def is_dex_transaction(self, tx: Dict) -> bool:
        """Check if transaction is a DEX swap"""
        if not tx.get('to'):
            return False
            
        to_address = to_checksum_address(tx['to'])
        return to_address in self.router_addresses
    
    def decode_swap_transaction(self, tx: Dict) -> Optional[Dict]:
        """Decode DEX swap transaction"""
        try:
            if not self.is_dex_transaction(tx):
                return None
            
            input_data = tx.get('input', '0x')
            if len(input_data) < 10:
                return None
            
            function_sig = input_data[:10]
            function_name = self.function_signatures.get(function_sig)
            
            if not function_name:
                return None
            
            decoded_data = self._decode_function_data(function_sig, input_data[10:])
            if not decoded_data:
                return None
            
            router_name = self.router_addresses[to_checksum_address(tx['to'])]
            
            return {
                'tx_hash': tx.get('hash'),
                'from': tx.get('from'),
                'to': tx.get('to'),
                'router': router_name,
                'function': function_name,
                'gas_price': int(tx.get('gasPrice', '0x0'), 16) if isinstance(tx.get('gasPrice'), str) else int(tx.get('gasPrice', 0)),
                'gas_limit': int(tx.get('gas', '0x0'), 16) if isinstance(tx.get('gas'), str) else int(tx.get('gas', 0)),
                'value': int(tx.get('value', '0x0'), 16) if isinstance(tx.get('value'), str) else int(tx.get('value', 0)),
                'decoded_params': decoded_data
            }
            
        except Exception as e:
            print(f"Error decoding transaction: {e}")
            return None
    
    def _decode_function_data(self, function_sig: str, data: str) -> Optional[Dict]:
        """Decode function parameters based on signature"""
        try:
            data_bytes = bytes.fromhex(data)
            
            if function_sig == '0x38ed1739':  # swapExactTokensForTokens
                types = ['uint256', 'uint256', 'address[]', 'address', 'uint256']
                decoded = decode(types, data_bytes)
                return {
                    'amount_in': decoded[0],
                    'amount_out_min': decoded[1],
                    'path': decoded[2],
                    'to': decoded[3],
                    'deadline': decoded[4],
                    'slippage': self._calculate_slippage(decoded[0], decoded[1])
                }
            
            elif function_sig == '0x7ff36ab5':  # swapExactETHForTokens
                types = ['uint256', 'address[]', 'address', 'uint256']
                decoded = decode(types, data_bytes)
                return {
                    'amount_out_min': decoded[0],
                    'path': decoded[1],
                    'to': decoded[2],
                    'deadline': decoded[3]
                }
            
            elif function_sig == '0x18cbafe5':  # swapExactTokensForETH
                types = ['uint256', 'uint256', 'address[]', 'address', 'uint256']
                decoded = decode(types, data_bytes)
                return {
                    'amount_in': decoded[0],
                    'amount_out_min': decoded[1],
                    'path': decoded[2],
                    'to': decoded[3],
                    'deadline': decoded[4],
                    'slippage': self._calculate_slippage(decoded[0], decoded[1])
                }
            
            return None
            
        except Exception as e:
            print(f"Error decoding function data: {e}")
            return None
    
    def _calculate_slippage(self, amount_in: int, amount_out_min: int) -> float:
        """Calculate slippage percentage (simplified)"""
        if amount_in == 0:
            return 0.0
        
        slippage = ((amount_in - amount_out_min) / amount_in) * 100
        return max(0.0, slippage)
    
    def extract_token_pair(self, decoded_tx: Dict) -> Optional[Tuple[str, str]]:
        """Extract token pair from decoded transaction"""
        try:
            params = decoded_tx.get('decoded_params', {})
            path = params.get('path', [])
            
            if len(path) >= 2:
                return (path[0], path[-1])
            
            return None
            
        except Exception as e:
            print(f"Error extracting token pair: {e}")
            return None
    
    def get_transaction_priority(self, tx: Dict) -> int:
        """Calculate transaction priority score based on gas price"""
        try:
            gas_price_raw = tx.get('gasPrice', '0x0')
            gas_price = int(gas_price_raw, 16) if isinstance(gas_price_raw, str) else int(gas_price_raw)
            gas_price_gwei = gas_price / 1e9
            
            if gas_price_gwei > 100:
                return 10  # Very high priority
            elif gas_price_gwei > 50:
                return 8   # High priority
            elif gas_price_gwei > 20:
                return 6   # Medium priority
            elif gas_price_gwei > 10:
                return 4   # Low priority
            else:
                return 2   # Very low priority
                
        except Exception:
            return 1
