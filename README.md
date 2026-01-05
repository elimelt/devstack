# DevStack

Self-hosted development environment with Traefik reverse proxy, Tailscale VPN, and essential development services.

## Services

| Service | URL Path |
|---------|----------|
| Homepage | `/` |
| Public API | `localhost:10000` |
| Traefik | `/dashboard/` |
| Grafana | `/grafana/` |
| Prometheus | `/prometheus/` |
| PostgreSQL | `postgres:5432` |
| Redis | `redis:6379` |

## Quick Start

```bash
git clone <your-repo-url> devstack && cd devstack
./setup.sh
```

Configure `.env`:
```bash
TAILSCALE_AUTHKEY=tskey-auth-xxxxx
TAILSCALE_DOMAIN=your-machine.tail12345.ts.net
BASIC_AUTH_USERS=admin:$$2y$$05$$xxxxx
POSTGRES_PASSWORD=your-password
REDIS_PASSWORD=your-password
```

Get certificates and start:
```bash
tailscale cert your-machine.tail12345.ts.net
cp your-machine.tail12345.ts.net.* certs/
docker-compose up -d
```

## Commands

```bash
docker-compose logs -f [service]
docker-compose restart [service]
docker-compose down
docker exec -it postgres psql -U devuser -d devdb
docker exec -it redis redis-cli -a your-password
```

## Backup

```bash
./export-grafana.sh
docker run --rm -v devstack_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

## API Endpoints

- `/health` - Health check
- `/cache/{key}` - Redis caching
- `/visitors` - Active visitors
- `/ws/visitors` - WebSocket updates
- `/system` - Container stats

