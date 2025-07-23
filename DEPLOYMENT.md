# 🚀 MEV Protection Bot - Deployment Guide

## Overview
This guide covers deploying the MEV Protection Alert Bot to production environments.

## Prerequisites

### Required API Keys
1. **Flashbots Protect RPC**: `https://rpc.flashbots.net`
2. **Telegram Bot Token**: From @BotFather
3. **Alchemy API Key**: For WebSocket monitoring
4. **CoinGecko API Key**: For price feeds

### System Requirements
- **Python**: 3.8+
- **Memory**: 512MB minimum, 1GB recommended
- **Storage**: 1GB for logs and database
- **Network**: Stable internet connection

## Local Deployment

### 1. Environment Setup
```bash
# Clone repository
git clone <repository-url>
cd mev-protection-bot

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### 2. Configuration
```env
FLASHBOTS_PROTECT_RPC=https://rpc.flashbots.net
ALCHEMY_API_KEY=your_alchemy_key_here
TELEGRAM_BOT_TOKEN=your_bot_token_here
COINGECKO_API_KEY=your_coingecko_key_here
ETHEREUM_RPC_URL=https://rpc.flashbots.net
MIN_SLIPPAGE_THRESHOLD=0.5
MIN_LOSS_THRESHOLD=50
ALERT_DELAY_SECONDS=2
```

### 3. Run System
```bash
# Demo mode (no API keys needed)
python main.py demo

# Production mode
python main.py

# Test mode
python main.py test
```

## Cloud Deployment

### AWS EC2 Deployment

#### 1. Launch EC2 Instance
```bash
# Launch Ubuntu 20.04 LTS instance
# t3.small or larger recommended
# Open ports: 22 (SSH), 5000 (Dashboard)
```

#### 2. Setup Instance
```bash
# Connect to instance
ssh -i your-key.pem ubuntu@your-instance-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install python3 python3-pip git -y

# Clone repository
git clone <repository-url>
cd mev-protection-bot

# Install dependencies
pip3 install -r requirements.txt
```

#### 3. Configure Environment
```bash
# Create environment file
cp .env.example .env
nano .env  # Add your API keys
```

#### 4. Setup Process Manager
```bash
# Install PM2
sudo npm install -g pm2

# Create PM2 ecosystem file
cat > ecosystem.config.js << EOF
module.exports = {
  apps: [{
    name: 'mev-protection-bot',
    script: 'python3',
    args: 'main.py',
    cwd: '/home/ubuntu/mev-protection-bot',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production'
    }
  }]
}
EOF

# Start application
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

#### 5. Setup Nginx (Optional)
```bash
# Install Nginx
sudo apt install nginx -y

# Configure reverse proxy
sudo cat > /etc/nginx/sites-available/mev-bot << EOF
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/mev-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### DigitalOcean Deployment

#### 1. Create Droplet
```bash
# Create Ubuntu 20.04 droplet
# $10/month droplet recommended
# Add SSH key for access
```

#### 2. Setup Application
```bash
# Connect via SSH
ssh root@your-droplet-ip

# Install dependencies
apt update && apt upgrade -y
apt install python3 python3-pip git nginx -y

# Clone and setup
git clone <repository-url>
cd mev-protection-bot
pip3 install -r requirements.txt
cp .env.example .env
# Edit .env with API keys
```

#### 3. Setup Systemd Service
```bash
# Create service file
cat > /etc/systemd/system/mev-bot.service << EOF
[Unit]
Description=MEV Protection Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/mev-protection-bot
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
systemctl enable mev-bot
systemctl start mev-bot
systemctl status mev-bot
```

## Docker Deployment

### 1. Create Dockerfile
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "main.py"]
```

### 2. Build and Run
```bash
# Build image
docker build -t mev-protection-bot .

# Run container
docker run -d \
  --name mev-bot \
  -p 5000:5000 \
  --env-file .env \
  --restart unless-stopped \
  mev-protection-bot
```

### 3. Docker Compose
```yaml
version: '3.8'

services:
  mev-bot:
    build: .
    ports:
      - "5000:5000"
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      - ./data:/app/data
```

## Monitoring & Maintenance

### Health Checks
```bash
# Check application status
curl http://localhost:5000/api/stats

# Check logs
tail -f /var/log/mev-bot.log

# PM2 monitoring
pm2 monit
```

### Log Management
```bash
# Setup log rotation
sudo cat > /etc/logrotate.d/mev-bot << EOF
/var/log/mev-bot.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    copytruncate
}
EOF
```

### Backup Strategy
```bash
# Backup database
cp data/mev_protection.db backups/mev_protection_$(date +%Y%m%d).db

# Backup configuration
tar -czf config_backup_$(date +%Y%m%d).tar.gz .env config.py
```

## Security Considerations

### Firewall Setup
```bash
# UFW configuration
sudo ufw allow ssh
sudo ufw allow 5000/tcp
sudo ufw enable
```

### SSL Certificate (Let's Encrypt)
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

### Environment Security
```bash
# Secure .env file
chmod 600 .env
chown root:root .env

# Use secrets management for production
# Consider AWS Secrets Manager or similar
```

## Troubleshooting

### Common Issues

#### 1. API Connection Errors
```bash
# Check network connectivity
curl -I https://rpc.flashbots.net
curl -I https://api.telegram.org

# Verify API keys
grep -v "^#" .env | grep -v "^$"
```

#### 2. Memory Issues
```bash
# Monitor memory usage
free -h
ps aux | grep python

# Increase swap if needed
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

#### 3. Database Issues
```bash
# Check database file
ls -la data/mev_protection.db

# Backup and recreate if corrupted
mv data/mev_protection.db data/mev_protection.db.backup
python3 -c "from src.utils.database import Database; Database()"
```

### Performance Optimization

#### 1. Database Optimization
```python
# Add to config.py
DATABASE_CLEANUP_INTERVAL = 3600  # 1 hour
MAX_ATTACK_RECORDS = 10000
```

#### 2. Memory Management
```python
# Add to main.py
import gc
gc.set_threshold(700, 10, 10)
```

#### 3. Connection Pooling
```python
# Add to mempool_monitor.py
import aiohttp
connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
```

## Scaling Considerations

### Horizontal Scaling
- Use load balancer for multiple instances
- Shared database (PostgreSQL/MySQL)
- Redis for caching and session management

### Vertical Scaling
- Increase instance size
- Add more CPU cores
- Increase memory allocation

### Database Scaling
- Move to PostgreSQL for better performance
- Implement read replicas
- Add database connection pooling

## Support

For deployment issues:
1. Check logs first
2. Verify API connectivity
3. Review configuration
4. Contact support with error details
