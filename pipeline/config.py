"""Central configuration for the pipeline (PLAN.md, section 6).

Every method decision lives here so it can be reviewed and changed in one place.
"""

from pathlib import Path

# --- Scope -------------------------------------------------------------------
YEAR = 2024
COUNTRY = "Mexico"

# --- Paths -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
REPORTS_DIR = DATA_DIR / "reports"
WEB_DATA_DIR = ROOT / "web" / "public" / "data"

# --- Input files (FIRMS "Country Yearly Summary") ------------------------------
FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/data/country"
SOURCES = {
    "modis": {
        "file": f"modis_{YEAR}_{COUNTRY}.csv",
        "url": f"{FIRMS_BASE_URL}/modis/{YEAR}/modis_{YEAR}_{COUNTRY}.csv",
        "label": "NASA FIRMS MODIS C6.1",
    },
    "viirs": {
        "file": f"viirs-snpp_{YEAR}_{COUNTRY}.csv",
        "url": f"{FIRMS_BASE_URL}/viirs-snpp/{YEAR}/viirs-snpp_{YEAR}_{COUNTRY}.csv",
        "label": "NASA FIRMS VIIRS S-NPP 375 m",
    },
}

# Files that are available but NOT part of the method unless the team approves
# (PLAN.md section 2 leaves NOAA-20 out of scope). Only described in reports.
ALT_SOURCES = {
    "viirs_noaa20": {
        "file": f"viirs-jpss1_{YEAR}_{COUNTRY}.csv",
        "url": f"{FIRMS_BASE_URL}/viirs-jpss1/{YEAR}/viirs-jpss1_{YEAR}_{COUNTRY}.csv",
        "label": "NASA FIRMS VIIRS NOAA-20 375 m",
    },
}

# Columns every FIRMS file must have for the pipeline to work.
REQUIRED_COLUMNS = [
    "latitude", "longitude", "acq_date", "acq_time", "satellite",
    "confidence", "frp", "daynight", "type",
]

# Rough bounding box of Mexico (lon_min, lat_min, lon_max, lat_max), used only
# to flag suspicious coordinates in the exploration report.
MEXICO_BBOX = (-118.6, 14.3, -86.5, 32.9)

# --- Filters -----------------------------------------------------------------
# type: 0 = presumed vegetation fire, 1 = active volcano,
#       2 = other static land source, 3 = offshore
KEEP_TYPES = [0]
MODIS_MIN_CONFIDENCE = 30          # MODIS confidence is 0-100; drop "low" (< 30)
VIIRS_CONFIDENCE = ["n", "h"]      # VIIRS confidence is l/n/h; drop "low"

# --- Local date --------------------------------------------------------------
# Simplification: fixed UTC-6 for the whole country (most of Mexico).
# acq_date + acq_time are in UTC.
UTC_OFFSET_HOURS = -6

# --- Spatial grid --------------------------------------------------------------
H3_RESOLUTION = 5                  # ~250 km² per cell
H3_RESOLUTION_ALT = 4              # sensitivity test

# --- Satellite names -----------------------------------------------------------
# FIRMS codes -> names used everywhere downstream (verified in Phase 1).
SATELLITE_NAMES = {"Terra": "Terra", "Aqua": "Aqua", "N": "S-NPP"}

# --- Data gaps -----------------------------------------------------------------
# A local day with zero raw detections (before any filter) for a sensor is
# treated as "no data" (instrument/processing outage), not as "no fire".
# Phase 1 found 20 such days for VIIRS S-NPP in 2024 and none for MODIS.

# --- Harmonization -------------------------------------------------------------
HARMONIZATION_METHOD = "monthly_ratio_v1"
REFERENCE_MODIS_SATELLITE = "Aqua"     # afternoon overpass, similar to S-NPP
REFERENCE_VIIRS_SATELLITE = "S-NPP"
MIN_COMMON_CELL_DAYS = 30              # below this, fall back to the annual factor

# --- Export --------------------------------------------------------------------
MAX_WEB_DATA_MB = 15
