# NBJ Condenser - Deployment Guide

This guide explains how to deploy NBJ Condenser to an Oracle Cloud VM (or any
similar Linux server).

## Prerequisites

- Oracle Cloud VM (Oracle Linux 9) with SSH access
- SSH config entry for the server (e.g., `ssh conciser`)
- GitHub repository with push access
- Local `.env` file with API keys

## One-Time Setup

### 1. Initial VM Setup

Install all required dependencies on the VM:

```bash
ssh conciser 'bash -s' < setup-vm.sh
```

This installs:

- Python 3 + pip
- Git
- ffmpeg
- yt-dlp

**Estimated time:** 3-5 minutes

### 2. Configure Firewall

Allow HTTP traffic on port 5000:

```bash
ssh conciser 'bash -s' < setup-firewall.sh
```

**Important:** You must also add an Ingress Rule in Oracle Cloud Console:

1. Go to: **Networking** → **Virtual Cloud Networks** → your VCN → **Security
   Lists**
2. Click on the default security list
3. Click **Add Ingress Rules**
4. Configure:
   - **Source CIDR:** `0.0.0.0/0`
   - **IP Protocol:** `TCP`
   - **Destination Port Range:** `5000`
5. Click **Add Ingress Rules**

### 3. Deploy Application

Deploy the code from GitHub:

```bash
./deploy.sh
```

This will:

- Commit local changes
- Push to GitHub
- Pull on the VM
- Set up Python venv
- Install dependencies
- Start the Flask server

### 4. Copy Environment File

Copy your `.env` file to the VM (contains API keys):

```bash
./deploy-env.sh
```

⚠️ **Security:** Never commit `.env` to git! It's already in `.gitignore`.

### 5. Set Up Cleanup Cron Job

Configure automatic cleanup of old files:

```bash
ssh conciser 'bash -s' < setup-cron.sh
```

This adds a cron job that runs daily at 3 AM to delete:

- `temp/` files older than 7 days
- `output/` files older than 7 days
- `server/output/` files older than 7 days
- Log files older than 30 days

## Daily Usage

### Deploy Updates

After making code changes, just run:

```bash
./deploy.sh
```

It handles everything:

- Commits your changes
- Pushes to GitHub
- Pulls on VM
- Restarts server

### Check Server Status

```bash
ssh conciser 'curl -s http://localhost:5000/health'
```

### View Logs

```bash
ssh conciser 'tail -f nbj-condenser/server.log'
```

### Manual Cleanup

```bash
ssh conciser '/home/opc/nbj-condenser/scripts/cleanup.sh'
```

## Server Management

### Start Server

```bash
ssh conciser 'cd nbj-condenser && source venv/bin/activate && nohup python server/app.py > server.log 2>&1 &'
```

### Stop Server

```bash
ssh conciser 'pkill -f "server/app.py"'
```

### Restart Server

```bash
ssh conciser 'pkill -f "server/app.py" && cd nbj-condenser && source venv/bin/activate && nohup python server/app.py > server.log 2>&1 &'
```

The `deploy.sh` script handles restart automatically.

## Access Points

Once deployed and firewall configured:

- **Health Check:** http://129.80.134.46:5000/health
- **Extension Install:** http://129.80.134.46:5000/start
- **API Endpoint:** http://129.80.134.46:5000/api/condense

Public URL:

- http://conciser.603apps.net

## Troubleshooting

### Server not responding

```bash
# Check if server is running
ssh conciser 'pgrep -f "server/app.py"'

# View recent logs
ssh conciser 'tail -50 nbj-condenser/server.log'

# Restart server
./deploy.sh
```

### Firewall issues

```bash
# Check firewall status
ssh conciser 'sudo firewall-cmd --list-all'

# Re-run firewall setup
ssh conciser 'bash -s' < setup-firewall.sh
```

### Disk space issues

```bash
# Check disk usage
ssh conciser 'df -h'

# Check project size
ssh conciser 'du -sh nbj-condenser/{temp,output,server/output}'

# Run cleanup manually
ssh conciser '/home/opc/nbj-condenser/scripts/cleanup.sh'
```

### Missing dependencies

```bash
# Re-run VM setup
ssh conciser 'bash -s' < setup-vm.sh
```

## File Structure on VM

```
/home/opc/
└── nbj-condenser/           # Git repo
    ├── venv/                # Python virtual environment
    ├── temp/                # Temporary processing files
    ├── output/              # CLI output files
    ├── server/
    │   ├── app.py
    │   └── output/          # Server output files
    ├── scripts/
    │   └── cleanup.sh       # Cron cleanup script
    ├── server.log           # Server logs
    ├── cleanup.log          # Cleanup logs
    └── .env                 # API keys (not in git)
```

## Scripts Summary

| Script               | Purpose                          | Run From       |
| -------------------- | -------------------------------- | -------------- |
| `setup-vm.sh`        | Initial VM setup (dependencies)  | Local          |
| `setup-firewall.sh`  | Configure firewall for port 5000 | Local          |
| `deploy.sh`          | Deploy code updates              | Local          |
| `deploy-env.sh`      | Copy .env to VM                  | Local          |
| `setup-cron.sh`      | Set up cleanup cron job          | Local          |
| `scripts/cleanup.sh` | Clean old files (runs via cron)  | VM (automatic) |

## Production Considerations

For production deployment, consider:

1. **Process Manager:** Use systemd or supervisord instead of nohup
2. **Reverse Proxy:** Use nginx or Apache in front of Flask
3. **HTTPS:** Set up SSL/TLS certificates
4. **Monitoring:** Add health checks and alerting
5. **Backups:** Backup `.env` and any persistent data
6. **Resource Limits:** Configure max concurrent jobs, timeouts
7. **Security:** Restrict port 5000 to specific IPs if needed

See `server/README.md` for production server setup guide (to be created).
