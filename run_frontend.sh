#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/frontend"

if [ ! -f ".env.local" ]; then
  cp .env.local.example .env.local
fi

npm install
npm run dev
