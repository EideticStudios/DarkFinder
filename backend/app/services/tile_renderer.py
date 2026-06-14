"""
Render a 256x256 PNG tile from a Cloud-Optimized GeoTIFF. Both the emission and
sky-glow layers share one vivid color ramp (RAMP_COLORS); they differ only in
their value anchors and interpolation (linear for emission, log for sky-glow).
"""

import io
from typing import Literal

import numpy as np
from PIL import Image

Layer = Literal["emission", "skyglow"]

# ── Shared color ramp ─────────────────────────────────────────────────────────
# One vivid 9-stop palette (Bortle classes 1–9) shared by both the emission and
# sky-glow layers so the map and legend always agree. Magenta is the brightest
# band; the legend mirror lives in frontend/src/lib/bortleScale.ts.

BASE_ALPHA = 235

RAMP_COLORS: list[tuple[int, int, int]] = [
    (0x02, 0x02, 0x2E),  # Bortle 1 — pristine dark sky
    (0x0B, 0x1E, 0x8C),  # Bortle 2 — typical dark site
    (0x1E, 0x64, 0xDC),  # Bortle 3 — rural sky
    (0x00, 0xC8, 0xC8),  # Bortle 4 — rural/suburban
    (0x28, 0xB4, 0x28),  # Bortle 5 — suburban sky
    (0xF0, 0xF0, 0x00),  # Bortle 6 — bright suburban
    (0xFF, 0x8C, 0x00),  # Bortle 7 — suburban/urban
    (0xFF, 0x1E, 0x1E),  # Bortle 8 — city sky
    (0xFF, 0x50, 0xFF),  # Bortle 9 — inner-city sky
]

# ── Emission ramp anchors ─────────────────────────────────────────────────────

BREAKPOINTS: list[float] = [0.0, 0.2, 0.4, 1.0, 3.0, 6.0, 12.0, 30.0, 60.0]


