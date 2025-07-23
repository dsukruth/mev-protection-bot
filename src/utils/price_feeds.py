import requests
import time
from typing import Dict, Optional
from config import Config

class PriceFeed:
    def __init__(self):
        self.coingecko_api_key = Config.COINGECKO_API_KEY
        self.price_cache = {}
        self.cache_duration = 60  # Cache prices for 60 seconds
        
        self.token_mapping = {
            '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2': 'ethereum',  # WETH
            '0xA0b86a33E6441c8C0E6C9b8C4C5C1B8C8C8C8C8C': 'usd-coin',   # USDC
            '0x6B175474E89094C44Da98b954EedeAC495271d0F': 'dai',        # DAI
            '0xdAC17F958D2ee523a2206206994597C13D831ec7': 'tether',     # USDT
            '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599': 'wrapped-bitcoin', # WBTC
            '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984': 'uniswap',    # UNI
            '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9': 'aave',       # AAVE
            '0x514910771AF9Ca656af840dff83E8264EcF986CA': 'chainlink',  # LINK
        }
    
    def get_token_price(self, token_address: str) -> Optional[float]:
        """Get current USD price for a token"""
        try:
            cache_key = token_address.lower()
            current_time = time.time()
            
            if cache_key in self.price_cache:
                cached_data = self.price_cache[cache_key]
                if current_time - cached_data['timestamp'] < self.cache_duration:
                    return cached_data['price']
            
            coingecko_id = self.token_mapping.get(token_address.lower())
            if not coingecko_id:
                price = self._get_price_by_contract(token_address)
            else:
                price = self._get_price_by_id(coingecko_id)
            
            if price:
                self.price_cache[cache_key] = {
                    'price': price,
                    'timestamp': current_time
                }
            
            return price
            
        except Exception as e:
            print(f"Error getting token price for {token_address}: {e}")
            return None
    
    def _get_price_by_id(self, coingecko_id: str) -> Optional[float]:
        """Get price using CoinGecko ID"""
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': coingecko_id,
                'vs_currencies': 'usd'
            }
            
            if self.coingecko_api_key:
                params['x_cg_demo_api_key'] = self.coingecko_api_key
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return data.get(coingecko_id, {}).get('usd')
            
        except Exception as e:
            print(f"Error getting price by ID {coingecko_id}: {e}")
            return None
    
    def _get_price_by_contract(self, contract_address: str) -> Optional[float]:
        """Get price using contract address"""
        try:
            url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum"
            params = {
                'contract_addresses': contract_address,
                'vs_currencies': 'usd'
            }
            
            if self.coingecko_api_key:
                params['x_cg_demo_api_key'] = self.coingecko_api_key
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return data.get(contract_address.lower(), {}).get('usd')
            
        except Exception as e:
            print(f"Error getting price by contract {contract_address}: {e}")
            return None
    
    def calculate_usd_value(self, token_address: str, amount: int, decimals: int = 18) -> Optional[float]:
        """Calculate USD value of token amount"""
        try:
            price = self.get_token_price(token_address)
            if price is None:
                return None
            
            token_amount = amount / (10 ** decimals)
            return token_amount * price
            
        except Exception as e:
            print(f"Error calculating USD value: {e}")
            return None
    
    def get_eth_price(self) -> Optional[float]:
        """Get current ETH price in USD"""
        return self.get_token_price('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')
    
    def estimate_transaction_value(self, decoded_tx: Dict) -> Optional[float]:
        """Estimate USD value of a decoded transaction"""
        try:
            params = decoded_tx.get('decoded_params', {})
            
            if decoded_tx.get('value', 0) > 0:
                eth_price = self.get_eth_price()
                if eth_price:
                    eth_amount = decoded_tx['value'] / 1e18
                    return eth_amount * eth_price
            
            path = params.get('path', [])
            amount_in = params.get('amount_in', 0)
            
            if path and amount_in > 0:
                token_address = path[0]
                return self.calculate_usd_value(token_address, amount_in)
            
            return None
            
        except Exception as e:
            print(f"Error estimating transaction value: {e}")
            return None
