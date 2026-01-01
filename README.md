# DevStack

Self-hosted development environment with Traefik reverse proxy, Tailscale VPN, and essential development services.

## Features

- Secure remote access via Tailscale VPN with HTTPS
- **Public API Gateway** - Expose APIs to the internet (isolated from VPN)
- Automated setup and configuration
- Full observability stack (Prometheus + Grafana)
- PostgreSQL and Redis databases
- Rate limiting and security headers for public APIs

## Services

| Service | Description | URL Path | Auth |
|---------|-------------|----------|------|
| Homepage | Service dashboard | `/` | Yes |
| Public API | Public API endpoints | `localhost:10000` | No |
| Internal API | Internal API endpoints | Internal only | - |
| Traefik | Reverse proxy with HTTPS | `/dashboard/` | Yes |
| Tailscale | VPN for secure remote access | - | - |
| Grafana | Metrics and logs visualization | `/grafana/` | Yes |
| Prometheus | Metrics collection | `/prometheus/` | Yes |
| Loki | Log aggregation | - | - |
| Promtail | Log collector | - | - |
| PostgreSQL | Relational database | `postgres:5432` | - |
| Redis | Cache and message broker | `redis:6379` | - |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Tailscale account
- `htpasswd` utility (apache2-utils package)

### Installation

1. Clone and run setup:
```bash
git clone <your-repo-url> devstack
cd devstack
./setup.sh
```

2. Configure `.env`:
```bash
# Tailscale auth key from https://login.tailscale.com/admin/settings/keys
TAILSCALE_AUTHKEY=tskey-auth-xxxxx
TAILSCALE_DOMAIN=your-machine.tail12345.ts.net

# Single sign-on authentication (htpasswd -nbB admin password | sed -e s/\\$/\\$\\$/g)
BASIC_AUTH_USERS=admin:$$2y$$05$$xxxxx

# Database passwords
POSTGRES_PASSWORD=your-password
REDIS_PASSWORD=your-password
CODE_SERVER_SUDO_PASSWORD=your-password
```

3. Get Tailscale certificates:
```bash
tailscale cert your-machine.tail12345.ts.net
cp your-machine.tail12345.ts.net.* certs/
```

4. Update `traefik-config.yml` with certificate paths:
```yaml
tls:
  certificates:
    - certFile: /certs/your-machine.tail12345.ts.net.crt
      keyFile: /certs/your-machine.tail12345.ts.net.key
```

5. Start services:
```bash
docker-compose up -d
```

Access services at `https://your-machine.tail12345.ts.net`

## Authentication

DevStack uses single sign-on via Traefik's basic auth. All services are configured to bypass their individual authentication and rely on Traefik's auth middleware.

**Single authentication point:**
- Configure `BASIC_AUTH_USERS` in `.env`
- Authenticate once at Traefik level
- Access all services without additional logins

**Services with disabled authentication:**
- Grafana: Anonymous access with Admin role

## Monitoring & Logging

### Metrics (Prometheus + Grafana)

Prometheus scrapes metrics from:
- **public-api** and **internal-api** - HTTP request metrics, Python runtime stats
- **traefik** - Reverse proxy requests, latency, connections
- **cadvisor** - Container CPU, memory, network
- **node-exporter** - Host system metrics

#### Prometheus Metrics Endpoints

Both API services expose Prometheus metrics internally:
```bash
# From within Docker network only (not exposed via Traefik)
http://public-api:80/metrics
http://internal-api:80/metrics
```

Example PromQL queries:
```promql
# API request rate
sum(rate(http_requests_total{job=~"public-api|internal-api"}[5m]))

# API latency P99
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job="public-api"}[5m])) by (le))

# Traefik request rate
rate(traefik_service_requests_total[5m])
```

### Grafana Dashboards

Pre-configured dashboards in `grafana/dashboards/`:

| Dashboard | Description |
|-----------|-------------|
| **API Performance** | Request rates, latency percentiles (P50/P90/P95/P99), error rates by API and handler |
| **System Overview** | Host CPU/memory/disk/network, container resource usage, top containers |
| **Application Health** | Service status, process metrics, Traefik connections, Python GC, Prometheus health |

All dashboards are version-controlled and automatically provisioned on startup.

### Logs (Loki + Grafana)

Loki aggregates logs from all services. Access via Grafana Explore:

