# FaceLens CLI

**AI Face Search & Verification System**

Search a face. Discover public matches. Verify the result. Prove the record.

## What It Does

FaceLens CLI accepts a photograph of a person, performs genuine reverse-image discovery across publicly indexed web content, identifies possible social-media profiles and visually similar images, compares detected faces using ArcFace embeddings, ranks candidate matches by similarity, and records the verification result on blockchain.

## Pipeline

```
Image → Face Detection → Face-Only Crop (background masked) → Face Embedding
  → Reverse Image Search (face-only query)
  → Google Lens identity matching → Public Web Results
  → Candidate Images → Face Detection on Candidates → reject non-face results
  → ArcFace Comparison → Rank Matches → Social Profile Discovery by Name
  → Verification Result → SHA-256 Hash → Blockchain Record
```

## Face-Only (Person) Search

By default the pipeline **crops the query to the detected face only** and blackens
everything outside an eye–nose–chin ellipse — background, body, glasses, logos and
ads are removed so search engines match the *person*, not the surrounding image.

- The face-only crop is saved to `results/face_only_*.jpg` so you can verify what was searched.
- Non-face results (products, ads, logos, graphics) are rejected before profile extraction.
- Pass `--search-full-image` to search the whole image instead.

## Social Profile Discovery

Search results that contain a detected face are used to extract social media
handles. When the subject's name can be inferred from the results, the pipeline
additionally queries each major platform (`site:instagram.com/<handle>`,
`site:twitter.com/<handle>`, etc.) to surface the person's genuine profile pages
(Facebook, Instagram, X, TikTok, YouTube, LinkedIn, Reddit, GitHub, and more).

## What "no profiles found" means

If no web image contains a matching face — or the person has no publicly indexed
photo anywhere — the tool reports zero profiles. That is the truthful answer for
an unindexed face; no search service (free or paid) can surface profiles for a
face that has no public presence.

## Three Core Technologies

| Technology | Responsibility |
|---|---|
| **Reverse Search** | "What content on the public web is visually related to this image?" |
| **ArcFace** | "How similar is the detected face in this candidate to the face in my input?" |
| **Blockchain** | "Can I prove that this verification record was recorded and detect later modification?" |

## Installation

### Windows

Requirements: **Python 3.9+** (tick "Add Python to PATH" during install).

```bat
:: Setup (creates venv, installs dependencies)
setup.bat

:: Then run a search
run.bat search --image "C:\Users\you\Pictures\person.jpg"

:: Show help
run.bat --help
```

PowerShell alternative:

```powershell
.\setup.ps1
python main.py search --image "C:\Users\you\Pictures\person.jpg"
```

After `setup.bat`, copy the `.env` file from your Linux server into the folder (it contains your working `PRIVATE_KEY`, `CONTRACT_ADDRESS`, RPC, and search API key). If it's missing, `setup.bat` creates one from `.env.example`.

On first run, InsightFace downloads its `buffalo_l` model (~288 MB) into `%USERPROFILE%\.insightface\models` automatically.

### Linux/macOS

