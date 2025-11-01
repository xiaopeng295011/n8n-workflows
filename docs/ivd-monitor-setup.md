# IVD Monitor Setup & Deployment Guide

This guide covers the deployment, configuration, and operational monitoring of the IVD (In Vitro Diagnostics) Monitor system, including the n8n workflow automation for daily digest delivery.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Deployment Options](#deployment-options)
  - [Bare Metal Deployment](#bare-metal-deployment)
  - [Docker Deployment](#docker-deployment)
- [n8n Workflow Configuration](#n8n-workflow-configuration)
- [Running the Pipeline](#running-the-pipeline)
- [Monitoring & Logging](#monitoring--logging)
- [Troubleshooting](#troubleshooting)

---

## Overview

The IVD Monitor system orchestrates:

1. **Data Collection**: Fetches regulatory and market intelligence from configured sources
2. **Enrichment**: Applies company matching and category classification
3. **Persistence**: Stores deduplicated records in SQLite database
4. **Digest Generation**: Produces HTML/plaintext email summaries
5. **Distribution**: Sends digests to stakeholders via email

The system can be run manually via CLI or automated through the included n8n workflow.

---

## Prerequisites

### Software Requirements

- **Python 3.9+** with pip
- **SQLite 3.35+** (for FTS5 support)
- **n8n** (optional, for workflow automation)
- **SMTP server** access for email delivery

### Python Dependencies

Install required packages:

```bash
pip install -r requirements.txt
```

Key dependencies:
- `jinja2` (email template rendering)
- `beautifulsoup4` (HTML parsing, if using web scrapers)
- Standard library: `sqlite3`, `argparse`, `logging`, `json`

---

## Environment Variables

The IVD Monitor system uses environment variables for configuration. Create a `.env.ivd` file in your project root or set these in your system environment:

### Core Configuration

```bash
# Database path (default: database/ivd_monitor.db)
IVD_DB_PATH=/path/to/ivd_monitor.db

# Python executable (default: python3)
PYTHON_EXECUTABLE=/usr/bin/python3

# Project root directory
IVD_PROJECT_DIR=/home/user/n8n-workflows

# Output directory for digest files
IVD_OUTPUT_DIR=/var/ivd_monitor/digests
```

### Email Configuration

```bash
# Digest email settings
IVD_DIGEST_SUBJECT_FORMAT="IVD Monitor Daily Digest - {date}"
IVD_DIGEST_INTRO_TEXT="Welcome to your daily IVD Monitor digest..."
IVD_DIGEST_RECIPIENTS="user1@example.com,user2@example.com"

# SMTP settings (used by n8n or custom email transport)
IVD_FROM_EMAIL="ivd-monitor@example.com"
IVD_SMTP_HOST="smtp.example.com"
IVD_SMTP_PORT=587
IVD_SMTP_USER="ivd-monitor@example.com"
IVD_SMTP_PASSWORD="your-secure-password"
IVD_SMTP_USE_TLS=true
```

### Error Notification

```bash
# Error notification recipients (defaults to IVD_DIGEST_RECIPIENTS)
IVD_ERROR_RECIPIENTS="ops-team@example.com"

# Slack integration (optional)
IVD_SLACK_CHANNEL="#ivd-alerts"
IVD_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### n8n-Specific Variables

These are used by the n8n workflow:

```bash
# n8n credential IDs (configure these in n8n UI)
IVD_SMTP_CREDENTIALS_ID="1"
IVD_SLACK_CREDENTIALS_ID="2"
```

---

## Database Setup

### Initialize the Database

Create the IVD monitor database schema:

```bash
python -m src.ivd_monitor.database --init
```

This creates `database/ivd_monitor.db` with:
- `records` table (deduplicated intelligence records)
- `records_fts` table (full-text search index)
- `ingestion_runs` table (audit log)

### Custom Database Path

Use a custom location:

```bash
python -m src.ivd_monitor.database --init --db-path /var/lib/ivd_monitor/data.db
```

Update `IVD_DB_PATH` environment variable accordingly.

---

## Deployment Options

### Bare Metal Deployment

#### 1. Clone and Setup

```bash
git clone <repository-url>
cd n8n-workflows
pip install -r requirements.txt
```

#### 2. Configure Environment

```bash
cp .env.ivd.example .env.ivd
# Edit .env.ivd with your settings
source .env.ivd
```

#### 3. Initialize Database

```bash
python -m src.ivd_monitor.database --init
```

#### 4. Test the Runner

```bash
python -m src.ivd_monitor.runner \
  --dry-run \
  --output /tmp/ivd_test \
  --formats html text \
  --verbose
```

#### 5. Setup Cron (Manual Alternative to n8n)

Add to crontab for daily execution:

```cron
# Run IVD monitor daily at 18:00
0 18 * * * cd /path/to/project && /usr/bin/python3 -m src.ivd_monitor.runner --output /var/ivd_monitor/digests --log-file /var/log/ivd_monitor/run.log
```

### Docker Deployment

#### 1. Create Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Initialize database
RUN python -m src.ivd_monitor.database --init --db-path /data/ivd_monitor.db

# Set environment
ENV IVD_DB_PATH=/data/ivd_monitor.db
ENV IVD_OUTPUT_DIR=/output

# Create volumes
VOLUME ["/data", "/output", "/config"]

# Run as non-root
RUN useradd -m -u 1000 ivduser && \
    chown -R ivduser:ivduser /app /data /output
USER ivduser

CMD ["python", "-m", "src.ivd_monitor.runner", "--output", "/output", "--formats", "html", "text", "csv"]
```

#### 2. Build and Run

```bash
# Build image
docker build -t ivd-monitor:latest .

# Run with volumes
docker run -d \
  --name ivd-monitor \
  -v ivd-data:/data \
  -v ivd-output:/output \
  -v $(pwd)/config:/config \
  --env-file .env.ivd \
  ivd-monitor:latest
```

#### 3. Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ivd-monitor:
    build: .
    container_name: ivd-monitor
    volumes:
      - ivd-data:/data
      - ivd-output:/output
      - ./config:/config:ro
    environment:
      - IVD_DB_PATH=/data/ivd_monitor.db
      - IVD_OUTPUT_DIR=/output
      - IVD_DIGEST_RECIPIENTS=${IVD_DIGEST_RECIPIENTS}
      - IVD_FROM_EMAIL=${IVD_FROM_EMAIL}
    env_file:
      - .env.ivd
    restart: unless-stopped

volumes:
  ivd-data:
  ivd-output:
```

Run with:

```bash
docker-compose up -d
```

---

## n8n Workflow Configuration

### 1. Import the Workflow

1. Open n8n UI (typically `http://localhost:5678`)
2. Navigate to **Workflows** → **Import from File**
3. Select `workflows/IVD/IVD_Daily_Digest.json`
4. Click **Import**

### 2. Configure Credentials

#### SMTP Credentials

1. Go to **Credentials** → **New**
2. Select **SMTP**
3. Fill in:
   - **Host**: `smtp.example.com`
   - **Port**: `587`
   - **User**: `ivd-monitor@example.com`
   - **Password**: Your SMTP password
   - **TLS**: Enabled
4. Click **Save**
5. Note the credential ID (e.g., `1`)

#### Slack Credentials (Optional)

1. Go to **Credentials** → **New**
2. Select **Slack API**
3. Fill in:
   - **Access Token**: Your Slack OAuth token
4. Click **Save**
5. Note the credential ID

### 3. Configure Environment Variables in n8n

In n8n settings or in the workflow itself, set:

```bash
IVD_PROJECT_DIR=/path/to/n8n-workflows
PYTHON_EXECUTABLE=/usr/bin/python3
IVD_OUTPUT_DIR=/tmp/ivd_digest
IVD_DIGEST_RECIPIENTS=team@example.com
IVD_ERROR_RECIPIENTS=ops@example.com
IVD_FROM_EMAIL=noreply@example.com
IVD_SMTP_CREDENTIALS_ID=1
IVD_SLACK_CHANNEL=#alerts
IVD_SLACK_CREDENTIALS_ID=2
```

### 4. Update Workflow Nodes

Review and update:

- **Daily Schedule 18:00**: Adjust trigger time if needed
- **Execute IVD Runner**: Verify command paths
- **Send Digest Email**: Check credential references
- **Send Slack Alert**: Enable/disable based on needs

### 5. Activate the Workflow

1. Click **Active** toggle in top-right
2. Monitor first execution in **Executions** tab

---

## Running the Pipeline

### Manual Execution

#### Basic Run

```bash
python -m src.ivd_monitor.runner --output /tmp/digest
```

#### Dry Run (No Database Writes)

```bash
python -m src.ivd_monitor.runner --dry-run --verbose
```

#### Specific Date

```bash
python -m src.ivd_monitor.runner --date 2024-01-15 --output /tmp/digest
```

#### Date Range

```bash
python -m src.ivd_monitor.runner \
  --date-range 2024-01-01 2024-01-07 \
  --output /tmp/digest \
  --formats html text csv
```

#### JSON Output

```bash
python -m src.ivd_monitor.runner --json
```

### Automated Execution (n8n)

The workflow automatically runs daily at 18:00 UTC. To manually trigger:

1. Open workflow in n8n
2. Click **Execute Workflow**
3. Monitor execution in real-time

---

## Monitoring & Logging

### Log Files

#### Runner Logs

Direct logs to a file:

```bash
python -m src.ivd_monitor.runner \
  --log-file /var/log/ivd_monitor/run.log \
  --verbose
```

#### Log Format

```
2024-01-15 18:00:01,123 - src.ivd_monitor.runner - INFO - Starting IVD monitor run for date: 2024-01-15
2024-01-15 18:00:02,456 - src.ivd_monitor.runner - INFO - Collecting data from sources...
2024-01-15 18:00:05,789 - src.ivd_monitor.runner - INFO - Collected 42 records from 3 sources
2024-01-15 18:00:10,012 - src.ivd_monitor.runner - INFO - Persisted: 35 inserted, 5 updated, 2 duplicates
2024-01-15 18:00:15,345 - src.ivd_monitor.runner - INFO - Digest written to /tmp/digest
2024-01-15 18:00:15,678 - src.ivd_monitor.runner - INFO - Run completed: 0 exit code
```

### Log Rotation

Use `logrotate` for automatic log management:

Create `/etc/logrotate.d/ivd-monitor`:

```
/var/log/ivd_monitor/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 ivduser ivduser
    sharedscripts
    postrotate
        systemctl reload ivd-monitor 2>/dev/null || true
    endscript
}
```

### Monitoring Metrics

The runner outputs a JSON summary with:

```json
{
  "run_id": 123,
  "started_at": "2024-01-15T18:00:00Z",
  "completed_at": "2024-01-15T18:00:15Z",
  "total_sources": 5,
  "successful_sources": 4,
  "failed_sources": ["unreliable_feed"],
  "total_records_collected": 42,
  "records_inserted": 35,
  "records_updated": 5,
  "records_duplicate": 2,
  "digest_generated": true,
  "digest_output_path": "/tmp/digest",
  "errors": [],
  "exit_code": 0
}
```

### Health Checks

#### Database Health

```bash
sqlite3 database/ivd_monitor.db "SELECT COUNT(*) FROM records;"
sqlite3 database/ivd_monitor.db "SELECT status, COUNT(*) FROM ingestion_runs GROUP BY status;"
```

#### Recent Runs

```bash
sqlite3 database/ivd_monitor.db \
  "SELECT started_at, status, total_records, new_records FROM ingestion_runs ORDER BY started_at DESC LIMIT 10;"
```

---

## Troubleshooting

### Common Issues

#### 1. Database Locked Error

**Symptom**: `database is locked` error during insertion

**Solution**: Ensure only one process accesses the database at a time. The database uses WAL mode for better concurrency.

```bash
# Check for stale locks
lsof database/ivd_monitor.db

# If needed, restart with exclusive lock
sqlite3 database/ivd_monitor.db "PRAGMA journal_mode=DELETE; PRAGMA journal_mode=WAL;"
```

#### 2. Missing Environment Variables

**Symptom**: Workflow fails with "undefined variable" error

**Solution**: Ensure all required environment variables are set in n8n:

```bash
# Test environment loading
python -c "import os; print(os.environ.get('IVD_DIGEST_RECIPIENTS'))"
```

#### 3. SMTP Authentication Failure

**Symptom**: Email sending fails with authentication error

**Solution**:
1. Verify SMTP credentials in n8n
2. Check firewall rules for SMTP port (usually 587 or 465)
3. Enable "less secure apps" if using Gmail (not recommended for production)
4. Use app-specific passwords for 2FA-enabled accounts

#### 4. Runner Exits with Code 2

**Symptom**: Some sources fail to collect data

**Solution**: Check logs for specific source errors:

```bash
python -m src.ivd_monitor.runner --verbose --log-file debug.log
grep "failed" debug.log
```

Partial failures don't stop the pipeline - the digest is generated with available data.

#### 5. No Records in Digest

**Symptom**: Digest email is empty or has no records

**Possible Causes**:
- No data collected (check collector config)
- Date mismatch (records published on different date)
- Database query issue

**Debug**:

```bash
# Check database for records on target date
sqlite3 database/ivd_monitor.db "SELECT COUNT(*) FROM records WHERE date(publish_date) = '2024-01-15';"

# Generate digest with verbose logging
python -m src.ivd_monitor.email_builder --date 2024-01-15 --format html --output debug.html
```

#### 6. File Permission Errors

**Symptom**: Cannot write to output directory

**Solution**:

```bash
# Ensure output directory exists and is writable
mkdir -p /var/ivd_monitor/digests
chown ivduser:ivduser /var/ivd_monitor/digests
chmod 755 /var/ivd_monitor/digests
```

### Debug Mode

Run with maximum verbosity:

```bash
python -m src.ivd_monitor.runner \
  --verbose \
  --dry-run \
  --log-file debug.log \
  --json > summary.json
```

Review `debug.log` for detailed execution traces and `summary.json` for structured output.

---

## Maintenance

### Regular Tasks

#### Weekly

- Review failed source alerts
- Check log file sizes
- Verify digest recipient list

#### Monthly

- Analyze ingestion metrics
- Update company matching rules
- Optimize database (VACUUM)

```bash
sqlite3 database/ivd_monitor.db "VACUUM;"
```

#### Quarterly

- Update Python dependencies
- Review and tune category classification rules
- Audit email delivery rates

### Backup Strategy

#### Database Backup

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR=/var/backups/ivd_monitor
DATE=$(date +%Y%m%d)

mkdir -p $BACKUP_DIR
sqlite3 database/ivd_monitor.db ".backup $BACKUP_DIR/ivd_monitor_$DATE.db"

# Compress
gzip $BACKUP_DIR/ivd_monitor_$DATE.db

# Retain last 30 days
find $BACKUP_DIR -name "*.db.gz" -mtime +30 -delete
```

#### Configuration Backup

Version control your configuration:

```bash
git add .env.ivd config/ workflows/IVD/
git commit -m "Backup IVD monitor configuration"
git push
```

---

## Support & Contributing

### Getting Help

- Check logs: `/var/log/ivd_monitor/`
- Review documentation: `docs/ivd_monitor.md`, `docs/ivd_company_matching.md`
- Run with `--verbose` for detailed output

### Extending the System

#### Adding New Data Sources

1. Create collector plugin in `src/ivd_monitor/collectors/`
2. Update `CollectorManager` to instantiate new collector type
3. Add source configuration to collector config JSON
4. Test with `--dry-run`

#### Customizing Enrichment

- Company matching: Edit `config/ivd_companies.json`
- Category rules: See `src/ivd_monitor/categorization.py`
- Custom classifier: Pass `custom_rules` to `CategoryClassifier()`

#### Email Template Customization

Templates are in `templates/ivd/`:
- `ivd_digest.html` - HTML email template
- `ivd_digest.txt` - Plaintext email template

Edit with Jinja2 syntax and test with:

```bash
python -m src.ivd_monitor.email_builder --date 2024-01-15 --format html --output preview.html
```

---

## Security Considerations

1. **Secrets Management**: Never commit credentials to version control
2. **File Permissions**: Restrict access to database and config files (0600)
3. **SMTP TLS**: Always use encrypted SMTP connections
4. **API Rate Limits**: Implement backoff for external data sources
5. **Input Validation**: Sanitize all scraped content before database insertion
6. **Log Sanitization**: Avoid logging sensitive data (URLs with tokens, credentials)

---

## Performance Tuning

### Database Optimization

```sql
-- Analyze query performance
EXPLAIN QUERY PLAN SELECT * FROM records WHERE date(publish_date) = '2024-01-15';

-- Rebuild FTS index if slow
INSERT INTO records_fts(records_fts) VALUES('rebuild');

-- Analyze for query planner
ANALYZE;
```

### Concurrent Execution

For high-volume deployments:

1. Shard by source (multiple databases)
2. Use connection pooling
3. Consider PostgreSQL migration for write-heavy workloads

---

## License & Credits

- IVD Monitor system: [Your License]
- n8n workflow platform: [Apache 2.0](https://github.com/n8n-io/n8n)
- Dependencies: See `requirements.txt` for individual licenses

---

For additional questions or issues, please open a GitHub issue or contact the maintainers.
