# NBJ Condenser - Quick Deploy Reference

## Initial Setup (once per VM)

```bash
# 1. Set up VM dependencies
ssh conciser 'bash -s' < setup-vm.sh

# 2. Configure firewall
ssh conciser 'bash -s' < setup-firewall.sh

# 3. Deploy app
./deploy.sh

# 4. Copy environment file
./deploy-env.sh

# 5. Set up cleanup cron
ssh conciser 'bash -s' < setup-cron.sh
```

**Don't forget:** Add Ingress Rule in Oracle Cloud Console for port 5000!

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
- Ngrok: https://conciser-aurora.ngrok.dev

See **DEPLOY.md** for full documentation.
