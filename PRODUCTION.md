# NBJ Condenser - Production Deployment Guide

This guide covers deploying NBJ Condenser for production use with proper HTTP/HTTPS setup.

## Overview

**Development Setup:**
- Flask dev server on port 5000
- Direct access: `http://ip:5000`
- Good for testing, not for production

**Production Setup:**
- Flask on port 5000 (internal only)
- Nginx reverse proxy on ports 80/443
- Access: `http://domain.com` or `https://domain.com`
- Proper timeouts, caching, SSL/TLS

## Initial Setup

### 1. Run Standard Setup

First, complete the standard VM setup:

```bash
./setup-new-vm.sh
```

This installs dependencies and deploys the app. At the end, you'll have Flask running on port 5000.

### 2. Set Up Nginx Reverse Proxy

Install and configure nginx to proxy port 80 → Flask on port 5000:

```bash
ssh conciser 'bash -s' < setup-nginx.sh
```

This will:
- Install nginx
- Configure reverse proxy
- Open port 80 in VM firewall
- Show Oracle Cloud Security List instructions

**Important:** Add Oracle Cloud Ingress Rule for port 80 (see script output).

### 3. Test HTTP Access

```bash
curl http://129.80.134.46
# Should show the extension install page
```

### 4. Set Up SSL/TLS (Optional but Recommended)

If you have a domain name pointing to your server:

```bash
ssh conciser 'bash -s' < setup-ssl.sh
```

