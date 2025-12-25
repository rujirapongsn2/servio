# Security Implementation Guide

## Overview

This document describes the security measures implemented in the Voice Agents SDK application to protect against unauthorized access and attacks.

## 1. WebSocket API Key Authentication (`/ws`)

### How It Works

The main WebSocket endpoint `/ws` now requires API key authentication to prevent unauthorized access.

- **API keys** are managed through the admin panel
- Keys are generated securely using `secrets.token_urlsafe(32)`
- Each key can be:
  - Named for easy identification
  - Activated/deactivated
  - Set to expire after a certain date
  - Tracked for usage statistics

### Creating an API Key

**Admin Endpoint**: `POST /api/admin/api-keys`

```bash
curl -X POST "https://your-domain.com/api/admin/api-keys" \
  -H "Authorization: Bearer YOUR_ADMIN_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Widget Production Key",
    "expires_days": 365
  }'
```

**Response**:
```json
{
  "message": "API key created successfully. Key: sk_xxxxxxxxxxxxx (Save this key securely - it won't be shown again!)"
}
```

**Important**: Save the API key immediately - it cannot be retrieved later!

### Using the API Key

Connect to WebSocket with the API key as a query parameter:

```javascript
const apiKey = "sk_xxxxxxxxxxxxx";  // From admin panel
const ws = new WebSocket(`wss://your-domain.com/ws?api_key=${apiKey}`);
```

### Managing API Keys

#### List All Keys
```bash
GET /api/admin/api-keys
Authorization: Bearer YOUR_ADMIN_JWT_TOKEN
```

#### Get Specific Key
```bash
GET /api/admin/api-keys/{key_id}
Authorization: Bearer YOUR_ADMIN_JWT_TOKEN
```

#### Update Key (Activate/Deactivate)
```bash
PUT /api/admin/api-keys/{key_id}
Authorization: Bearer YOUR_ADMIN_JWT_TOKEN
Content-Type: application/json

{
  "is_active": false
}
```

#### Delete Key
```bash
DELETE /api/admin/api-keys/{key_id}
Authorization: Bearer YOUR_ADMIN_JWT_TOKEN
```

### Error Responses

**Missing API Key**:
```json
{
  "type": "error",
  "message": "API key is required"
}
```

**Invalid or Expired Key**:
```json
{
  "type": "error",
  "message": "Invalid or expired API key"
}
```

## 2. Twilio Webhook Security

### `/incoming-call` Endpoint

This endpoint now validates Twilio request signatures to prevent spoofing attacks.

**How it works**:
1. Twilio sends requests with an `X-Twilio-Signature` header
2. Server validates the signature using the Twilio Auth Token
3. Only requests with valid signatures are processed

**Configuration**:
- Configure Twilio Auth Token in the VoIP Provider settings (Admin Panel)
- If auth_token is not configured, signature validation is skipped (development mode)

### `/ws/twilio-stream` WebSocket

This endpoint receives audio streams from Twilio phone calls.

**Security Considerations**:
- This endpoint is designed for Twilio's use and should not be publicly accessible
- Consider implementing IP whitelisting for Twilio's IP ranges in production
- Use environment variables to control access

## 3. Database Schema Changes

New table `api_keys`:
```sql
CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    key VARCHAR(255) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_api_keys_key ON api_keys(key);
```

## 4. Best Practices

### For Production Deployment

1. **API Keys**:
   - Set expiration dates for all API keys
   - Rotate keys regularly (e.g., every 90 days)
   - Disable unused keys immediately
   - Monitor usage_count for anomalies

2. **Twilio**:
   - Always configure Auth Token for signature validation
   - Use HTTPS for all webhook URLs
   - Verify Twilio IP addresses if possible

3. **Admin Access**:
   - Use strong JWT secrets (set `JWT_SECRET_KEY` in environment)
   - Set appropriate token expiration times
   - Use HTTPS for admin panel access

4. **Environment Variables**:
   ```bash
   # Required
   OPENAI_API_KEY=sk-...
   JWT_SECRET_KEY=your-secure-random-string

   # Optional but recommended
   ALLOWED_ORIGINS=https://your-frontend-domain.com
   DATABASE_URL=postgresql://...
   ```

### For Development

1. **Testing API Keys**:
   ```bash
   # Create a test key
   curl -X POST "http://localhost:8000/api/admin/api-keys" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Development Test Key"}'
   ```

2. **Skip Twilio Validation** (local testing):
   - Leave `auth_token` empty in VoIP Provider config
   - Signature validation will be skipped

## 5. Migration Guide

### Updating Existing Deployments

1. **Pull latest code**:
   ```bash
   git pull origin main
   ```

2. **Database Migration** (automatic on startup):
   - The `api_keys` table will be created automatically
   - No manual migration needed

3. **Create First API Key**:
   - Login to admin panel
   - Navigate to API Keys section (or use API endpoint)
   - Create an API key for your widget

4. **Update Frontend/Widget**:
   ```javascript
   // Old (insecure)
   const ws = new WebSocket('wss://domain.com/ws');

   // New (secure)
   const API_KEY = 'sk_xxxxx'; // From config or environment
   const ws = new WebSocket(`wss://domain.com/ws?api_key=${API_KEY}`);
   ```

5. **Test Connection**:
   - Verify WebSocket connects successfully with API key
   - Check admin panel for usage statistics

## 6. Monitoring

### Usage Tracking

API key usage is automatically tracked:
- `usage_count`: Total number of connections
- `last_used_at`: Timestamp of last use

### Checking Logs

Monitor for failed authentication attempts:
```bash
# Check server logs for unauthorized access attempts
docker logs voice-agent-backend | grep "Invalid or expired API key"
```

## 7. Security Checklist

- [ ] JWT_SECRET_KEY is set to a strong random value
- [ ] All API keys have expiration dates set
- [ ] Twilio Auth Token is configured for production
- [ ] ALLOWED_ORIGINS is set to specific domains (not "*")
- [ ] HTTPS is enabled for all endpoints
- [ ] Old/unused API keys are disabled
- [ ] WebSocket connections are monitored for anomalies
- [ ] Regular security audits are scheduled

## 8. Support

For security issues or questions:
1. Check this documentation first
2. Review server logs for error details
3. Contact your system administrator
4. Report security vulnerabilities privately to your security team

---

**Last Updated**: 2025-12-24
**Version**: 1.0
