# DarkFinder

DarkFinder turns [NASA VIIRS](https://en.wikipedia.org/wiki/Visible_Infrared_Imaging_Radiometer_Suite)
nighttime satellite imagery into an interactive light-pollution heat map of the entire
planet. Brighter colors mean there's more light pollution, while darker ones indicate
darker skies.

## Data sources

The map is built from VIIRS VNL V2.2, the 2023 annual nighttime-lights composite produced
by the [Earth Observation Group](https://eogdata.mines.edu/) at the Colorado School of
Mines and accessed through [Google Earth Engine](https://earthengine.google.com/). It's
the cloud-free, moonlight-corrected product, so each pixel reflects steady year-round
upward radiance rather than transient weather. Values are calibrated radiance in
nW/cm²/sr at roughly 500 meter (15 arc-second) resolution, and the dataset is public
domain.

If the live data server is unreachable, the client falls back to NASA's pre-rendered
[Black Marble tiles](https://blackmarble.gsfc.nasa.gov/) (2016) so the map still renders.

## Sky Glow and Emission

DarkFinder renders the same area two ways, switchable from the toggle at the top.

Emission is the raw upward radiance: the light leaving streetlights, buildings, and
everything else shining straight up. It maps where light is actually being produced.

Sky Glow models what that light does next. Photons scatter through the atmosphere and
brighten the sky for up to a hundred kilometers around their source, which is why a city
washes out the stars long before you reach its streetlights. If you're hunting for a
genuinely dark site, this is the view that matters, which is why I've set it as the
default one.

Sky Glow is derived from the Emission layer by spreading each source's light outward and
summing the contributions: nearby sources dominate, and their influence decays to zero by
roughly a hundred kilometers. The falloff follows the established
[Falchi/Garstang model](https://www.science.org/doi/10.1126/sciadv.1600377), so the result
approximates the artificial sky brightness an observer on the ground would actually see.

## About the Bortle scale

The [Bortle scale](https://en.wikipedia.org/wiki/Bortle_scale) is a nine-step
classification of night-sky darkness, running from Class 1, the pristine skies you only
find well away from any city, to Class 9, the orange haze over a downtown. DarkFinder bins
each pixel's radiance into one of those nine classes and colors it accordingly. It's a
satellite-derived proxy rather than a ground-based sky-quality (SQM) reading, but it tracks
real-world darkness closely enough to be a reliable guide to where the dark skies are.

- **Class 1** · Pristine dark sky
- **Class 2** · Typical dark site
- **Class 3** · Rural sky
- **Class 4** · Rural / suburban
- **Class 5** · Suburban sky
- **Class 6** · Bright suburban
- **Class 7** · Suburban / urban
- **Class 8** · City sky
- **Class 9** · Inner-city sky

## Technical specs

DarkFinder has a [React](https://react.dev/) and TypeScript frontend, built with
[Vite](https://vite.dev/), and a Python [FastAPI](https://fastapi.tiangolo.com/) backend.
The source data is the global VIIRS VNL V2.2 annual composite, which the pipeline
reprojects and repackages into a [Cloud-Optimized GeoTIFF](https://www.cogeo.org/) (COG)
with internal tiling and overviews, so any zoom level can be served from a few HTTP
byte-range reads rather than loading the full multi-gigabyte raster.

Tiles are rendered on demand. An endpoint (`/tiles/{layer}/{z}/{x}/{y}.png`) uses
[rio-tiler](https://cogeotiff.github.io/rio-tiler/) to read the matching window from the
COG, applies the Bortle color ramp, and returns a PNG. The Sky Glow layer is the one heavy
computation, so it's precomputed offline by convolving the emission raster with a
Falchi/Garstang distance-falloff kernel ([SciPy](https://scipy.org/)), processed in
latitude bands to keep the kernel physically correct as longitudinal scale shrinks toward
the poles, then written out as its own COG served through the same path.

In the browser, [MapLibre GL JS](https://maplibre.org/) composites three layers:
[Carto Dark Matter](https://carto.com/basemaps) base tiles underneath, the VIIRS raster in
the middle, and Carto's label-only tiles on top so place names stay legible above the
glow. The whole project is open source.

## Getting started

### Prerequisites

- **Node.js** (for the React/Vite frontend)
- **Python 3.12+** and [**uv**](https://docs.astral.sh/uv/) (for the FastAPI backend)
- A **Google Earth Engine** account, if you want to run the data pipeline yourself
  (the frontend falls back to Black Marble tiles without it)

### Install

From the repo root, this sets up the frontend (`npm install`) and a backend virtualenv
in `backend/.venv`:

```bash
make install
```

### Get the data

The map needs a processed COG for at least one year. This is a one-time step that
authenticates with Earth Engine, downloads the VIIRS composite, and builds the emission
and Sky Glow tiles:

```bash
earthengine authenticate          # one-time, opens a browser
make pipeline                     # download + process (mosaic + skyglow), defaults to 2023
```

`YEAR` is optional and defaults to 2023; pass `make pipeline YEAR=2022` to target a
different year.

### Run

Start the two dev servers in separate terminals:

```bash
make dev-frontend                 # Vite — http://localhost:5173
make dev-backend                  # FastAPI — http://localhost:8000
```

Open http://localhost:5173 to view the map.

### Quality checks

```bash
make lint                         # ESLint (frontend) + ruff (backend)
make typecheck                    # tsc --noEmit
```
