# NBJ Condenser - Quick Deploy Reference

## Development Setup (Testing)

### One Command

```bash
./setup-new-vm.sh
```

**Result:** Flask dev server on port 5000\
**Access:** `http://129.80.134.46:5000`\
**Oracle Cloud Rule:** Port 5000

---

## Production Setup (Public Use)

### Step 1: Base Setup

```bash
./setup-new-vm.sh
```

### Step 2: Add Nginx (Port 80)

```bash
ssh conciser 'bash -s' < setup-nginx.sh
```

**Result:** HTTP on port 80\
**Access:** `http://129.80.134.46`\
**Oracle Cloud Rule:** Port 80

### Step 3: Add SSL (Port 443) - Optional

```bash
ssh conciser 'bash -s' < setup-ssl.sh
```

**Result:** HTTPS on port 443\
**Access:** `https://yourdomain.com`\
**Oracle Cloud Rule:** Port 443\
**Requires:** Domain name pointing to server

---

## Manual Steps (Advanced)

```bash
# 1. Install system dependencies
ssh conciser 'bash -s' < terraform-vm.sh

# 2. Deploy app
./deploy.sh

# 3. Copy environment file
./deploy-env.sh

# 4. Configure firewall (port 5000)
ssh conciser 'bash -s' < setup-firewall.sh

# 5. Set up cleanup cron
ssh conciser 'bash -s' < setup-cron.sh

# 6. [Production] Add nginx
ssh conciser 'bash -s' < setup-nginx.sh

# 7. [Production] Add SSL
ssh conciser 'bash -s' < setup-ssl.sh
```

---

## Oracle Cloud Security Lists

**For Development (port 5000):**

- Add Ingress Rule: TCP port 5000

**For Production (ports 80, 443):**

- Add Ingress Rule: TCP port 80
- Add Ingress Rule: TCP port 443
- Remove port 5000 rule (keep Flask internal)

See scripts output for detailed instructions.

## Daily Deployment

```bash
./deploy.sh
```

That's it! Commits, pushes, deploys, and restarts the server.

## Common Commands

```bash
# View logs
ssh conciser 'tail -f nbj-condenser/server.log'

# Check health
ssh conciser 'curl -s http://localhost:5000/health'

# Manual cleanup
ssh conciser '/home/opc/nbj-condenser/scripts/cleanup.sh'

# Server status
ssh conciser 'pgrep -f "server/app.py"'
```

## URLs

- Local: http://129.80.134.46:5000
- Public: http://conciser.603apps.net

See **DEPLOY.md** for full documentation.
