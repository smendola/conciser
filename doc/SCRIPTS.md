# NBJ Condenser - Deployment Scripts Guide

This document explains all deployment and setup scripts.

## 🚀 Quick Start

**For a brand new VM:**

```bash
./setup-new-vm.sh
```

**For updates to existing VM:**

```bash
./deploy.sh
```

## 📋 Script Reference

### Infrastructure / One-Time Setup

#### `terraform-vm.sh`

**Purpose:** Install all system-level dependencies on the VM\
**Run from:** Local machine\
**Frequency:** Once per new VM\
**What it does:**

- Updates system packages (yum update)
- Installs EPEL repository
- Installs Python 3 + development tools
- Installs Git
- Installs ffmpeg and media tools
- Installs system utilities (wget, curl, cronie, firewalld)
- Enables firewalld and crond services
- Installs yt-dlp globally

**Usage:**

```bash
ssh conciser 'bash -s' < terraform-vm.sh
```

**Time:** ~3-5 minutes

---

#### `setup-new-vm.sh`

**Purpose:** Orchestrate complete VM setup in one command\
**Run from:** Local machine\
**Frequency:** Once per new VM\
**What it does:**

1. Checks SSH connectivity
2. Runs `terraform-vm.sh` (installs dependencies)
3. Runs `deploy.sh` (deploys code)
4. Runs `deploy-env.sh` (copies .env)
5. Runs `setup-firewall.sh` (configures firewall)
6. Runs `setup-cron.sh` (sets up cleanup job)

**Usage:**

```bash
./setup-new-vm.sh          # Uses 'conciser' host
./setup-new-vm.sh myhost   # Use custom SSH host
```

**Time:** ~5-10 minutes

---

#### `setup-firewall.sh`

**Purpose:** Configure VM firewall to allow port 5000\
**Run from:** Local machine\
**Frequency:** Once per new VM\
**What it does:**

- Starts and enables firewalld
- Opens port 5000/tcp
- Verifies the rule was added
- Displays Oracle Cloud Security List instructions

**Usage:**

```bash
ssh conciser 'bash -s' < setup-firewall.sh
```

**Important:** You must ALSO configure Oracle Cloud Security List!

---

#### `setup-cron.sh`

**Purpose:** Set up daily cleanup cron job\
**Run from:** Local machine\
**Frequency:** Once per new VM\
**What it does:**

- Makes `scripts/cleanup.sh` executable
- Adds cron job to run daily at 3 AM
- Shows current crontab

**Usage:**

```bash
ssh conciser 'bash -s' < setup-cron.sh
```

---

### Application Deployment

#### `deploy.sh`

**Purpose:** Deploy code updates to the VM\
**Run from:** Local machine\
**Frequency:** Every time you make code changes\
**What it does:**

1. Commits local changes to git
2. Pushes to GitHub
3. SSHs to VM
4. Pulls latest code from GitHub
5. Creates/updates Python venv
6. Installs dependencies (`pip install -e .`)
7. Restarts Flask server

**Usage:**

```bash
./deploy.sh
```

**Time:** ~1-2 minutes

---

#### `deploy-env.sh`

**Purpose:** Copy .env file to VM\
**Run from:** Local machine\
**Frequency:** Once per new VM, or when .env changes\
**What it does:**

- Copies `.env` file via SCP to the VM

**Usage:**

```bash
./deploy-env.sh
```

**Security:** Never commit `.env` to git!

---

### Maintenance

#### `scripts/cleanup.sh`

**Purpose:** Clean up old temp and output files\
**Run from:** VM (automatically via cron)\
**Frequency:** Daily at 3 AM (via cron)\
**What it does:**

- Deletes files from `temp/` older than 7 days
- Deletes files from `output/` older than 7 days
- Deletes log files older than 30 days
- Removes empty directories

**Manual usage:**

```bash
ssh conciser '/home/opc/nbj-condenser/scripts/cleanup.sh'
```

---

## 📁 File Locations on VM

After setup, the VM will have:

```
/home/opc/
└── nbj-condenser/              # Git repo
    ├── .env                    # API keys (copied via deploy-env.sh)
    ├── venv/                   # Python virtual environment
    ├── temp/                   # Temporary processing files
    ├── output/                 # All output files (CLI and server)
    ├── server/
    │   └── app.py             # Flask server
    ├── scripts/
    │   └── cleanup.sh         # Cleanup script (runs via cron)
    ├── server.log             # Server logs
    └── cleanup.log            # Cleanup logs
```

---

## 🔄 Typical Workflow

### First Time Setup

```bash
./setup-new-vm.sh
# Wait 5-10 minutes
# Manually configure Oracle Cloud Security List
# Test: curl http://129.80.134.46:5000/health
```

### Daily Development

```bash
# Make code changes
./deploy.sh
# Wait 1-2 minutes
# Server automatically restarts
```

### Updating Environment Variables

```bash
# Edit .env locally
./deploy-env.sh
./deploy.sh  # Restart server to pick up changes
```

---

## 🐛 Troubleshooting Scripts

### SSH connection fails

```bash
# Test SSH connection
ssh conciser 'echo "SSH OK"'

# Check SSH config
cat ~/.ssh/config | grep -A5 conciser
```

### terraform-vm.sh fails

```bash
# Check internet connectivity on VM
ssh conciser 'ping -c 3 google.com'

# Check available disk space
ssh conciser 'df -h'

# Run with verbose output
ssh conciser 'bash -x -s' < terraform-vm.sh
```

### deploy.sh fails

```bash
# Check git status
ssh conciser 'cd nbj-condenser && git status'

# Check Python venv
ssh conciser 'ls -la nbj-condenser/venv'

# View full server logs
ssh conciser 'cat nbj-condenser/server.log'
```

### Firewall issues

```bash
# Check firewalld status
ssh conciser 'sudo systemctl status firewalld'

# List open ports
ssh conciser 'sudo firewall-cmd --list-ports'

# Check if server is listening
ssh conciser 'netstat -tlnp | grep 5000'
```

---

## 📊 Script Dependencies

```
setup-new-vm.sh
    ├─→ terraform-vm.sh      (installs system deps)
    ├─→ deploy.sh            (deploys code)
    │   └─→ GitHub repo
    ├─→ deploy-env.sh        (copies .env)
    │   └─→ .env file
    ├─→ setup-firewall.sh    (firewall config)
    └─→ setup-cron.sh        (cron job)
        └─→ scripts/cleanup.sh
```

---

## ⚙️ Configuration

All scripts use these defaults:

- **Remote user:** `opc`
- **Remote host:** `conciser` (can be changed in SSH config)
- **Remote directory:** `/home/opc/nbj-condenser`
- **Server port:** `5000`
- **Cleanup age:** 7 days (temp/output), 30 days (logs)
- **Cron schedule:** Daily at 3 AM

To customize, edit the respective script files.
