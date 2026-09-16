# Production deployment

Aegis Quant is safe to deploy first in `TRADING_MODE=paper`. The service can run on a Windows host with the native MT5 terminal, or on Linux only when a tested `mt5linux` bridge is available. Do not expose the API or MT5 credentials directly to the public internet.

## 1. Prepare the host

Required:

- Python 3.11 or newer
- Node.js 20 or newer and npm
- MetaTrader 5 installed and logged in on Windows, or a configured `mt5linux` bridge on Linux
- systemd and Nginx for the Linux service template in this directory
- A dedicated, non-root OS user

Install the application as a dedicated user and keep the repository outside shared/home directories:

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin aegis
sudo install -d -o aegis -g aegis -m 0750 /opt/aegis-quant
sudo install -d -o aegis -g aegis -m 0750 /var/log/aegis-quant
sudo cp -a . /opt/aegis-quant
sudo chown -R aegis:aegis /opt/aegis-quant
```

Create the Python environment and build the frontend:

```bash
sudo -u aegis python3 -m venv /opt/aegis-quant/.venv
sudo -u aegis /opt/aegis-quant/.venv/bin/python -m pip install --upgrade pip
sudo -u aegis /opt/aegis-quant/.venv/bin/python -m pip install -r /opt/aegis-quant/server/requirements.txt
sudo -u aegis npm --prefix /opt/aegis-quant/client ci
sudo -u aegis npm --prefix /opt/aegis-quant/client run build
```

Run the test suite before installation when the host has the required dependencies:

```bash
sudo -u aegis /opt/aegis-quant/.venv/bin/python -m pytest -q /opt/aegis-quant/tests
```

## 2. Configure secrets

Copy `server/.env.example` to `/etc/aegis-quant.env`, set a unique `API_TOKEN`, set the OpenAI key, and configure the MT5 account for unattended startup:

```bash
sudo cp /opt/aegis-quant/server/.env.example /etc/aegis-quant.env
sudo chown root:aegis /etc/aegis-quant.env
sudo chmod 0640 /etc/aegis-quant.env
sudoedit /etc/aegis-quant.env
```

Minimum production values:

```dotenv
API_HOST=127.0.0.1
API_PORT=8000
CORS_ORIGINS=https://your-domain.example
API_TOKEN=<long-random-value>
TRADING_MODE=paper
OPENAI_API_KEY=<openai-key>
MT5_LOGIN=<demo-login>
MT5_PASSWORD=<demo-password>
MT5_SERVER=<broker-server>
MT5LINUX_ENABLED=0
LOG_LEVEL=INFO
MAX_CANDLE_AGE_SECONDS=7200
```

`MT5_LOGIN`, `MT5_PASSWORD`, and `MT5_SERVER` may be left empty only when an operator will enter them through Settings after startup. They are required for an unattended service.

Build the frontend against the public origin and the same API token:

```bash
sudo -u aegis VITE_API_BASE=https://your-domain.example \
  VITE_API_TOKEN='<same-api-token>' \
  npm --prefix /opt/aegis-quant/client run build
```

The API token is necessarily present in the browser bundle. Use TLS, restrict access to the deployment, and rotate the token if the bundle is ever distributed outside the intended users.

## 3. Install the service

Copy the systemd template and adjust the paths only if the installation root or user differs:

```bash
sudo cp /opt/aegis-quant/deploy/aegis-quant.service /etc/systemd/system/aegis-quant.service
sudo systemd-analyze verify /etc/systemd/system/aegis-quant.service
sudo systemctl daemon-reload
sudo systemctl enable --now aegis-quant
systemctl status aegis-quant
```

The service uses `Type=notify` and a 120-second watchdog. The application sends `READY=1`, `WATCHDOG=1`, and `STOPPING=1` notifications when run by systemd.

## 4. Put Nginx in front of the API

Copy `deploy/nginx.conf` to `/etc/nginx/sites-available/aegis-quant`, replace `CHANGE_ME` with the public hostname, and enable the site:

```bash
sudo cp /opt/aegis-quant/deploy/nginx.conf /etc/nginx/sites-available/aegis-quant
sudo sed -i 's/CHANGE_ME/your-domain.example/' /etc/nginx/sites-available/aegis-quant
sudo ln -s /etc/nginx/sites-available/aegis-quant /etc/nginx/sites-enabled/aegis-quant
sudo nginx -t
sudo systemctl reload nginx
```

Terminate TLS at Nginx or an upstream load balancer. The API remains bound to `127.0.0.1:8000` by default. `/metrics` is restricted to localhost by the template.

## 5. Verify the deployment

From the host:

```bash
curl --fail http://127.0.0.1:8000/healthz
curl --fail -H "X-API-Key: <api-token>" http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/metrics
```

From a browser or remote host:

```bash
curl --fail https://your-domain.example/
curl --fail https://your-domain.example/healthz
```

`/api/health` returns HTTP 503 when the MT5 terminal is disconnected, the configured symbols cannot be validated, or the newest closed H1 candle is older than `MAX_CANDLE_AGE_SECONDS`.

Inspect service and application logs:

```bash
journalctl -u aegis-quant -f
tail -f /opt/aegis-quant/server/trading_bot.log
```

## 6. Demo-account acceptance gate

Before enabling `TRADING_MODE=live`, run at least one full market-week on a dedicated demo account and verify:

- clean startup, restart, MT5 disconnect, and reconnect behavior;
- AI HOLD and rejected-proposal paths without process crashes;
- invalid stop, volume, margin, and symbol checks block `order_send`;
- daily-loss, peak-drawdown, max-trade, and correlation guards;
- OpenAI and news outages fail closed to HOLD;
- trailing-stop updates and `position_state.json` recovery after restart;
- broker history reconciles with the bot's position state.

Do not promote to funded capital if any check is missing or reconciliation differs.

## 7. Rollback and recovery

Stop the service without changing configuration:

```bash
sudo systemctl stop aegis-quant
```

Restore the previous frontend build or repository revision, then restart:

```bash
sudo systemctl restart aegis-quant
systemctl status aegis-quant
```

Rotate `API_TOKEN` and `OPENAI_API_KEY` on the organization's defined schedule. Never commit `.env`, `server/.env`, `client/.env`, logs, or `position_state.json`.
