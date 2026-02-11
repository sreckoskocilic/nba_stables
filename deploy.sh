#!/bin/bash
# NBA Stables - Hetzner Deployment Script
# Run this on a fresh Ubuntu 22.04 server

set -e

DOMAIN="${1:-nbastables.com}"
REPO_URL="${2:-https://github.com/sreckoskocilic/nba_stables.git}"

echo "==================================="
echo "NBA Stables Deployment"
echo "Domain: $DOMAIN"
echo "==================================="

# Update system
echo "[1/6] Updating system..."
apt update && apt upgrade -y

# Install Docker
echo "[2/6] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

# Install Docker Compose
echo "[3/6] Installing Docker Compose..."
apt install -y docker-compose

# Clone repository
echo "[4/6] Cloning repository..."
cd /opt
if [ -d "nba_stables" ]; then
    cd nba_stables
    git pull
else
    git clone "$REPO_URL" nba_stables
    cd nba_stables
fi

# Start the app
echo "[5/6] Starting application..."
docker-compose down 2>/dev/null || true
docker-compose up -d --build

# Install and configure Caddy (reverse proxy with auto-SSL)
echo "[6/6] Setting up Caddy (SSL)..."
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null || true
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy

# Configure Caddy
cat > /etc/caddy/Caddyfile << EOF
$DOMAIN {
    reverse_proxy localhost:8000
}

www.$DOMAIN {
    redir https://$DOMAIN{uri}
}
EOF

# Restart Caddy
systemctl restart caddy
systemctl enable caddy

# Setup firewall
echo "Setting up firewall..."
ufw allow 22
ufw allow 80
ufw allow 443
ufw --force enable

echo ""
echo "==================================="
echo "Deployment complete!"
echo "==================================="
echo ""
echo "Your app is now running at:"
echo "  https://$DOMAIN"
echo ""
echo "Useful commands:"
echo "  cd /opt/nba_stables"
echo "  docker-compose logs -f    # View logs"
echo "  docker-compose restart    # Restart app"
echo "  docker-compose pull && docker-compose up -d  # Update"
echo ""
echo "Make sure your DNS A records point to this server:"
echo "  $DOMAIN -> $(curl -s ifconfig.me)"
echo "  www.$DOMAIN -> $(curl -s ifconfig.me)"
echo ""
