# DarkFinder

DarkFinder turns [NASA VIIRS](https://en.wikipedia.org/wiki/Visible_Infrared_Imaging_Radiometer_Suite)
nighttime satellite imagery into an interactive light-pollution heat map of the entire
planet. Brighter colors mean there's more light pollution, while darker ones indicate
darker skies. Check out [the current Vercel deployment](https://dark-finder.vercel.app/) 
if you're interested in seeing it in action!  

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

## Attribution

Base map tiles © [CARTO](https://carto.com/attributions), with map data ©
[OpenStreetMap](https://www.openstreetmap.org/copyright) contributors. Nighttime-lights
data courtesy of NASA and the [Earth Observation Group](https://eogdata.mines.edu/) at the
Colorado School of Mines. DarkFinder is an independent project and is not affiliated with
or endorsed by these providers.

## Getting started

### Prerequisites

- **Node.js** (for the React/Vite frontend)
- **Python 3.12+** and [**uv**](https://docs.astral.sh/uv/) (for the FastAPI backend)
- A free **Google Earth Engine** account, with a **Google Cloud project** that has the
  Earth Engine API enabled — the data pipeline downloads the VIIRS composite through it.
  (Sign up at [earthengine.google.com](https://earthengine.google.com/); approval is
  usually quick.)

### Configure the project ID

Before running the pipeline, point it at your Earth Engine–enabled GCP project. Copy the
template and fill in your project ID:

```bash
cp backend/.env.example backend/.env
# then edit backend/.env and set GEE_PROJECT=your-gcp-project-id
```

Without this, the download step exits with `GEE_PROJECT not set`.

### First-time setup

Once `backend/.env` is configured, one command from the repo root installs everything and
builds the data:

```bash
make setup
```

This runs three steps in order:

1. **Install** — frontend packages (`npm install`) and a backend virtualenv in
   `backend/.venv`.
2. **Authenticate** — opens a browser to sign in to Earth Engine (one-time).
3. **Pipeline** — downloads the 2023 VIIRS composite and builds the emission and Sky Glow
   tiles. This is a large, one-time download, so expect it to take a while.

The steps run in sequence, so if one fails (e.g. a missing `GEE_PROJECT`), `make setup`
stops there. The earlier steps are safe to repeat, but once install and auth are done you
can just re-run the step that failed — usually `make pipeline` — instead of the whole
`make setup`.

If you'd rather run the steps individually, they're also available on their own:

```bash
make install                      # deps only
make auth                         # Earth Engine sign-in (opens a browser)
make pipeline                     # download + process, defaults to 2023
```

`YEAR` is optional and defaults to 2023; pass `make pipeline YEAR=2022` to target a
different year.

### Run

From the repo root, start both dev servers with one command (Ctrl-C stops both):

```bash
make dev                          # Vite on :5173, FastAPI on :8000
```

Open http://localhost:5173 to view the map. (If the data server isn't running, the map
falls back to NASA's pre-rendered Black Marble tiles so it still renders.)

### Quality checks

```bash
make lint                         # ESLint (frontend) + ruff (backend)
make typecheck                    # tsc --noEmit
```

## License

MIT License

Copyright (c) 2026 Eidetic Studios

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