```bash
cd facelens
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Blockchain (optional)

```bash
npm install
npx hardhat compile
```

## Configuration

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `REVERSE_SEARCH_API_KEY` | SerpAPI key (free tier works; reverse-image engine needs paid plan) |
| `REVERSE_SEARCH_PROVIDER` | `serpapi` or `bing` (default: `serpapi` with auto-fallback) |
| `GOOGLE_CSE_KEY` / `GOOGLE_CSE_ID` | Google Custom Search credentials — free 100 searches/day fallback for social profile discovery when SerpAPI quota runs out |
| `FACE_FIRST_SEARCH` | `true` (default) crops the query to the face only; `false` searches the whole image |
| `GOOGLE_LENS` | `true` (default) additionally queries Google Lens via SerpAPI for identity matching |
| `RPC_URL` | Ethereum RPC endpoint (default: Sepolia PublicNode) |
| `PRIVATE_KEY` | Wallet private key for blockchain transactions |
| `CONTRACT_ADDRESS` | Deployed FaceVerification contract address |

## Usage

### Search

```bash
python main.py search --image person.jpg
python main.py search --image person.jpg --limit 30
# Supply the person's name when you know it (skips name guessing):
python main.py search --image person.jpg --name "Tushar Pamnani"
```

When no web image matches the face, the tool asks for the person's name on the
terminal (if run interactively) so it can search their socials directly.

## Face verification on profiles (the "is it really them?" check)

After social profiles are found, the tool downloads each profile's avatar/photo
and compares it to the **face in your input image** with ArcFace, printing a
FACE MATCH table: `MATCH` (≥90%), `LIKELY` (80-90%), or `unlikely`. This proves
whether the face on that profile is the same person as your photo — independent
of what the search engines happened to return.

- Avatars that contain no measurable face are reported as `not measured`.
- Disable with `FACE_PROFILE_VERIFY=false` in `.env`.

### Verify saved result

```bash
python main.py verify --record results/result_001.json
```

### Blockchain lookup

```bash
python main.py blockchain --hash <record_hash>
```

### Help

```bash
python main.py --help
```

## Reverse Search Providers

The search layer uses a provider abstraction (`search/base.py`) with automatic fallback:

1. **SerpAPI** (`google_reverse_image`) — used when `REVERSE_SEARCH_API_KEY` is set and has reverse-image engine access (paid plan).
2. **Bing Visual Search** — automatic fallback; uploads the image to a free host, queries Bing Images, and parses real page/media URLs (Facebook, Tumblr, Pinterest, etc.).

If SerpAPI returns an error or empty results (e.g., free-tier key without image-engine access), the pipeline automatically falls back to Bing.

## Deploy Smart Contract

```bash
# Compile
npx hardhat compile

# Deploy to Sepolia
npx hardhat run scripts/deploy.js --network sepolia
```

Copy the deployed contract address to `.env` as `CONTRACT_ADDRESS`.

## Project Structure

```
facelens/
├── main.py              # CLI entry point
├── config.py            # Configuration
├── requirements.txt
├── face/
│   ├── detector.py      # InsightFace/SCRFD detection
│   ├── encoder.py       # ArcFace embedding
│   ├── matcher.py       # Cosine similarity comparison
│   └── quality.py       # Face quality assessment
├── search/
│   ├── base.py          # Provider abstraction
│   ├── reverse_search.py # Search orchestrator
│   └── providers/
│       └── provider.py  # SerpAPI + scraper providers
├── candidates/
│   ├── downloader.py    # Image downloader
│   ├── extractor.py     # Result extractor
│   └── processor.py     # Candidate face processor
├── ranking/
│   └── ranker.py        # Multi-signal ranking
├── verification/
│   └── verifier.py      # Verification record + hashing
├── blockchain/
│   ├── client.py        # Web3 blockchain client
│   └── abi.json         # Contract ABI
├── contracts/
│   └── FaceVerification.sol
├── scripts/
│   └── deploy.js        # Hardhat deploy script
├── utils/
│   ├── hashing.py       # SHA-256 utilities
│   ├── image.py         # Image I/O utilities
│   └── logger.py        # Rich CLI output
├── tests/
│   └── test_core.py
└── results/             # Saved JSON results
```

## Limitations

- Only publicly indexed/accessible content can be discovered
- Search engines do not index the entire internet
- Social platforms may restrict indexing/access
- Face similarity is not absolute proof of identity
- Search results depend on the chosen provider
- API rate limits may affect results
- Image quality and pose influence face matching

## What Blockchain Does NOT Prove

Blockchain does **not** prove: "This person is definitely John Doe."

It proves: "This verification record was recorded on-chain and can be checked for subsequent alteration."

## Security

- `.env` is git-ignored and must never be committed.
- Commit `.env.example` with **placeholder** values only.
- If a real key/secret was ever committed and pushed, treat it as **compromised**:
  rotate it immediately (the git history still contains it even after a fix commit).

## License

MIT
