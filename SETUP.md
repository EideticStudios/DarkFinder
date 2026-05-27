# DarkFinder — Project Setup Guide

Step-by-step instructions for setting up the monorepo from scratch on a new machine.

## Prerequisites

- **Node.js** 20+ and npm (or pnpm/yarn — adjust commands accordingly)
- **Python** 3.12+
- **GDAL** system library (for rasterio)
- **Git**
- **uv** (optional but recommended for Python package management)

### Installing GDAL

GDAL is required by rasterio. Install the system library first:

```bash
# macOS (Homebrew)
brew install gdal

# Ubuntu/Debian
sudo apt-get install gdal-bin libgdal-dev

# Fedora
sudo dnf install gdal gdal-devel

# Verify
gdalinfo --version
```

## 1. Create the Monorepo

```bash
mkdir dark-finder
cd dark-finder
git init
```

## 2. Create the Directory Structure

```bash
# Root-level files
touch README.md LICENSE .gitignore

# Documentation
mkdir -p docs

# Frontend
mkdir -p frontend/src/{components,hooks,lib,styles}
mkdir -p frontend/public

# Backend
mkdir -p backend/app/{routers,services,pipeline}
mkdir -p backend/data/{raw,processed}
mkdir -p backend/tiles

# CI
mkdir -p .github/workflows
```

## 3. Set Up .gitignore

```bash
cat > .gitignore << 'EOF'
# Dependencies
node_modules/
frontend/node_modules/

# Build output
frontend/dist/
backend/__pycache__/
**/__pycache__/
*.pyc

# Python virtual environment
backend/.venv/
.venv/

# Data files (large, downloaded/generated)
backend/data/
backend/tiles/

# Environment variables
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
EOF
```

## 4. Set Up the Frontend

```bash
cd frontend

# Scaffold with Vite
npm create vite@latest . -- --template react-ts

# Install dependencies
npm install maplibre-gl react-map-gl

# Install dev dependencies
npm install -D @types/react @types/react-dom

# Verify it runs
npm run dev
# → Should open on http://localhost:5173
```

Press Ctrl+C to stop the dev server, then:

```bash
cd ..
```

## 5. Set Up the Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install \
  fastapi \
  "uvicorn[standard]" \
  rasterio \
  numpy \
  rio-tiler \
  click \
  requests \
  pyproj \
  pydantic

# Freeze dependencies
pip freeze > requirements.txt

# Create the FastAPI entry point
touch app/__init__.py
touch app/main.py
touch app/config.py
touch app/routers/__init__.py
touch app/services/__init__.py
touch app/pipeline/__init__.py
```

Create a minimal `app/main.py` to verify FastAPI works:

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="DarkFinder API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
```

Test it:

```bash
uvicorn app.main:app --reload
# → Should respond on http://localhost:8000/api/v1/health
```

```bash
cd ..
```

## 6. Set Up the Makefile

Create a root-level `Makefile` for common tasks:

```bash
cat > Makefile << 'EOF'
.PHONY: dev-frontend dev-backend dev install lint typecheck

# Development
dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

dev:
	@echo "Run 'make dev-frontend' and 'make dev-backend' in separate terminals"

# Setup
install:
	cd frontend && npm install
	cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt

# Quality
lint:
	cd frontend && npm run lint
	cd backend && .venv/bin/ruff check app/

typecheck:
	cd frontend && npx tsc --noEmit

# Data pipeline
download-data:
	cd backend && source .venv/bin/activate && python -m app.pipeline.download --year $(YEAR)

process-data:
	cd backend && source .venv/bin/activate && python -m app.pipeline.mosaic --year $(YEAR)
	cd backend && source .venv/bin/activate && python -m app.pipeline.colorize --year $(YEAR)
	cd backend && source .venv/bin/activate && python -m app.pipeline.generate_tiles --year $(YEAR)

pipeline: download-data process-data
EOF
```

## 7. Set Up GitHub Actions

```bash
cat > .github/workflows/ci.yml << 'EOF'
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npx tsc --noEmit
      - run: npm run lint

  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff mypy
      - run: pip install -r requirements.txt
      - run: ruff check app/
      - run: mypy app/ --ignore-missing-imports
EOF
```

## 8. Create the README

```bash
cat > README.md << 'EOF'
# DarkFinder 🌌

An open-source, ad-free light pollution map built with NASA VIIRS nighttime satellite data.

## Quick Start

### Prerequisites
- Node.js 20+
- Python 3.12+
- GDAL (`brew install gdal` / `apt install gdal-bin libgdal-dev`)

### Setup
```bash
# Clone
git clone https://github.com/YOUR_USERNAME/dark-finder.git
cd dark-finder

# Frontend
cd frontend && npm install && cd ..

# Backend
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cd ..
```

### Development
```bash
# Terminal 1: Frontend
cd frontend && npm run dev

# Terminal 2: Backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture overview.

## Data

Light pollution data comes from [NASA's VIIRS Black Marble](https://viirsland.gsfc.nasa.gov/Products/NASA/BlackMarble.html) annual composites, published by the [Earth Observation Group](https://eogdata.mines.edu/products/vnl/) at Colorado School of Mines. The data is public domain.

## License

MIT
EOF
```

## 9. Create the LICENSE

```bash
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2026 YOUR_NAME

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
```

## 10. Initial Commit

```bash
git add .
git commit -m "chore: initial project scaffold"
```

## 11. Push to GitHub

```bash
# Create the repo on GitHub first (via gh CLI or web UI)
gh repo create dark-finder --public --source=. --remote=origin --push

# Or manually:
git remote add origin https://github.com/YOUR_USERNAME/dark-finder.git
git branch -M main
git push -u origin main
```

## Running the Full Stack Locally

Once setup is complete, your development workflow is:

1. **Terminal 1** — Frontend dev server:
   ```bash
   cd frontend && npm run dev
   ```
   Open http://localhost:5173

2. **Terminal 2** — Backend API:
   ```bash
   cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
   ```
   API at http://localhost:8000, docs at http://localhost:8000/docs

3. **Data pipeline** (run once, or when adding a new year):
   ```bash
   cd backend && source .venv/bin/activate
   python -m app.pipeline.download --year 2023
   python -m app.pipeline.mosaic --year 2023
   python -m app.pipeline.colorize --year 2023
   python -m app.pipeline.generate_tiles --year 2023
   ```

## Folder Reference

```
dark-finder/
├── CLAUDE.md              ← Claude Code context file
├── README.md              ← Public-facing project README
├── LICENSE                ← MIT license
├── Makefile               ← Dev/pipeline task runner
├── .gitignore
├── .github/workflows/     ← CI configuration
├── docs/
│   ├── ARCHITECTURE.md    ← System design and tech decisions
│   ├── PLAN.md            ← Phased implementation plan
│   └── DATA_PIPELINE.md   ← VIIRS data processing reference
├── frontend/
│   ├── src/
│   │   ├── components/    ← React components (Map, Legend, etc.)
│   │   ├── hooks/         ← Custom hooks (useRadiance, etc.)
│   │   ├── lib/           ← Constants, types, utilities
│   │   └── styles/        ← Global CSS
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
└── backend/
    ├── app/
    │   ├── main.py        ← FastAPI entry point
    │   ├── config.py      ← Settings
    │   ├── routers/       ← API route handlers
    │   ├── services/      ← Business logic
    │   └── pipeline/      ← Data download/processing scripts
    ├── data/              ← Raw + processed GeoTIFFs (gitignored)
    ├── tiles/             ← Generated tile pyramid (gitignored)
    └── requirements.txt
```