You'll be prompted for:
- Domain name (e.g., `conciser.example.com`)
- Email address (for Let's Encrypt notifications)

This will:
- Install certbot
- Obtain SSL certificate from Let's Encrypt
- Configure nginx for HTTPS
- Set up auto-renewal
- Open port 443 in VM firewall

**Important:** Add Oracle Cloud Ingress Rule for port 443 (see script output).

### 5. Test HTTPS Access

```bash
curl https://conciser.example.com
# Should show the extension install page over HTTPS
```

## Oracle Cloud Security Lists

You need to configure these Ingress Rules in Oracle Cloud Console:

### For HTTP Only (Development/Testing)
- Port 80: HTTP traffic

### For Production (HTTP + HTTPS)
- Port 80: HTTP traffic (redirects to HTTPS)
- Port 443: HTTPS traffic

### Configuration Steps:

1. Go to [Oracle Cloud Console](https://cloud.oracle.com)
2. Navigate to: **Networking** → **Virtual Cloud Networks**
3. Click your VCN → **Security Lists** → **Default Security List**
4. Click **Add Ingress Rules**
5. For each port (80, 443), add:
   - **Source Type:** CIDR
   - **Source CIDR:** `0.0.0.0/0`
   - **IP Protocol:** TCP
   - **Destination Port Range:** `80` (or `443`)
6. Click **Add Ingress Rules**

**Note:** Port 5000 should NOT be exposed to the internet in production. Keep it internal only.

## Architecture

```
Internet
    ↓
Oracle Cloud Security List (ports 80, 443)
    ↓
Oracle Linux Firewall (ports 80, 443)
    ↓
Nginx (reverse proxy)
    ↓
Flask App (port 5000, localhost only)
```

## Nginx Configuration

The nginx config is at: `/etc/nginx/conf.d/nbj-condenser.conf`

Key settings:
- `client_max_body_size 500M` - Allow large video files
- Long timeouts (300s) - For video processing
- Proxy headers - Preserve client info

To edit:
```bash
ssh conciser 'sudo nano /etc/nginx/conf.d/nbj-condenser.conf'
ssh conciser 'sudo nginx -t'  # Test config
ssh conciser 'sudo systemctl reload nginx'  # Apply changes
```

## SSL/TLS Certificate Management

### Auto-Renewal

Certificates auto-renew via systemd timer:
```bash
ssh conciser 'sudo systemctl status certbot-renew.timer'
```

### Manual Renewal

```bash
ssh conciser 'sudo certbot renew'
```

### Certificate Status

```bash
ssh conciser 'sudo certbot certificates'
```

## Monitoring

### Check Service Status

```bash
# Nginx
ssh conciser 'sudo systemctl status nginx'

# Flask app
ssh conciser 'pgrep -f "server/app.py"'

# View logs
ssh conciser 'tail -f /var/log/nginx/access.log'
ssh conciser 'tail -f /var/log/nginx/error.log'
ssh conciser 'tail -f nbj-condenser/server.log'
```

### Health Check

```bash
# Via nginx (production)
curl http://129.80.134.46/health

# Direct to Flask (internal)
ssh conciser 'curl http://localhost:5000/health'
```

## Performance Tuning

### Nginx Worker Processes

Edit `/etc/nginx/nginx.conf`:
```nginx
worker_processes auto;  # Use all CPU cores
worker_connections 1024;  # Max connections per worker
```

### Flask Workers

For higher concurrency, use gunicorn instead of Flask dev server:

```bash
# Install gunicorn in venv
ssh conciser 'cd nbj-condenser && source venv/bin/activate && pip install gunicorn'

# Run with multiple workers
ssh conciser 'cd nbj-condenser && source venv/bin/activate && gunicorn -w 4 -b 127.0.0.1:5000 server.app:app'
```

Update `deploy.sh` to use gunicorn instead of `python server/app.py`.

## Security Hardening

### 1. Restrict Flask to Localhost Only

Flask should only listen on `127.0.0.1:5000`, not `0.0.0.0:5000`.

In `server/app.py`, use:
```python
app.run(host='127.0.0.1', port=5000)
```

### 2. Rate Limiting (Optional)

Add to nginx config:
```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20;
    # ... rest of config
}
```

### 3. Firewall - Block Port 5000

Ensure port 5000 is NOT in Oracle Cloud Security List. It should only be accessible via nginx.

## Troubleshooting

### Nginx won't start

```bash
# Check config syntax
ssh conciser 'sudo nginx -t'

# Check error logs
ssh conciser 'sudo tail -50 /var/log/nginx/error.log'

# Check if port 80 is already in use
ssh conciser 'sudo netstat -tlnp | grep :80'
```

### SSL certificate failed

```bash
# Check DNS
dig conciser.example.com

# Check port 80 is accessible (required for Let's Encrypt)
curl -I http://conciser.example.com

# Try manual renewal
ssh conciser 'sudo certbot renew --dry-run'
```

### 502 Bad Gateway

Nginx can't reach Flask. Check:
```bash
# Is Flask running?
ssh conciser 'pgrep -f "server/app.py"'

# Is Flask listening on 5000?
ssh conciser 'netstat -tlnp | grep 5000'

# Check Flask logs
ssh conciser 'tail -50 nbj-condenser/server.log'
```

## Maintenance

### Update Nginx Config

```bash
# Edit config
ssh conciser 'sudo nano /etc/nginx/conf.d/nbj-condenser.conf'

# Test
ssh conciser 'sudo nginx -t'

# Apply
ssh conciser 'sudo systemctl reload nginx'
```

### Restart Services

```bash
# Restart nginx
ssh conciser 'sudo systemctl restart nginx'

# Restart Flask (via deploy)
./deploy.sh
```

### View Access Logs

```bash
# Real-time
ssh conciser 'sudo tail -f /var/log/nginx/access.log'

# Last 100 requests
ssh conciser 'sudo tail -100 /var/log/nginx/access.log'

# Search for errors
ssh conciser 'sudo grep "50[0-9]" /var/log/nginx/access.log'
```

## Backup Considerations

**Critical files to backup:**
- `/home/opc/nbj-condenser/.env` - API keys
- `/etc/nginx/conf.d/nbj-condenser.conf` - Nginx config
- `/etc/letsencrypt/` - SSL certificates (if using)

**Automated backups recommended for:**
- Video output files (if long-term storage needed)
- Server logs (for analytics)

## Next Steps

After production setup:
1. Set up monitoring/alerting (optional)
2. Configure log rotation
3. Set up automated backups
4. Consider CDN for static assets
5. Set up staging environment

See `DEPLOY.md` for ongoing deployment workflow.
