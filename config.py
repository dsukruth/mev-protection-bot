import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    FLASHBOTS_PROTECT_RPC = os.getenv('FLASHBOTS_PROTECT_RPC', 'https://rpc.flashbots.net')
    ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY', '')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY', '')
    
    ETHEREUM_RPC_URL = os.getenv('ETHEREUM_RPC_URL', 'https://eth-mainnet.g.alchemy.com/v2/' + ALCHEMY_API_KEY)
    
    MIN_SLIPPAGE_THRESHOLD = float(os.getenv('MIN_SLIPPAGE_THRESHOLD', '0.5'))  # 0.5%
    MIN_LOSS_THRESHOLD = float(os.getenv('MIN_LOSS_THRESHOLD', '50'))  # $50
    ALERT_DELAY_SECONDS = int(os.getenv('ALERT_DELAY_SECONDS', '2'))
    
    UNISWAP_V2_ROUTER = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
    UNISWAP_V3_ROUTER = '0xE592427A0AEce92De3Edee1F18E0157C05861564'
    SUSHISWAP_ROUTER = '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F'
    
    DATABASE_PATH = 'mev_protection.db'
    
    FLASK_HOST = '0.0.0.0'
    FLASK_PORT = 5000
    FLASK_DEBUG = True
