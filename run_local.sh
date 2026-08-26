#!/bin/bash
# SmartStock AI - Local Dev Setup
# Run this once to get going

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SmartStock AI — Local Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Create .env if missing
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✓ Created .env from .env.example"
  echo "  → Edit DATABASE_URL and SECRET_KEY before running"
fi

# 2. Python virtual environment
if [ ! -d "venv" ]; then
  python3 -m venv venv
  echo "✓ Virtual environment created"
fi

source venv/bin/activate
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# 3. Run
echo ""
echo "Starting server at http://localhost:8000"
echo "API docs at      http://localhost:8000/docs"
echo ""
uvicorn main:app --reload --host 0.0.0.0 --port 8000
