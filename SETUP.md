# DarkFinder — Project Setup Guide

Step-by-step instructions for setting up the monorepo from scratch on a new machine.

## Prerequisites

- **Node.js** 20+ and npm (or pnpm/yarn — adjust commands accordingly)
- **Python** 3.12+
- **GDAL** system library (for rasterio)
- **Git**
- **uv** (optional but recommended for Python package management)
- **Google Earth Engine** account (free, for data downloads)

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

### GEE Authentication

The data pipeline downloads VIIRS nighttime lights from Google Earth Engine. Set up authentication once:

```bash
pip install earthengine-api
earthengine authenticate
```

This opens a browser for Google account authorization. No credentials in `.env` are needed.

## 1. Clone the Repo

```bash
git clone https://github.com/YOUR_USERNAME/dark-finder.git
cd dark-finder
```

## 2. Set Up the Frontend

```bash
cd frontend
npm install

# Verify it runs
npm run dev
# -> Should open on http://localhost:5173

cd ..
```

## 3. Set Up the Backend

```bash
cd backend

# Create virtual environment (using uv or venv)
uv venv .venv --python 3.12
uv pip install -r requirements.txt --python .venv/bin/python

# Or with standard venv:
# python -m venv .venv
# source .venv/bin/activate
# pip install -r requirements.txt

cd ..
```

Test the backend:

```bash
cd backend && ../.venv/bin/uvicorn app.main:app --reload
# -> Should respond on http://localhost:8000/api/v1/health
cd ..
```

## 4. Run the Data Pipeline

```bash
# Download VIIRS data from GEE (default: North America)
make download YEAR=2023

# Or with a custom bounding box
make download YEAR=2023 BBOX="-130,24,-60,50"

# Process into a Cloud-Optimized GeoTIFF
make process YEAR=2023

# Or do both in one step
make pipeline YEAR=2023

# Validate the downloaded data
make validate YEAR=2023
```

## 5. Makefile Targets

| Target     | Description                                    |
|------------|------------------------------------------------|
| `install`  | Install frontend npm deps + backend Python deps |
| `dev-frontend` | Start Vite dev server (port 5173)         |
| `dev-backend`  | Start FastAPI dev server (port 8000)      |
| `download` | Download VIIRS data from GEE for YEAR          |
| `process`  | Build COG from raw GeoTIFFs for YEAR           |
| `pipeline` | Download + process for YEAR                     |
| `validate` | Run data quality checks for YEAR                |
| `lint`     | Run linters (frontend + backend)                |
| `typecheck`| Run TypeScript type checking                    |

## Running the Full Stack Locally

Once setup is complete, your development workflow is:

1. **Terminal 1** — Frontend dev server:
   ```bash
   make dev-frontend
   ```
   Open http://localhost:5173

2. **Terminal 2** — Backend API:
   ```bash
   make dev-backend
   ```
   API at http://localhost:8000, docs at http://localhost:8000/docs

3. **Data pipeline** (run once, or when adding a new year):
   ```bash
   make pipeline YEAR=2023
   ```

## Folder Reference

```
dark-finder/
├── CLAUDE.md              <- Claude Code context file
├── README.md              <- Public-facing project README
├── LICENSE                <- MIT license
├── Makefile               <- Dev/pipeline task runner
├── .gitignore
├── .github/workflows/     <- CI configuration
├── docs/
│   ├── ARCHITECTURE.md    <- System design and tech decisions
│   ├── PLAN.md            <- Phased implementation plan
│   └── DATA_PIPELINE.md   <- VIIRS data processing reference
├── frontend/
│   ├── src/
│   │   ├── components/    <- React components (Map, Legend, etc.)
│   │   ├── hooks/         <- Custom hooks (useRadiance, etc.)
│   │   ├── lib/           <- Constants, types, utilities
│   │   └── styles/        <- Global CSS
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
└── backend/
    ├── app/
    │   ├── main.py        <- FastAPI entry point
    │   ├── config.py      <- Settings
    │   ├── routers/       <- API route handlers
    │   ├── services/      <- Business logic
    │   └── pipeline/      <- Data download/processing scripts
    ├── data/              <- Raw + processed GeoTIFFs (gitignored)
    ├── tiles/             <- Generated tile pyramid (gitignored)
    └── requirements.txt
```