def apply_bortle_colormap(band: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """
    Map a float32 radiance band to an RGBA uint8 array using the Bortle color ramp.

    Args:
        band:       (H, W) float32 radiance values in nW/cm²/sr
        valid_mask: (H, W) bool — True = valid pixel, False = nodata

    Returns:
        (H, W, 4) uint8 RGBA array
    """
    h, w = band.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    # Linear interpolation between adjacent Bortle class colors
    for i in range(len(BREAKPOINTS) - 1):
        lo, hi = BREAKPOINTS[i], BREAKPOINTS[i + 1]
        seg_mask = (band >= lo) & (band < hi)
        if not np.any(seg_mask):
            continue

        t = (band[seg_mask] - lo) / (hi - lo)
        r0, g0, b0 = RAMP_COLORS[i]
        r1, g1, b1 = RAMP_COLORS[i + 1]

        rgba[seg_mask, 0] = np.clip(r0 + t * (r1 - r0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 1] = np.clip(g0 + t * (g1 - g0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 2] = np.clip(b0 + t * (b1 - b0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 3] = BASE_ALPHA

    # Clamp anything >= 60 to Bortle 9
    top_mask = band >= BREAKPOINTS[-1]
    if np.any(top_mask):
        r, g, b = RAMP_COLORS[-1]
        rgba[top_mask] = (r, g, b, BASE_ALPHA)

    # Transparent where nodata or zero radiance
    no_light = (band <= 0) | np.isnan(band) | ~valid_mask
    rgba[no_light, 3] = 0

    return rgba


# ── Sky-glow ramp anchors ─────────────────────────────────────────────────────
# Shares RAMP_COLORS with the emission layer; only the value anchors differ.
# Tuned against the post-kernel distribution (p50~0.0002, p90~0.23, p99~3.2,
# max~2950): green (#28B428) ~ p90, orange/red ~ p99, and only the extreme tail
# (dense city cores) reaches magenta. Log-interpolated between anchors.

FADE_FLOOR = 1e-3  # nW/cm²/sr — below this, fully transparent (kills FFT noise ~1e-9)

SKYGLOW_ANCHORS: list[float] = [
    0.002, 0.008, 0.03, 0.08, 0.2, 0.6, 1.8, 6.0, 30.0,
]


def apply_skyglow_colormap(band: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """
    Map a float32 sky-glow band to RGBA using log10-interpolated vivid ramp.

    Values below the lowest anchor fade alpha to 0 (reveal basemap in pristine
    areas). Values >= the top anchor clamp to magenta; invalid pixels transparent.
    """
    h, w = band.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    safe = np.where((band > 0) & np.isfinite(band), band, 1e-10)
    log_band = np.log10(safe)

    for i in range(len(SKYGLOW_ANCHORS) - 1):
        lo, hi = SKYGLOW_ANCHORS[i], SKYGLOW_ANCHORS[i + 1]
        seg_mask = (band >= lo) & (band < hi)
        if not np.any(seg_mask):
            continue

        log_lo, log_hi = np.log10(lo), np.log10(hi)
        t = (log_band[seg_mask] - log_lo) / (log_hi - log_lo)

        r0, g0, b0 = RAMP_COLORS[i]
        r1, g1, b1 = RAMP_COLORS[i + 1]
        rgba[seg_mask, 0] = np.clip(r0 + t * (r1 - r0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 1] = np.clip(g0 + t * (g1 - g0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 2] = np.clip(b0 + t * (b1 - b0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 3] = BASE_ALPHA

    # Clamp >= top anchor to the top color (magenta)
    top_mask = band >= SKYGLOW_ANCHORS[-1]
    if np.any(top_mask):
        r, g, b = RAMP_COLORS[-1]
        rgba[top_mask] = (r, g, b, BASE_ALPHA)

    # Fade alpha from 0 (at FADE_FLOOR) to BASE_ALPHA (at lowest anchor)
    fade_mask = (band >= FADE_FLOOR) & (band < SKYGLOW_ANCHORS[0]) & valid_mask
    if np.any(fade_mask):
        log_floor = np.log10(FADE_FLOOR)            # -3
        log_anchor = np.log10(SKYGLOW_ANCHORS[0])   # -2
        fade_t = np.clip((log_band[fade_mask] - log_floor) / (log_anchor - log_floor), 0, 1)
        r0, g0, b0 = RAMP_COLORS[0]
        rgba[fade_mask, 0] = r0
        rgba[fade_mask, 1] = g0
        rgba[fade_mask, 2] = b0
        rgba[fade_mask, 3] = (fade_t * BASE_ALPHA).astype(np.uint8)

    # Fully transparent for invalid / non-positive
    invalid = (band <= 0) | np.isnan(band) | ~valid_mask
    rgba[invalid, 3] = 0

    return rgba


# ── Tile rendering ────────────────────────────────────────────────────────────

def render_tile(
    cog_path: str, z: int, x: int, y: int, layer: Layer = "emission"
) -> bytes | None:
    """
    Read a tile window from a COG and return colored PNG bytes.
    Returns None if the tile falls outside the COG extent.
    """
    try:
        from rio_tiler.errors import TileOutsideBounds
        from rio_tiler.io import COGReader
    except ImportError as exc:
        raise RuntimeError("rio-tiler is required for tile rendering") from exc

    try:
        with COGReader(cog_path) as cog:
            img = cog.tile(x, y, z, resampling_method="bilinear", reproject_method="bilinear")
    except TileOutsideBounds:
        return None

    band = img.data[0].astype(np.float32)           # (H, W)

    # Build a boolean valid-pixel mask. rio-tiler uses 0 for invalid pixels
    # regardless of mask dtype (uint8 255=valid or float32 FLT_MAX=valid).
    raw_mask = img.mask if img.mask.ndim == 2 else img.mask[0]
    valid_mask = raw_mask != 0

    if layer == "skyglow":
        rgba = apply_skyglow_colormap(band, valid_mask)
    else:
        rgba = apply_bortle_colormap(band, valid_mask)

    pil_img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()
