import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

FACE_DETECTION_MODEL = "buffalo_l"
FACE_DETECTION_PROVIDER = "insightface"
EMBEDDING_MODEL = "arcface"
SIMILARITY_THRESHOLD_HIGH = 0.90
SIMILARITY_THRESHOLD_MEDIUM = 0.80
SIMILARITY_THRESHOLD_LOW = 0.60
MAX_IMAGE_SIZE_MB = 10
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}
DOWNLOAD_TIMEOUT = 15
SOCIAL_PAGE_TIMEOUT = 8
MAX_PROFILE_PAGES = 15
MAX_CANDIDATE_IMAGES = 50

RANKING_WEIGHTS = {
    "face": 0.60,
    "image": 0.20,
    "search": 0.15,
    "source": 0.05,
}

REVERSE_SEARCH_API_KEY = os.getenv("REVERSE_SEARCH_API_KEY", "")
REVERSE_SEARCH_PROVIDER = os.getenv("REVERSE_SEARCH_PROVIDER", "serpapi")
FACE_FIRST_SEARCH = os.getenv("FACE_FIRST_SEARCH", "true").strip().lower() == "true"
GOOGLE_LENS = os.getenv("GOOGLE_LENS", "true").strip().lower() == "true"
GOOGLE_CSE_KEY = os.getenv("GOOGLE_CSE_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
FACE_PROFILE_VERIFY = os.getenv("FACE_PROFILE_VERIFY", "true").strip().lower() == "true"

RPC_URL = os.getenv("RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
