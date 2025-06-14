# Home Assistant E-ink Data API

A Flask-based API server that fetches data from Home Assistant and provides it in a compact format suitable for e-ink displays. This project is designed to work with external services like TRMNL or custom e-ink devices that need periodic access to Home Assistant sensor data.

## 🤖 AI-Assisted Development

**This project was entirely coded using AI assistance with [aider.chat](https://aider.chat/) and Google Gemini 2.5 Flash + Claude Sonnet 4. Beware!** 

While functional, this code represents AI-generated solutions and may contain patterns or approaches that differ from traditional human-written code. Use at your own discretion and review thoroughly before production deployment.

## ⚠️ Security Warning

**This project is in active development and should NOT be directly exposed to the internet without proper security measures.**

Always use a reverse proxy (like Caddy, Nginx, or Nginx Proxy Manager) with:
- SSL/TLS termination
- Rate limiting
- Additional authentication layers if needed
- Proper firewall configuration

## 🚨 Important Disclaimer

**FORKS are highly encouraged**, but please note:

- **Limited Support**: Support and development from my side will be very limited
- **Personal Use Focus**: I do NOT see myself building this further than my own needs
- **Development Status**: This project is in active development
- **Security Limitations**: I'm no security expert and this might not be as secure as I think
- **My Security Setup**: I rely on Cloudflare WAF to protect me and monitor logs closely with highly restricted domain access

**Security enhancements and contributions are welcome!** If you find security issues or have improvements, please submit pull requests or open issues.

## Features

- 🔐 Bearer token authentication for API security
- 📊 Configurable Home Assistant sensor data fetching
- ⏰ Scheduled data polling with configurable intervals
- 🌍 Timezone-aware timestamp formatting
- 📱 Compact JSON output optimized for e-ink displays
- 🐳 Docker support for easy deployment
- 🔄 Automatic retry and error handling
- 📝 Comprehensive logging with configurable levels

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd ha-eink-api
```

### 2. Configure Environment

Copy the example environment file and customize it:

```bash
cp .env.example .env
```

### 3. Configure Sensors

Copy the example config file and customize it:

```bash
cp config.yaml.example config.yaml
```

Edit `.env` with your specific configuration:

```bash
# Home Assistant Configuration
HA_URL=http://192.168.1.100:8123
HA_TOKEN=your_long_lived_access_token_here

# API Security (REQUIRED)
API_BEARER_TOKEN=your_secure_api_token_here

# Optional Configuration
POLLING_INTERVAL_MINUTES=5
LOG_LEVEL=INFO
TIMEZONE=Europe/Berlin
TIME_FORMAT=%H:%M:%S
BASE_URL=ha-api-server.mydomain.tld
EINK_API_PATH=/eink-data
```

### 4. Generate Secure API Token

Generate a secure bearer token for API access:

```bash
# Generate a 32-byte hex token
openssl rand -hex 32
```

Copy the output and set it as your `API_BEARER_TOKEN` in the `.env` file.

Edit `config.yaml` to specify which Home Assistant sensors to fetch:

```yaml
# config.yaml
home_assistant_sensors:
  - entity_id: sensor.living_room_temperature
    fields:
      - state
      - attributes.unit_of_measurement
      - attributes.friendly_name
  - entity_id: sensor.washing_machine_time_remaining
    fields:
      - state
      - last_changed
  - entity_id: weather.home
    fields:
      - state
      - attributes.temperature
```

### 5. Deploy with Docker

```bash
# Build and run
docker-compose up -d

# Or build manually
docker build -t ha-eink-api .
docker run -d --name ha-eink-api -p 8234:8234 --env-file .env ha-eink-api
```

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HA_URL` | ✅ | - | Home Assistant URL (e.g., `http://192.168.1.100:8123`) |
| `HA_TOKEN` | ✅ | - | Home Assistant Long-Lived Access Token |
| `API_BEARER_TOKEN` | ✅ | - | Secure token for API authentication |
| `POLLING_INTERVAL_MINUTES` | ❌ | `5` | How often to fetch data from HA (minutes) |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `TIMEZONE` | ❌ | `UTC` | IANA timezone name (e.g., `Europe/Berlin`) |
| `TIME_FORMAT` | ❌ | `%H:%M:%S` | Python strftime format for timestamps |
| `BASE_URL` | ❌ | - | Domain for reverse proxy (e.g., `api.mydomain.com`) |
| `EINK_API_PATH` | ❌ | `/eink-data` | API endpoint path |

### Config.yaml Structure

The `config.yaml` file defines which Home Assistant entities to fetch and which fields to extract:

```yaml
home_assistant_sensors:
  - entity_id: sensor.example_sensor
    fields:
      - state                           # Current value
      - last_changed                    # Last update timestamp
      - attributes.unit_of_measurement  # Unit (°C, %, etc.)
      - attributes.friendly_name        # Display name
      - attributes.device_class         # Sensor type
```

#### Available Fields

- `state`: Current sensor value
- `last_changed`: ISO timestamp of last update
- `last_updated`: ISO timestamp of last state update
- `attributes.*`: Any attribute (e.g., `attributes.unit_of_measurement`)

#### Special Handling

- **Timestamp sensors**: Automatically converted to human-readable format (e.g., "02h 30m" for remaining time)
- **Friendly names**: Used as JSON keys, sanitized for compatibility
- **Multiple fields**: Automatically prefixed to avoid key conflicts

## API Usage

### Authentication

All API requests require a Bearer token in the Authorization header:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
     https://your-domain.com/eink-data
```

### Response Format

The API returns a compact JSON object optimized for e-ink displays:

```json
{
  "living_room_temperature": "22.5",
  "living_room_temperature_unit_of_measurement": "°C",
  "washing_machine_time_remaining": "01h 23m",
  "weather_home": "sunny",
  "last_updated": "14:30:25"
}
```

### Error Responses

```json
// Missing/invalid authentication
{
  "error": "Unauthorized: Missing Authorization header"
}

// Data not available
{
  "error": "Data not yet available or failed to fetch."
}
```

## Deployment with Reverse Proxy

### Caddy Example

**⚠️ Untested Configuration** - This configuration is provided as an example but has not been tested.

```caddyfile
ha-api.yourdomain.com {
    reverse_proxy localhost:8234
    
    # Optional: Rate limiting
    rate_limit {
        zone static_rl {
            key {remote_host}
            events 10
            window 1m
        }
    }
}
```

### Nginx Example

**⚠️ Untested Configuration** - This configuration is provided as an example but has not been tested.

```nginx
server {
    listen 443 ssl;
    server_name ha-api.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8234;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Rate limiting
        limit_req zone=api burst=10 nodelay;
    }
}
```

### Nginx Proxy Manager (Tested)

**✅ Tested Configuration** - I personally use Nginx Proxy Manager for this deployment.

1. Create a new proxy host in NPM
2. Set domain name (e.g., `ha-api.yourdomain.com`)
3. Forward to `localhost:8234` (or your server IP)
4. Enable SSL with Let's Encrypt
5. Optional: Add rate limiting in the Advanced tab

### Cloudflare WAF Protection

If you're using Cloudflare as your CDN/proxy, you can add additional protection with Web Application Firewall (WAF) rules. These examples are adapted from [Cloudflare protection strategies](https://ogitive.com/cloudflare-protection-of-wordpress/) and should be adjusted to your specific needs.

**⚠️ Important**: These rules are examples and may need modification for your specific use case. Test thoroughly before implementing in production.

#### Block Bad Bots

Create a firewall rule using the expression builder:

```
(http.user_agent contains "Yandex") or (http.user_agent contains "muckrack") or (http.user_agent contains "Qwantify") or (http.user_agent contains "Sogou") or (http.user_agent contains "BUbiNG") or (http.user_agent contains "knowledge") or (http.user_agent contains "CFNetwork") or (http.user_agent contains "Scrapy") or (http.user_agent contains "SemrushBot") or (http.user_agent contains "AhrefsBot") or (http.user_agent contains "Baiduspider") or (http.user_agent contains "python-requests") or (http.user_agent contains "crawl" and not cf.client.bot) or (http.user_agent contains "Crawl" and not cf.client.bot) or (http.user_agent contains "bot" and not http.user_agent contains "bingbot" and not http.user_agent contains "Google" and not http.user_agent contains "Twitter" and not cf.client.bot) or (http.user_agent contains "Bot" and not http.user_agent contains "Google" and not cf.client.bot) or (http.user_agent contains "Spider" and not cf.client.bot) or (http.user_agent contains "spider" and not cf.client.bot)
```

#### Geographic Restrictions (Example: Allow only specific country)

Restrict API access to specific countries (replace "US" with your country code):

```
ip.geoip.country ne "US"
```

#### Rate Limiting by Path

Add additional rate limiting for your API endpoint:

```
(http.request.uri.path eq "/eink-data")
```

**Note**: These rules should be thoroughly tested with your specific setup. Monitor your logs after implementation to ensure legitimate traffic isn't being blocked.

## Home Assistant Setup

### 1. Create Long-Lived Access Token

1. Go to Home Assistant → Profile → Security
2. Scroll down to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Give it a name (e.g., "E-ink API")
5. Copy the token and add it to your `.env` file

### 2. Verify Sensor Entity IDs

Find your sensor entity IDs in Home Assistant:

1. Go to Developer Tools → States
2. Search for your sensors
3. Copy the exact `entity_id` (e.g., `sensor.living_room_temperature`)
4. Add them to your `config.yaml`

## Troubleshooting

### Common Issues

**401 Unauthorized**
- Check your `API_BEARER_TOKEN` is correctly set
- Verify the Authorization header format: `Bearer YOUR_TOKEN`
- Ensure no extra spaces or characters in the token

**Empty Response (only last_updated)**
- Verify Home Assistant URL and token are correct
- Check that sensor entity IDs exist in Home Assistant
- Review logs with `LOG_LEVEL=DEBUG` for detailed error messages

**Connection Refused**
- Ensure Home Assistant is accessible from the API server
- Check firewall settings
- Verify HA_URL includes the correct protocol (http/https)

### Debug Mode

Enable detailed logging:

```bash
# In .env file
LOG_LEVEL=DEBUG
```

This will show:
- Token validation details
- Home Assistant API requests/responses
- Data processing steps
- Scheduling information

### Health Check

Test the API endpoint:

```bash
# Replace with your actual token and URL
curl -H "Authorization: Bearer your_token_here" \
     http://localhost:8234/eink-data
```

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python app.py
```

### Docker Development

```bash
# Build development image
docker build -t ha-eink-api:dev .

# Run with volume mount for live editing
docker run -p 8234:8234 --env-file .env \
           -v $(pwd):/app ha-eink-api:dev
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

[Add your license information here]

## Support

For issues and questions:
- Check the troubleshooting section above
- Review logs with DEBUG level enabled
- Open an issue on GitHub with relevant log output

---

**Remember**: This API provides access to your Home Assistant data. Always use proper security measures when deploying to production environments.
