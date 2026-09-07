# FaceLens CLI

**AI Face Search & Verification System**

Search a face. Discover public matches. Verify the result. Prove the record.

## What It Does

FaceLens CLI accepts a photograph of a person, performs genuine reverse-image
discovery across publicly indexed web content, identifies possible social-media
profiles and visually similar images, compares detected faces using ArcFace
embeddings, ranks candidate matches by similarity, and records the verification
result on the **Sepolia** blockchain — for every completed run, whether or not a
face match was found.

## Pipeline

```
Image → Face Detection → Face-Only Crop (background masked) → Face Embedding
  → Reverse Image Search (face-only query, full-image fallback)
  → Candidate Images → Face Detection on Candidates → reject non-face results
  → ArcFace Comparison → Rank Matches
  → Name Inference (frequency-based) → Social Profile Discovery by Name
  → Profile-Avatar Face Verification ("is it really them?")
  → Verification Result → SHA-256 Hash → Blockchain Record (every run)
```

## Key Features

### Face-Only (Person) Search

By default the pipeline **crops the query to the detected face only** and
blackens everything outside an eye–nose–chin ellipse — background, body,
glasses, logos and ads are removed so search engines match the *person*, not the
surrounding image.

- The face-only crop is saved to `results/face_only_*.jpg` so you can verify
  exactly what was searched.
- Non-face results (products, ads, logos, graphics) are rejected before profile
  extraction, using a serious product-domain blacklist (eyewear/optical stores,
  etc.).
- Pass `--search-full-image` to search the whole image instead of the face crop.
- If the face crop finds no indexed match, the pipeline automatically falls back
  to the full image and reports honestly that only the surroundings matched
  (e.g. an eyeglasses ad) rather than silently fabricating a "person" result.

### Honest Result Reporting

The CLI never pretends an unrelated product/ad page is the person:

- When only surroundings matched, it warns: *"The engine matched only the
  person's surroundings"*.
- When every web result is a product page, it discards them all and says so.
- When the reverse search API itself fails (quota/network), it tells you the
  problem instead of returning silent empty results.

### Name Inference & Social Discovery

When no name is supplied, the pipeline infers the subject's name from the
**most frequent** two-word capitalized name across **all** reverse-search result
titles (not just face-bearing ones) — so a random face in an unrelated tweet
can't hijack the search (e.g. it correctly identifies "Elon Musk", not "Jeremy
Fowler").

With a name, the pipeline queries each platform:

```
X/Twitter, Instagram, Facebook, GitHub, LinkedIn, YouTube, TikTok, Pinterest,
Reddit, Telegram, Threads, DeviantArt, Flickr
```

using handle variants (concat, underscore, dash, TitleCase, TitleCase_) and
name-only fallback queries. Validated results are filtered:

- Junk handles (`marketplace…`, `groups`, `home`, …) are dropped.
- Off-topic handles that don't relate to the inferred name are dropped.
- Impersonator duplicates (`elonmusk.1723803`, `elonmusk.28695546`, …) are
  collapsed to one clean profile per handle base.

Early-stop at ≥8 profiles and a per-run search budget (`MAX_CALLS=25`) keep API
usage predictable.

### Face Verification on Profiles ("is it really them?")

After social profiles are found, the tool downloads each profile's avatar/photo
and compares it to the **face in your input image** with ArcFace, printing a
FACE MATCH table:

- `MATCH` — ≥90% similarity
- `LIKELY` — 80–90%
- `unlikely` — <80%
- `not measured` — avatar contains no measurable face

This proves whether the face on that profile is the same person as your photo —
independent of what the search engines happened to return.

### Blockchain Proof (every run)

Every completed run — matched or not — computes a SHA-256 `record_hash` over the
verification record and writes it to the `FaceVerification` contract on Sepolia:

- **Matched run**: records `(record_hash, input_hash, candidate_url, similarity, matched=true)`.
- **No-match run**: records `(record_hash, input_hash, "", 0.0, matched=false)` —
  an immutable timestamped proof that the search happened and found no match.

The transaction hash and block are printed and saved into the result JSON, so you
can open the Etherscan link to see the embedded hash in the contract call args.

## Setup

### Requirements

- **Python 3.9+** (tick "Add Python to PATH" on Windows)
- **Node.js + npm** (only for contract compile/deploy; not needed to run searches)
- Network access to the public internet and an Ethereum Sepolia RPC

### Windows

Quick start (creates `venv`, installs dependencies, copies `.env`):

```bat
setup.bat

:: Then run a search
run.bat search --image "C:\Users\you\Pictures\person.jpg"

:: With a known name:
run.bat search --image "C:\Users\you\Pictures\person.jpg" --name "Tushar Pamnani"

:: Show help
run.bat --help
```

PowerShell alternative:

```powershell
.\setup.ps1
python main.py search --image "C:\Users\you\Pictures\person.jpg"
```

After `setup.bat`, copy your `.env` into the folder (it contains your `PRIVATE_KEY`,
`CONTRACT_ADDRESS`, `RPC_URL`, and search API key). If it's missing, the setup
script creates one from `.env.example`.

On first run, InsightFace downloads its `buffalo_l` model (~288 MB) into
`%USERPROFILE%\.insightface\models` automatically.

### Linux / macOS / WSL

```bash
cd facelens
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in values (see Configuration)
```

### Blockchain (optional — only if deploying your own contract)

```bash
npm install
npx hardhat compile
npx hardhat run scripts/deploy.js --network sepolia
```

Copy the returned `CONTRACT_ADDRESS` into `.env`. To publish proofs you must have
**Sepolia ETH** in the wallet (e.g. from a faucet) to pay gas; a typical proof
costs well under 0.001 ETH.

## Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `REVERSE_SEARCH_API_KEY` | Yes | SerpAPI key — powers reverse-image **and** social-discovery web search. Free tier 100/mo |
| `REVERSE_SEARCH_PROVIDER` | No | `serpapi` (default) or `bing` |
| `CONTRACT_ADDRESS` | For proofs | Deployed `FaceVerification` contract address (Sepolia) |
| `PRIVATE_KEY` | For proofs | Wallet private key — **must have Sepolia ETH** for gas |
| `RPC_URL` | No | Ethereum RPC (default: Sepolia PublicNode) |
| `GOOGLE_CSE_KEY` / `GOOGLE_CSE_ID` | No | Free Google Custom Search (100/day) fallback for social discovery when SerpAPI quota runs out. Get at programmablesearchengine.google.com + Google Cloud Console |
| `FACE_FIRST_SEARCH` | No | `true` (default) crops to the face; `false` searches the full image |
| `GOOGLE_LENS` | No | `true` (default) also queries Google Lens via SerpAPI for identity matching |
| `FACE_PROFILE_VERIFY` | No | `true` (default) compares the input face against each profile avatar |

> **Security:** never commit `.env`. It is git-ignored. Commit only `.env.example`
> with placeholder values. If a real secret was ever pushed, rotate it
> immediately — git history retains it even after a fix commit.

## Usage

```
usage: facelens [-h] {search,verify,blockchain} ...

  search      Search for a face in public web content
  verify      Verify a saved result on blockchain
  blockchain  Look up a blockchain record
```

### Search

```bash
# Search by face alone (name is inferred from results)
python main.py search --image person.jpg

# Process more candidate results
python main.py search --image person.jpg --limit 30

# Supply the person's name when you know it (skips name guessing)
python main.py search --image person.jpg --name "Tushar Pamnani"

# Search the whole image instead of the face-only crop
python main.py search --image person.jpg --search-full-image

# Windows paths with spaces
python main.py search --image "C:\Users\anujp\Downloads\photo.jpg"
```

When run interactively and no name can be inferred, the tool **prompts for the
person's name** so it can search their socials directly.

### Verify a Saved Result

```bash
python main.py verify --record results/result_001.json
```

### Look Up a Blockchain Record

```bash
python main.py blockchain --hash <record_hash>
```

## Reverse Search Providers

The search layer uses a provider abstraction with automatic fallback:

1. **SerpAPI** (`google_reverse_image`) — primary provider. On free-tier keys
   without image-engine access, `search_image` returns an honest `warning` that
   is surfaced to the user.
2. **Bing Visual Search** — optional fallback via `REVERSE_SEARCH_PROVIDER=bing`.

If the query is the face-only crop and the provider returns nothing, the whole
image is searched as a fallback; the pipeline then rejects product/ad pages.

## Deploy Smart Contract

```bash
npx hardhat compile
npx hardhat run scripts/deploy.js --network sepolia
```

Copy the deployed address to `.env` as `CONTRACT_ADDRESS`.

## Project Structure

```
facelens/
├── main.py                  # CLI entry point (search / verify / blockchain)
├── config.py                # Configuration (.env)
├── requirements.txt         # Python dependencies
├── hardhat.config.js        # Hardhat (contract compilation/deploy)
├── package.json
├── setup.bat / setup.ps1    # Windows bootstrap
├── run.bat                  # Windows run wrapper
├── face/
│   ├── detector.py          # InsightFace/SCRFD detection + face-only crop
│   └── encoder.py           # ArcFace embedding
├── search/
│   ├── reverse_search.py    # Search orchestrator (crop/full fallback, errors)
│   ├── social_discovery.py  # Name inference + platform discovery (13 platforms)
│   ├── profile_face.py      # Avatar download + face-to-face comparison
│   └── providers/
│       └── provider.py      # SerpAPI + Bing providers
├── candidates/
│   ├── extractor.py         # Result extraction
│   ├── downloader.py        # Image downloader
│   └── processor.py         # Candidate face processor
├── ranking/
│   └── ranker.py            # Multi-signal ranking
├── verification/
│   └── verifier.py          # Verification record + hashing
├── blockchain/
│   ├── client.py            # Web3 client (record / read)
│   └── abi.json             # Contract ABI
├── contracts/
│   └── FaceVerification.sol # Sepolia contract
├── scripts/
│   └── deploy.js            # Hardhat deploy script
├── utils/
│   ├── hashing.py           # SHA-256 utilities
│   ├── image.py             # Image I/O + Windows path resolution
│   └── logger.py            # Rich CLI output
├── tests/                   # 51 tests across 5 suites
├── results/                 # Saved JSON results (+ face-only crops)
└── .env.example             # Template configuration
```

## Tests

```bash
source venv/bin/activate
python -m pytest tests/ -q
```

51 tests across `test_core`, `test_face_only`, `test_profiles`,
`test_social_discovery`, and `test_profile_face`.

## Limitations & Honest Caveats

- Only publicly indexed/accessible content can be discovered — an unindexed face
  truthfully returns zero profiles.
- Reverse image search matches visual similarity, not identity. A stylized or
  low-resolution illustration may return the right text results but fail face
  matching (e.g. a graphic "background" wallpaper of a famous person).
- Search engines do not index the entire internet.
- Social platforms may restrict indexing/access (LinkedIn is login-gated; X/Twitter
  avatars are often not scrapable → reported `not measured`).
- Face similarity is probabilistic, not absolute proof of identity.
- API rate limits (SerpAPI free tier = 100/mo) may produce empty results.
- Image quality and pose influence face matching.

## What Blockchain Does NOT Prove

Blockchain does **not** prove: *"This person is definitely John Doe."*

It proves: *"This verification record was recorded on-chain at this timestamp and
can be checked for subsequent alteration."*

## License

MIT