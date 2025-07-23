import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from typing import Dict, List
from config import Config
from src.utils.database import Database
from src.attack_detector import SandwichAttack
import time

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MEVProtectionBot:
    def __init__(self, attack_detector=None):
        self.config = Config()
        self.db = Database()
        self.attack_detector = attack_detector
        self.application = None
        
        self.stats = {
            'total_users': 0,
            'active_subscriptions': 0,
            'alerts_sent': 0,
            'start_time': time.time()
        }
    
    async def initialize(self):
        """Initialize the Telegram bot"""
        if not self.config.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN not provided in config")
        
        self.application = Application.builder().token(self.config.TELEGRAM_BOT_TOKEN).build()
        
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("unsubscribe", self.unsubscribe_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("threshold", self.threshold_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        print("Telegram bot initialized successfully")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        self.db.add_user(chat_id, user.username)
        self.stats['total_users'] += 1
        
        welcome_message = f"""
🛡️ **MEV Protection Alert Bot**

Welcome {user.first_name}! I help protect you from sandwich attacks on Ethereum.

**What I do:**
• Monitor Ethereum mempool for sandwich attacks
• Alert you before your transactions get exploited
• Provide protection recommendations

**Commands:**
/subscribe - Start receiving alerts
/unsubscribe - Stop receiving alerts  
/stats - View protection statistics
/threshold <amount> - Set alert threshold (default: $50)
/help - Show this help message

**Get Started:**
1. Use /subscribe to enable alerts
2. Set your alert threshold with /threshold
3. Get protected from MEV attacks!

⚡ **Powered by Flashbots Protect**
        """
        
        keyboard = [
            [InlineKeyboardButton("🔔 Subscribe to Alerts", callback_data="subscribe")],
            [InlineKeyboardButton("📊 View Stats", callback_data="stats")],
            [InlineKeyboardButton("ℹ️ Learn About MEV", callback_data="learn_mev")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = """
🛡️ **MEV Protection Bot Commands**

**Basic Commands:**
/start - Initialize bot and get welcome message
/help - Show this help message

**Alert Management:**
/subscribe - Enable sandwich attack alerts
/unsubscribe - Disable alerts
/threshold <amount> - Set minimum loss threshold for alerts
  Example: `/threshold 100` (alerts for losses > $100)

**Information:**
/stats - View your protection statistics and recent attacks

**How It Works:**
1. I monitor the Ethereum mempool in real-time
2. When I detect a potential sandwich attack targeting your transaction
3. I send you an instant alert with:
   • Transaction hash
   • Estimated loss amount
   • Recommended action (cancel/protect)

**Protection Tips:**
• Use Flashbots Protect RPC to avoid public mempool
• Set appropriate slippage (0.5-1% for most trades)
• Consider transaction timing during high volatility

**Need Help?**
Contact support or visit our documentation for more information.
        """
        
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /subscribe command"""
        chat_id = update.effective_chat.id
        user = self.db.get_user(chat_id)
        
        if not user:
            self.db.add_user(chat_id, update.effective_user.username)
            user = self.db.get_user(chat_id)
        
        if user['is_active']:
            message = "✅ You're already subscribed to MEV protection alerts!"
        else:
            self.db.add_user(chat_id, update.effective_user.username)
            self.stats['active_subscriptions'] += 1
            
            message = f"""
✅ **Successfully subscribed to MEV Protection Alerts!**

**Your Settings:**
• Alert threshold: ${user['alert_threshold']:.0f}
• Status: Active 🟢

**What happens next:**
• I'll monitor for sandwich attacks targeting your transactions
• You'll receive instant alerts when attacks are detected
• Alerts include protection recommendations

**Tip:** Use `/threshold <amount>` to adjust your alert sensitivity.
            """
        
        keyboard = [
            [InlineKeyboardButton("📊 View Stats", callback_data="stats")],
            [InlineKeyboardButton("⚙️ Adjust Threshold", callback_data="set_threshold")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unsubscribe command"""
        chat_id = update.effective_chat.id
        user = self.db.get_user(chat_id)
        
        if user and user['is_active']:
            self.stats['active_subscriptions'] = max(0, self.stats['active_subscriptions'] - 1)
            
            message = """
❌ **Unsubscribed from MEV Protection Alerts**

You will no longer receive sandwich attack alerts.

**To resubscribe:** Use /subscribe anytime

**Stay Safe:** Consider using Flashbots Protect RPC even without alerts:
`https://rpc.flashbots.net`
            """
        else:
            message = "ℹ️ You're not currently subscribed to alerts."
        
        keyboard = [
            [InlineKeyboardButton("🔔 Resubscribe", callback_data="subscribe")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        chat_id = update.effective_chat.id
        
        user = self.db.get_user(chat_id)
        daily_stats = self.db.get_daily_stats()
        recent_attacks = self.db.get_recent_attacks(10)
        
        runtime_hours = (time.time() - self.stats['start_time']) / 3600
        
        stats_message = f"""
📊 **MEV Protection Statistics**

**Your Account:**
• Status: {'🟢 Active' if user and user['is_active'] else '🔴 Inactive'}
• Alert threshold: ${user['alert_threshold']:.0f if user else 50}

**Today's Protection:**
• Attacks detected: {daily_stats['attacks_today']}
• Total value saved: ${daily_stats['total_saved_today']:.2f}

**System Stats:**
• Total users: {self.stats['total_users']}
• Active subscriptions: {self.stats['active_subscriptions']}
• Alerts sent: {self.stats['alerts_sent']}
• Uptime: {runtime_hours:.1f} hours

**Recent Attacks:**
        """
        
        if recent_attacks:
            for i, attack in enumerate(recent_attacks[:5]):
                stats_message += f"\n{i+1}. ${attack['estimated_loss']:.0f} loss - {attack['token_pair']}"
        else:
            stats_message += "\nNo recent attacks detected"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="stats")],
            [InlineKeyboardButton("🛡️ Learn Protection", callback_data="learn_protection")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(stats_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def threshold_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /threshold command"""
        chat_id = update.effective_chat.id
        
        if context.args:
            try:
                threshold = float(context.args[0])
                if threshold < 1 or threshold > 10000:
                    raise ValueError("Threshold must be between $1 and $10,000")
                
                self.db.update_user_threshold(chat_id, threshold)
                
                message = f"""
✅ **Alert threshold updated to ${threshold:.0f}**

You'll now receive alerts for potential losses above this amount.

**Recommendations:**
• $50-100: High sensitivity (more alerts)
• $100-500: Balanced protection
• $500+: Only major attacks

Current setting: ${threshold:.0f}
                """
                
            except (ValueError, IndexError):
                message = """
❌ **Invalid threshold amount**

**Usage:** `/threshold <amount>`
**Examples:**
• `/threshold 50` - Alert for losses > $50
• `/threshold 200` - Alert for losses > $200

**Valid range:** $1 - $10,000
                """
        else:
            user = self.db.get_user(chat_id)
            current_threshold = user['alert_threshold'] if user else 50
            
            message = f"""
⚙️ **Current Alert Threshold: ${current_threshold:.0f}**

**To change:** `/threshold <new_amount>`

**Examples:**
• `/threshold 25` - More sensitive (more alerts)
• `/threshold 100` - Balanced protection  
• `/threshold 500` - Less sensitive (fewer alerts)
            """
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "subscribe":
            await self.subscribe_command(update, context)
        elif query.data == "stats":
            await self.stats_command(update, context)
        elif query.data == "learn_mev":
            await self.send_mev_education(query)
        elif query.data == "learn_protection":
            await self.send_protection_tips(query)
        elif query.data == "set_threshold":
            await self.send_threshold_help(query)
    
    async def send_mev_education(self, query):
        """Send MEV education message"""
        education_message = """
🎓 **What is MEV (Maximal Extractable Value)?**

**MEV** is profit extracted from users by reordering, including, or excluding transactions in blocks.

**Common MEV Attacks:**

🥪 **Sandwich Attacks**
• Attacker sees your trade in mempool
• Places buy order before yours (front-run)
• Places sell order after yours (back-run)
• Profits from price impact of your trade

💸 **How You Lose Money:**
• Your trade gets worse execution price
• Higher slippage than expected
• Can lose 1-5% of transaction value

🛡️ **Protection Methods:**
• Use private mempools (Flashbots Protect)
• Set tight slippage tolerance
• Use MEV-protected RPCs
• Time trades carefully

**This bot helps by alerting you before attacks happen!**
        """
        
        await query.edit_message_text(education_message, parse_mode='Markdown')
    
    async def send_protection_tips(self, query):
        """Send protection tips"""
        tips_message = """
🛡️ **MEV Protection Best Practices**

**1. Use Flashbots Protect RPC**
```
https://rpc.flashbots.net
```
• Sends transactions to private mempool
• Prevents front-running
• Free to use

**2. Optimize Slippage Settings**
• 0.1-0.5%: Stable pairs (USDC/USDT)
• 0.5-1%: Major tokens (ETH/BTC)
• 1-3%: Volatile/small cap tokens

**3. Transaction Timing**
• Avoid high volatility periods
• Monitor gas prices
• Use limit orders when possible

**4. Advanced Protection**
• Use CoW Protocol for batch auctions
• Consider 1inch Fusion for MEV protection
• Use private relayers for large trades

**5. Stay Informed**
• Monitor this bot's alerts
• Check transaction status before confirming
• Learn about new protection methods

**Remember:** Prevention is better than detection!
        """
        
        await query.edit_message_text(tips_message, parse_mode='Markdown')
    
    async def send_threshold_help(self, query):
        """Send threshold setting help"""
        threshold_help = """
⚙️ **Setting Your Alert Threshold**

Your threshold determines when you receive alerts.

**Threshold Guidelines:**

💰 **$25-50** (High Sensitivity)
• Get alerts for small losses
• More notifications
• Good for frequent traders

💰 **$50-200** (Balanced)
• Recommended for most users
• Catches significant attacks
• Manageable alert volume

💰 **$200-500** (Conservative)
• Only major attacks
• Fewer notifications
• Good for large trades only

**To set:** Use `/threshold <amount>`
**Example:** `/threshold 100`

**Current recommendation:** $50-100 for most users
        """
        
        await query.edit_message_text(threshold_help, parse_mode='Markdown')
    
    async def send_attack_alert(self, attack: SandwichAttack):
        """Send sandwich attack alert to subscribed users"""
        try:
            
            alert_message = f"""
🚨 **SANDWICH ATTACK DETECTED!**

**Transaction at Risk:**
• Hash: `{attack.victim_tx.tx_hash[:20]}...`
• Estimated Loss: **${attack.estimated_victim_loss:.2f}**
• Confidence: {attack.confidence_score:.0%}

**Attack Details:**
• Token Pair: {attack.victim_tx.token_pair[0][:8]}.../{attack.victim_tx.token_pair[1][:8]}...
• Attacker Profit: ${attack.estimated_profit:.2f}

**🛡️ RECOMMENDED ACTIONS:**
1. **Cancel transaction immediately**
2. Use Flashbots Protect RPC:
   `https://rpc.flashbots.net`
3. Reduce slippage tolerance
4. Wait for lower network congestion

**⏰ Time is critical - Act now!**
            """
            
            keyboard = [
                [InlineKeyboardButton("🚫 How to Cancel", callback_data="cancel_help")],
                [InlineKeyboardButton("🛡️ Use Flashbots", url="https://docs.flashbots.net/flashbots-protect/rpc/quick-start")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            print(f"ALERT SENT: {alert_message}")
            self.stats['alerts_sent'] += 1
            
        except Exception as e:
            logger.error(f"Error sending attack alert: {e}")
    
    async def start_bot(self):
        """Start the Telegram bot"""
        if not self.application:
            await self.initialize()
        
        print("Starting Telegram bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        print("Telegram bot is running...")
    
    async def stop_bot(self):
        """Stop the Telegram bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        print("Telegram bot stopped")

async def test_telegram_bot():
    """Test the Telegram bot"""
    bot = MEVProtectionBot()
    
    try:
        await bot.initialize()
        print("Bot initialized successfully")
        
        from src.attack_detector import SandwichAttack, PendingTransaction
        import uuid
        
        victim_tx = PendingTransaction(
            tx_hash=f"0x{uuid.uuid4().hex}",
            from_address="0x1234567890123456789012345678901234567890",
            to_address="0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
            gas_price=30000000000,
            decoded_data={},
            timestamp=time.time(),
            token_pair=('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86a33E6441c8C0E6C9b8C4C5C1B8C8C8C8C8C'),
            estimated_value=5000,
            slippage=2.5
        )
        
        mock_attack = SandwichAttack(
            victim_tx=victim_tx,
            front_run_tx=None,
            back_run_tx=None,
            estimated_profit=100,
            estimated_victim_loss=150,
            confidence_score=0.85
        )
        
        await bot.send_attack_alert(mock_attack)
        
    except Exception as e:
        print(f"Error testing bot: {e}")

if __name__ == "__main__":
    asyncio.run(test_telegram_bot())