```logql
# All container logs
{job="docker"}

# Specific container
{job="docker", container="postgres"}

# Search for errors
{job="docker"} |= "error"
```

## Management

### Common Commands

```bash
docker-compose logs -f [service]      # View logs
docker-compose restart [service]      # Restart service
docker-compose pull && docker-compose up -d  # Update services
docker-compose down                   # Stop all
docker-compose down -v                # Stop and remove data
```

### Access Logs

View all incoming connections and IPs:

```bash
# Real-time access log
tail -f logs/access.log

# View with jq for formatted output
tail -f logs/access.log | jq

# Filter by IP
grep "ClientAddr" logs/access.log | jq '.ClientAddr'

# Filter by service
grep "RouterName" logs/access.log | jq 'select(.RouterName | contains("grafana"))'

# View authentication attempts
grep "ClientUsername" logs/access.log | jq '{time: .time, ip: .ClientAddr, user: .ClientUsername, status: .DownstreamStatus}'
```

Log fields include:
- `ClientAddr` - Source IP and port
- `ClientUsername` - Authenticated username
- `RequestMethod` - HTTP method
- `RequestPath` - URL path
- `RouterName` - Which service was accessed
- `DownstreamStatus` - HTTP status code
- `Duration` - Request duration in nanoseconds

### Database Access

```bash
# PostgreSQL
docker exec -it postgres psql -U devuser -d devdb

# Redis
docker exec -it redis redis-cli -a your-password
```

## Data Persistence

Docker volumes:
- `postgres_data` - PostgreSQL databases
- `redis_data` - Redis data
- `grafana_data` - Grafana dashboards and settings
- `prometheus_data` - Metrics history
- `loki_data` - Log storage

### Backup

**Grafana dashboards and datasources:**
```bash
./export-grafana.sh
```

This creates:
- `grafana-export/datasources/` - All datasource configurations
- `grafana-export/dashboards/` - All dashboard JSON files
- `grafana-backup-TIMESTAMP.tar.gz` - Compressed archive

**Database volumes:**
```bash
docker run --rm -v devstack_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

**Restore Grafana:**
```bash
cp grafana-export/datasources/* grafana/datasources/
cp grafana-export/dashboards/* grafana/dashboards/
docker-compose restart grafana
```

## Security

- Change all default passwords in `.env`
- Use ephemeral Tailscale auth keys with expiration
- Configure Tailscale ACLs to restrict access
- Keep services updated regularly
- Enable Tailscale MFA
- Review Traefik access logs periodically

## Troubleshooting

### Services won't start
```bash
docker-compose logs
cat .env | grep -v "^#" | grep -v "^$"
sudo netstat -tulpn | grep -E ':(80|443|5432|6379)'
```

### Can't access services
```bash
# Verify Tailscale connection
tailscale status

# Check Traefik dashboard at https://your-domain/dashboard/

# Test certificate
openssl s_client -connect your-domain:443 -servername your-domain
```

### Homepage multiplexor
The homepage provides a multiplexor interface for managing multiple services. Services that support iframe embedding (Prometheus, Traefik) can be added to the grid. Services with CSP restrictions (Grafana) open in new tabs.

### Public API

The public API provides endpoints for system monitoring, caching, and visitor tracking.

#### Endpoints

- `/` - API information and available endpoints
- `/health` - Health check with Redis status
- `/example` - Example endpoint
- `/cache/{key}` - GET/POST for Redis caching
- `/visitors` - Active visitors and visit log
- `/ws/visitors` - WebSocket for real-time visitor updates
- `/system` - Container stats (CPU, memory)

#### Access

Via Tailscale VPN:
```bash
curl https://your-machine.tail12345.ts.net:10000/health
```

Via localhost:
```bash
curl http://localhost:10000/health
```

### Certificate errors
```bash
tailscale cert --force your-machine.tail12345.ts.net
cp your-machine.tail12345.ts.net.* certs/
docker-compose restart traefik
```

### Prometheus not collecting metrics
```bash
curl http://localhost:9090/api/v1/targets
docker exec traefik wget -qO- http://localhost:8080/metrics | head
```

## Customization

### Adding Services

Add to `docker-compose.yml` with Traefik labels:
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myservice.rule=Host(`${DOMAIN}`) && PathPrefix(`/myservice`)"
  - "traefik.http.routers.myservice.entrypoints=websecure"
  - "traefik.http.routers.myservice.tls=true"
```


