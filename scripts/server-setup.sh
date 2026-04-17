#!/bin/bash
# ============================================================
# CryptoAnalyzer — Hetzner VPS Setup Script
# Server: CX21 (2 vCPU, 4GB RAM) — Ubuntu 22.04 LTS
# ============================================================
# Usage: sudo bash server-setup.sh
# ============================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

# ============================================================
# 1. System Update
# ============================================================
log "Updating system packages..."
apt update && apt upgrade -y

# ============================================================
# 2. Create Non-Root User
# ============================================================
USERNAME="deployer"
if id "$USERNAME" &>/dev/null; then
    warn "User $USERNAME already exists"
else
    log "Creating user: $USERNAME"
    adduser --disabled-password --gecos "" $USERNAME
    usermod -aG sudo $USERNAME
    echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/$USERNAME
    
    # Copy SSH keys from root
    mkdir -p /home/$USERNAME/.ssh
    cp /root/.ssh/authorized_keys /home/$USERNAME/.ssh/
    chown -R $USERNAME:$USERNAME /home/$USERNAME/.ssh
    chmod 700 /home/$USERNAME/.ssh
    chmod 600 /home/$USERNAME/.ssh/authorized_keys
    log "User $USERNAME created with SSH access"
fi

# ============================================================
# 3. Install Dependencies
# ============================================================
log "Installing dependencies..."
apt install -y \
    git \
    curl \
    wget \
    unzip \
    software-properties-common \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    nginx \
    certbot \
    python3-certbot-nginx \
    ufw

# Node.js 20 LTS
log "Installing Node.js 20 LTS..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# PM2
log "Installing PM2..."
npm install -g pm2

# ============================================================
# 4. PostgreSQL
# ============================================================
log "Installing PostgreSQL..."
apt install -y postgresql postgresql-contrib

DB_NAME="crypto_analyzer"
DB_USER="crypto_user"
DB_PASS=$(openssl rand -base64 24)

sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || warn "DB user already exists"
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || warn "DB already exists"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
sudo -u postgres psql -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";"

log "Database created: $DB_NAME"
log "Database user: $DB_USER"
log "Database password: $DB_PASS"
warn "⚠️  SAVE THIS PASSWORD! It won't be shown again."

# ============================================================
# 5. Firewall (UFW)
# ============================================================
log "Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
log "Firewall enabled: 22, 80, 443"

# ============================================================
# 6. SSH Security
# ============================================================
log "Securing SSH..."
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart sshd
log "SSH password login disabled"

# ============================================================
# 7. Project Directory
# ============================================================
PROJECT_DIR="/opt/crypto-analyzer"
mkdir -p $PROJECT_DIR
chown $USERNAME:$USERNAME $PROJECT_DIR
log "Project directory: $PROJECT_DIR"

# ============================================================
# 8. Nginx Config
# ============================================================
cat > /etc/nginx/sites-available/crypto-analyzer << 'EOF'
server {
    listen 80;
    server_name _;

    # Frontend (Next.js)
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
EOF

ln -sf /etc/nginx/sites-available/crypto-analyzer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
log "Nginx configured"

# ============================================================
# Summary
# ============================================================
echo ""
echo "============================================================"
echo "  ✅ Server Setup Complete!"
echo "============================================================"
echo "  User:       $USERNAME"
echo "  DB Name:    $DB_NAME"
echo "  DB User:    $DB_USER"
echo "  DB Pass:    $DB_PASS"
echo "  Project:    $PROJECT_DIR"
echo "  Firewall:   22, 80, 443"
echo "============================================================"
echo ""
echo "  Next steps:"
echo "  1. Save the DB password above"
echo "  2. SSH as: ssh $USERNAME@YOUR_SERVER_IP"
echo "  3. Clone repo: cd $PROJECT_DIR && git clone YOUR_REPO ."
echo "  4. Add SSL: sudo certbot --nginx -d your-domain.com"
echo "============================================================"
