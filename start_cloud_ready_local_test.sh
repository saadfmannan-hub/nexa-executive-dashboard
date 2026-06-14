#!/bin/sh
cd "$(dirname "$0")"
DAS_CLOUD_MODE=0 DAS_DEMO_MODE=1 DAS_DB_PATH="$PWD/cloud_demo_test.db" python3 server.py
