# NBJ Condenser - Port Configuration Guide

## Port Architecture

### Development Mode
```
Internet → Port 5000 → Flask Dev Server
```
- **Port 5000:** Flask development server (direct access)
- **Use case:** Testing, development
- **URL:** `http://129.80.134.46:5000`

### Production Mode
```
Internet → Port 80/443 → Nginx → Port 5000 (localhost) → Flask
```
- **Port 80:** HTTP (nginx reverse proxy)
- **Port 443:** HTTPS (nginx with SSL)
- **Port 5000:** Flask (internal only, not exposed)
- **Use case:** Production deployment
- **URL:** `http://yourdomain.com` or `https://yourdomain.com`

## Setup Commands

### Development (Port 5000)
```bash
./setup-new-vm.sh
# Configure Oracle Cloud: Allow port 5000
```

### Production (Ports 80/443)
```bash
./setup-new-vm.sh                          # Base setup
ssh conciser 'bash -s' < setup-nginx.sh    # Add nginx (port 80)
ssh conciser 'bash -s' < setup-ssl.sh      # Add SSL (port 443)
# Configure Oracle Cloud: Allow ports 80 and 443
# Remove port 5000 from Security List
```

## Oracle Cloud Security List

### Development Configuration
Add one Ingress Rule:
- **Port:** 5000
- **Protocol:** TCP
- **Source:** 0.0.0.0/0

### Production Configuration
Add two Ingress Rules:
- **Port:** 80 (HTTP)
- **Port:** 443 (HTTPS)
- **Protocol:** TCP
- **Source:** 0.0.0.0/0

**Security:** Do NOT expose port 5000 in production!

## Firewall Rules (On VM)

The setup scripts configure these automatically:

**Development:**
```bash
sudo firewall-cmd --add-port=5000/tcp
```

**Production:**
```bash
sudo firewall-cmd --add-service=http      # Port 80
sudo firewall-cmd --add-service=https     # Port 443
```

## Testing Connectivity

### Development (Port 5000)
```bash
# From internet
curl http://129.80.134.46:5000/health

# From VM
ssh conciser 'curl http://localhost:5000/health'
```

### Production (Ports 80/443)
```bash
# HTTP (Port 80)
curl http://129.80.134.46/health

# HTTPS (Port 443)
curl https://yourdomain.com/health

# Flask internal (should NOT work from internet)
curl http://129.80.134.46:5000/health  # Should timeout/fail
```

## Port Forwarding Flow

### Development
1. Request: `http://129.80.134.46:5000`
2. Oracle Security List: ✅ Allow port 5000
3. VM Firewall: ✅ Allow port 5000
4. Flask: ✅ Listening on `0.0.0.0:5000`
5. Response: Direct from Flask

### Production
1. Request: `http://129.80.134.46` (port 80)
2. Oracle Security List: ✅ Allow port 80
3. VM Firewall: ✅ Allow port 80
4. Nginx: ✅ Listening on port 80
5. Nginx proxies to: `http://127.0.0.1:5000`
6. Flask: ✅ Listening on `127.0.0.1:5000`
7. Response: Flask → Nginx → Client

## Security Implications

### Port 5000 Exposed (Development)
- ❌ Flask dev server is not production-ready
- ❌ No SSL/TLS encryption
- ❌ No request buffering
- ❌ Single-threaded (slow)
- ✅ OK for testing/development

### Ports 80/443 via Nginx (Production)
- ✅ Production-ready web server
- ✅ SSL/TLS encryption (port 443)
- ✅ Request buffering and timeouts
- ✅ Can add rate limiting
- ✅ Can use gunicorn for multi-process Flask

## Migration: Dev → Production

If you already set up development mode (port 5000):

```bash
# 1. Add nginx
ssh conciser 'bash -s' < setup-nginx.sh

# 2. Add SSL (optional)
ssh conciser 'bash -s' < setup-ssl.sh

# 3. Update Oracle Cloud Security List:
#    - Add port 80
#    - Add port 443
#    - Remove port 5000

# 4. Update Flask to listen on localhost only
#    (prevents direct access to port 5000)
```

No need to redeploy - nginx will proxy to existing Flask instance.

## Common Issues

### "Connection refused" on port 80
- Check nginx is running: `sudo systemctl status nginx`
- Check Oracle Cloud Security List has port 80

### "Connection refused" on port 443
- Check SSL was set up: `sudo certbot certificates`
- Check Oracle Cloud Security List has port 443

### Can still access port 5000 directly
- This is OK if you want it for debugging
- For security, remove port 5000 from Oracle Security List
- Change Flask to listen on `127.0.0.1:5000` instead of `0.0.0.0:5000`

## Recommended Setup

**For testing/development:**
- Use port 5000 (quick and simple)

**For public/production use:**
- Use ports 80/443 with nginx
- Block port 5000 from internet
- Set up SSL with Let's Encrypt

See `PRODUCTION.md` for complete production setup guide.
