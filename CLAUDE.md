# DarkFinder — Light Pollution Map

## Project Overview

DarkFinder is an interactive light pollution map built with a React (TypeScript) frontend and a Python (FastAPI) backend. It visualizes NASA VIIRS nighttime satellite data as a heat map overlay on a dark base map, allowing users to explore light pollution levels worldwide.

The project is structured as a monorepo with two packages: `frontend/` and `backend/`.

## Architecture

```
dark-finder/
├── frontend/          # React + TypeScript + Vite
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── hooks/         # Custom React hooks
│   │   ├── lib/           # Utilities, constants, types
│   │   └── styles/        # Global styles
│   ├── public/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── backend/           # Python FastAPI
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py        # FastAPI app entry
│   │   ├── routers/       # API route modules
│   │   ├── services/      # Business logic (tile serving, radiance queries)
│   │   ├── pipeline/      # Data processing scripts
│   │   └── config.py      # Settings and constants
│   ├── data/              # Downloaded/processed geospatial data (gitignored)
│   ├── tiles/             # Generated tile pyramids (gitignored)
│   ├── pyproject.toml
│   └── requirements.txt
├── docs/              # Planning and architecture docs
├── .github/
│   └── workflows/     # CI (lint, typecheck, test)
├── CLAUDE.md          # This file
├── README.md
├── .gitignore
└── LICENSE
```

## Tech Stack

### Frontend
- **Framework:** React 19 + TypeScript
- **Build:** Vite
- **Map library:** MapLibre GL JS (open-source, no API key required)
- **Base map:** Carto Dark Matter (free, no key) or MapTiler free tier
- **Styling:** CSS Modules or vanilla-extract (developer preference)
- **No component library.** Custom components only.

### Backend
- **Framework:** FastAPI (Python 3.12+)
- **Geospatial:** rasterio, numpy, pyproj
- **Tile serving:** rio-tiler (on-the-fly COG rendering)
- **Data format:** GeoTIFF (VIIRS VNL V2.2 annual composites via GEE)
- **Task runner:** Make (for pipeline commands)

### Data Source
- **VIIRS VNL V2.2** annual composites from EOG (Colorado School of Mines) via Google Earth Engine
- GEE collection: `NOAA/VIIRS/DNB/ANNUAL_V22`
- Band: `average_masked`
- Format: GeoTIFF, 15 arc-second resolution, EPSG:4326, public domain
- Coverage: 2014-2023
- Authentication: `earthengine authenticate` (one-time, no .env credentials needed)

## Key Conventions

### Code Style
- TypeScript: strict mode, no `any` types
- Python: type hints everywhere, ruff for linting, black for formatting
- Prefer explicit over clever
- Components are function components with hooks, no class components
- One component per file, file name matches component name

### Naming
- React components: PascalCase (`MapOverlay.tsx`)
- Hooks: camelCase with `use` prefix (`useRadianceQuery.ts`)
- Python modules: snake_case (`tile_server.py`)
- API routes: kebab-case (`/api/v1/radiance-query`)
- CSS classes: camelCase via CSS Modules, or kebab-case in vanilla CSS

### API Design
- All API routes prefixed with `/api/v1/`
- Tile endpoint: `GET /api/v1/tiles/{layer}/{z}/{x}/{y}.png` (`layer` is `emission` or `skyglow`)
- Radiance query: `GET /api/v1/radiance?lat={lat}&lng={lng}`
- Available layers: `GET /api/v1/layers` (which COGs are present, for frontend bootstrap)
- Health check: `GET /api/v1/health`
- CORS enabled for local dev (frontend on :5173, backend on :8000)
- The serving layer is single-year: it auto-discovers the newest processed COG. Year is only a pipeline/build concept.

### Git
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `pipeline:`
- Branch naming: `feat/description`, `fix/description`, `pipeline/description`
- Keep commits atomic — one logical change per commit

## Color Ramp (Radiance -> Visual)

The heat map color ramp maps VIIRS radiance values (nW/cm2/sr) to colors inspired by the Bortle scale:

| Radiance Range     | Color          | Bortle Class | Description           |
|--------------------|----------------|-------------|-----------------------|
| 0.0 - 0.2         | `#000011`      | 1           | Pristine dark sky     |
| 0.2 - 0.4         | `#000033`      | 2           | Typical dark site     |
| 0.4 - 1.0         | `#003366`      | 3           | Rural sky             |
| 1.0 - 3.0         | `#006633`      | 4           | Rural/suburban        |
| 3.0 - 6.0         | `#339900`      | 5           | Suburban sky          |
| 6.0 - 12.0        | `#CCCC00`      | 6           | Bright suburban       |
| 12.0 - 30.0       | `#FF6600`      | 7           | Suburban/urban        |
| 30.0 - 60.0       | `#CC0000`      | 8           | City sky              |
| 60.0+             | `#FFFFFF`      | 9           | Inner-city sky        |

These thresholds are approximate. The exact mapping should be refined against reference SQM measurements. The color ramp is defined once in the backend pipeline and once as a legend constant in the frontend.

## Development Workflow

### Data Pipeline
Download VIIRS data from GEE, process into a COG, serve tiles on-the-fly from FastAPI.

```bash
# One-time GEE auth
earthengine authenticate

# Download + process (YEAR is optional, defaults to 2023)
make pipeline
make pipeline YEAR=2022   # target a different year

# Or step by step:
make download YEAR=2023
make process YEAR=2023
```

### Running the App
```bash
# Terminal 1: Frontend
make dev-frontend

# Terminal 2: Backend
make dev-backend
```

## Important Notes for Claude Code

- When working on the frontend, `cd frontend` first. The Vite dev server runs from there.
- When working on the backend, `cd backend` first. The FastAPI server runs from there.
- Never commit anything in `backend/data/` or `backend/tiles/` — these are gitignored and can be multiple GB.
- The VIIRS GeoTIFFs are large (hundreds of MB to several GB). Pipeline scripts should be resumable.
- MapLibre GL JS uses `maplibre-gl` on npm, not `mapbox-gl`. They are API-compatible but the package name matters.
- The Carto Dark Matter basemap uses split tiles so labels render above the VIIRS overlay: `dark_nolabels` (bottom), VIIRS overlay (middle), `dark_only_labels` (top). URLs: `https://basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png` and `https://basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png` (no API key needed, subject to fair use terms).
- Python virtual environment should be in `backend/.venv/` (gitignored).
- Use `uv` for Python package management if available, otherwise `pip`.
