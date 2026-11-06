#!/bin/sh
set -eu
export CHROME_VERSION_MAIN="$(chromium --version | sed -E 's/[^0-9]*([0-9]+).*/\1/')"
exec "$@"
