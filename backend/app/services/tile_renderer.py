"""
Render a 256x256 PNG tile from a Cloud-Optimized GeoTIFF using either the
Bortle color ramp (emission layer) or an lpm-style vivid ramp (sky-glow layer).
"""

import io
from typing import Literal

import numpy as np
from PIL import Image

Layer = Literal["emission", "skyglow"]

# ── Emission (Bortle) color ramp ──────────────────────────────────────────────

BREAKPOINTS: list[float] = [0.0, 0.2, 0.4, 1.0, 3.0, 6.0, 12.0, 30.0, 60.0]

COLORS: list[tuple[int, int, int, int]] = [
    (0x00, 0x00, 0x11, 200),  # Bortle 1 — pristine dark sky
    (0x00, 0x00, 0x33, 200),  # Bortle 2 — typical dark site
    (0x00, 0x33, 0x66, 200),  # Bortle 3 — rural sky
    (0x00, 0x66, 0x33, 200),  # Bortle 4 — rural/suburban
    (0x33, 0x99, 0x00, 200),  # Bortle 5 — suburban sky
    (0xCC, 0xCC, 0x00, 200),  # Bortle 6 — bright suburban
    (0xFF, 0x66, 0x00, 200),  # Bortle 7 — suburban/urban
    (0xCC, 0x00, 0x00, 220),  # Bortle 8 — city sky
    (0xFF, 0xFF, 0xFF, 220),  # Bortle 9 — inner-city sky
]


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
        r0, g0, b0, a0 = COLORS[i]
        r1, g1, b1, a1 = COLORS[i + 1]

        rgba[seg_mask, 0] = np.clip(r0 + t * (r1 - r0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 1] = np.clip(g0 + t * (g1 - g0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 2] = np.clip(b0 + t * (b1 - b0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 3] = np.clip(a0 + t * (a1 - a0), 0, 255).astype(np.uint8)

    # Clamp anything >= 60 to Bortle 9
    top_mask = band >= BREAKPOINTS[-1]
    if np.any(top_mask):
        r, g, b, a = COLORS[-1]
        rgba[top_mask] = (r, g, b, a)

    # Transparent where nodata or zero radiance
    no_light = (band <= 0) | np.isnan(band) | ~valid_mask
    rgba[no_light, 3] = 0

    return rgba


# ── Sky-glow (lpm-style) color ramp ──────────────────────────────────────────

SKYGLOW_ANCHORS: list[float] = [
    0.01, 0.04, 0.12, 0.35, 1.0, 3.0, 8.0, 20.0, 45.0, 100.0,
]

SKYGLOW_COLORS: list[tuple[int, int, int]] = [
    (0x02, 0x02, 0x2E),  # deep navy
    (0x0B, 0x1E, 0x8C),  # navy blue
    (0x1E, 0x64, 0xDC),  # blue
    (0x00, 0xC8, 0xC8),  # cyan
    (0x28, 0xB4, 0x28),  # green
    (0xF0, 0xF0, 0x00),  # yellow
    (0xFF, 0x8C, 0x00),  # orange
    (0xFF, 0x1E, 0x1E),  # red
    (0xFF, 0x50, 0xFF),  # magenta
    (0xFF, 0xFF, 0xFF),  # white
]


def apply_skyglow_colormap(band: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    """
    Map a float32 sky-glow band to RGBA using log10-interpolated vivid ramp.

    Values below 0.01 fade alpha to 0 (reveal basemap in pristine areas).
    Values >= 100 clamp to white. Invalid pixels are fully transparent.
    """
    h, w = band.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    base_alpha = 235

    safe = np.where((band > 0) & np.isfinite(band), band, 1e-10)
    log_band = np.log10(safe)

    for i in range(len(SKYGLOW_ANCHORS) - 1):
        lo, hi = SKYGLOW_ANCHORS[i], SKYGLOW_ANCHORS[i + 1]
        seg_mask = (band >= lo) & (band < hi)
        if not np.any(seg_mask):
            continue

        log_lo, log_hi = np.log10(lo), np.log10(hi)
        t = (log_band[seg_mask] - log_lo) / (log_hi - log_lo)

        r0, g0, b0 = SKYGLOW_COLORS[i]
        r1, g1, b1 = SKYGLOW_COLORS[i + 1]
        rgba[seg_mask, 0] = np.clip(r0 + t * (r1 - r0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 1] = np.clip(g0 + t * (g1 - g0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 2] = np.clip(b0 + t * (b1 - b0), 0, 255).astype(np.uint8)
        rgba[seg_mask, 3] = base_alpha

    # Clamp >= 100 to white
    top_mask = band >= SKYGLOW_ANCHORS[-1]
    if np.any(top_mask):
        r, g, b = SKYGLOW_COLORS[-1]
        rgba[top_mask] = (r, g, b, base_alpha)

    # Below lowest anchor: fade alpha from base_alpha (at 0.01) to 0 (at ~0.001)
    fade_mask = (band > 0) & (band < SKYGLOW_ANCHORS[0]) & valid_mask
    if np.any(fade_mask):
        fade_t = np.clip(log_band[fade_mask] / np.log10(SKYGLOW_ANCHORS[0]), 0, 1)
        r0, g0, b0 = SKYGLOW_COLORS[0]
        rgba[fade_mask, 0] = r0
        rgba[fade_mask, 1] = g0
        rgba[fade_mask, 2] = b0
        rgba[fade_mask, 3] = (fade_t * base_alpha).astype(np.uint8)

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
