# DevStack Quick Reference

## Commands

### Setup
```bash
./setup.sh                          # Initial setup
docker-compose up -d                # Start services
docker-compose down                 # Stop services
docker-compose restart [service]    # Restart service
docker-compose logs -f [service]    # View logs
docker-compose pull && docker-compose up -d  # Update
docker-compose down -v              # Remove all data
```

### Access Logs
```bash
tail -f logs/access.log             # Real-time access log
tail -f logs/access.log | jq        # Formatted JSON output
grep "ClientAddr" logs/access.log | jq '.ClientAddr'  # View IPs
grep "ClientUsername" logs/access.log | jq  # View auth attempts
```

## Configuration

Authentication via Traefik basic auth (single sign-on):
- `BASIC_AUTH_USERS` - Only authentication required

Database passwords:
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `CODE_SERVER_SUDO_PASSWORD`

## Service URLs

Base URL: `https://your-domain.tail12345.ts.net`

| Service | Path | Auth |
|---------|------|------|
| Homepage | `/` | Basic Auth |
| Code Server | `/code/` | Basic Auth |
| JupyterLab | `/jupyter/` | Basic Auth |
| Grafana | `/grafana/` | Basic Auth |
| Prometheus | `/prometheus/` | Basic Auth |
| Portainer | `/portainer/` | Basic Auth |
| Traefik | `/dashboard/` | Basic Auth |

## Database Access

### PostgreSQL
```bash
docker exec -it postgres psql -U devuser -d devdb
# Connection: postgresql://devuser:password@postgres:5432/devdb
```

### Redis
```bash
docker exec -it redis redis-cli -a your-password
# Connection: redis://:password@redis:6379
```

## Prometheus Queries

```promql
# Request rate
rate(traefik_service_requests_total[5m])

# Container CPU
rate(container_cpu_usage_seconds_total[5m])

# Container memory
container_memory_usage_bytes

# HTTP status codes
sum by (code) (rate(traefik_entrypoint_requests_total[5m]))

# 95th percentile latency
histogram_quantile(0.95, rate(traefik_service_request_duration_seconds_bucket[5m]))
```

## Loki Queries

```logql
# Traefik access logs
{job="traefik"}

# Filter by service
{job="traefik", router_name=~"grafana.*"}

# Errors only
{job="traefik"} | json | status >= 400

# Container logs
{job="docker", container="postgres"}

# Search logs
{job="docker"} |= "error"
```

## Common Tasks

### Generate Basic Auth
```bash
htpasswd -nbB admin yourpassword | sed -e s/\\$/\\$\\$/g
```

### Certificates
```bash
tailscale cert your-machine.tail12345.ts.net
cp your-machine.tail12345.ts.net.* certs/
```

### Backups
```bash
# Grafana (dashboards and datasources)
./export-grafana.sh

# PostgreSQL
docker exec postgres pg_dump -U devuser devdb > backup.sql
cat backup.sql | docker exec -i postgres psql -U devuser -d devdb

# Docker volume
docker run --rm -v devstack_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

## Troubleshooting

```bash
# Service health
docker-compose ps
docker-compose logs [service]

# Tailscale
tailscale status
tailscale ping your-machine

# Certificates
openssl x509 -in certs/your-cert.crt -text -noout

# Port conflicts
sudo netstat -tulpn | grep -E ':(80|443|5432|6379)'

# Reset
docker-compose down -v
rm -rf tailscale/state/*
./setup.sh
```

## Security Checklist

- [ ] Changed all default passwords
- [ ] Using ephemeral Tailscale auth key
- [ ] Configured Tailscale ACLs
- [ ] Enabled Tailscale MFA
- [ ] Certificates not in git
- [ ] .env not in git
- [ ] Regular backups configured
- [ ] Services up to date

