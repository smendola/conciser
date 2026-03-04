# Cloudflare Tunnel Setup for NBJ Condenser

This guide sets up `conciser.603apps.net` to reach your server on any machine running the NBJ Condenser Flask app.

## Benefits

- Custom domain with automatic HTTPS
- Works from anywhere (not just Tailscale network)
- Easy to move between physical servers
- Free for this use case

## One-Time Setup

### 1. Install cloudflared

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
sudo mv cloudflared /usr/local/bin/
sudo chmod +x /usr/local/bin/cloudflared
```

### 2. Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This opens a browser to authorize cloudflared with your Cloudflare account.

### 3. Create the tunnel

```bash
cloudflared tunnel create nbj-server
```

Note the tunnel ID from the output (e.g., `abc123def456`).

### 4. Configure the tunnel

List your files to find the credentials:
```bash
ls ~/.cloudflared/
```

You should see a `.json` file matching your tunnel ID.

Create `~/.cloudflared/config.yml`:
```yaml
tunnel: <your-tunnel-id>
credentials-file: /home/<your-username>/.cloudflared/<your-tunnel-id>.json

ingress:
  - hostname: conciser.603apps.net
    service: http://localhost:5000
  - service: http_status:404
```

Replace:
- `<your-tunnel-id>` with the ID from step 3
- `<your-username>` with your actual username

### 5. Add DNS record in Cloudflare

1. Go to Cloudflare Dashboard → DNS → Records for `603apps.net`
2. Add CNAME record:
   - **Type**: CNAME
   - **Name**: `conciser`
   - **Target**: `<your-tunnel-id>.cfargotunnel.com`
   - **Proxy status**: Proxied (orange cloud)
   - **TTL**: Auto

## Running the Tunnel

### Start the tunnel:
```bash
cloudflared tunnel run nbj-server
```

### Run as a service (recommended):

Install the service:
```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

Check status:
```bash
sudo systemctl status cloudflared
```

View logs:
```bash
sudo journalctl -u cloudflared -f
```

## Moving to a New Server

1. Install cloudflared on the new server (step 1)
2. Copy `~/.cloudflared/` directory from old server to new server
3. Run the tunnel (step "Running the Tunnel")

No DNS changes needed - the tunnel ID stays the same.

## Troubleshooting

**Check tunnel status:**
```bash
cloudflared tunnel list
cloudflared tunnel info nbj-server
```

**Test locally first:**
```bash
curl http://localhost:5000
```

**Check tunnel logs:**
```bash
cloudflared tunnel run nbj-server
# or if running as service:
sudo journalctl -u cloudflared -f
```

**Verify DNS:**
```bash
dig conciser.603apps.net
```

## Removing Old Tailscale Funnel Setup

If you were using Tailscale Funnel before:

```bash
tailscale serve reset
```

You can keep Tailscale running for other purposes, but the Funnel is no longer needed.
