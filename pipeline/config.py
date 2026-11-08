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

# --- Harmonization -------------------------------------------------------------
HARMONIZATION_METHOD = "monthly_ratio_v1"
REFERENCE_MODIS_SATELLITE = "Aqua"     # afternoon overpass, similar to S-NPP
REFERENCE_VIIRS_SATELLITE = "N"        # S-NPP as coded in FIRMS (verify in Phase 1)
MIN_COMMON_CELL_DAYS = 30              # below this, fall back to the annual factor

# --- Export --------------------------------------------------------------------
MAX_WEB_DATA_MB = 15
