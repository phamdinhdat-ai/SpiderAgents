#!/bin/sh
# OpenSpider entrypoint.
# Substitute OPENSPIDER_PORT in supervisord template and start supervisord.
# Default port 8088; override at runtime with -e OPENSPIDER_PORT=3000.
set -e

# Auto-initialize if config.json is missing (bind mount with empty directory).
if [ ! -f "${OPENSPIDER_WORKING_DIR:-/app/working}/config.json" ]; then
  echo "⚠️  No config.json found in ${OPENSPIDER_WORKING_DIR}"
  echo "📦 Running initialization..."
  openspider init --defaults --accept-security
  echo "✅ Initialization complete!"
else
  echo "✓ Config found in ${OPENSPIDER_WORKING_DIR}, skipping initialization."
fi

export OPENSPIDER_PORT="${OPENSPIDER_PORT:-8088}"
envsubst '${OPENSPIDER_PORT}' \
  < /etc/supervisor/conf.d/supervisord.conf.template \
  > /etc/supervisor/conf.d/supervisord.conf
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
