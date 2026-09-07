import re
import requests

from config import REVERSE_SEARCH_API_KEY, GOOGLE_CSE_KEY, GOOGLE_CSE_ID
from profiles.extractor import _canon, _RESERVED
from search.providers.provider import detect_platform

_SOCIAL_SITES = [
    ("X/Twitter", "twitter.com"),
    ("Instagram", "instagram.com"),
    ("GitHub", "github.com"),
    ("LinkedIn", "linkedin.com"),
    ("Facebook", "facebook.com"),
    ("YouTube", "youtube.com"),
    ("TikTok", "tiktok.com"),
    ("Reddit", "reddit.com"),
    ("Twitch", "twitch.tv"),
    ("Pinterest", "pinterest.com"),
    ("Medium", "medium.com"),
    ("Threads", "threads.net"),
    ("Telegram", "t.me"),
    ("Snapchat", "snapchat.com"),
    ("SoundCloud", "soundcloud.com"),
    ("DeviantArt", "deviantart.com"),
    ("Flickr", "flickr.com"),
]

_PROFILE_PATH_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:instagram\.com|facebook\.com|twitter\.com|x\.com|tiktok\.com|youtube\.com|"
    r"linkedin\.com/(?:in|company)|pinterest\.[a-z.]+|reddit\.com/(?:u|user)|"
    r"threads\.net|github\.com|t\.me|snapchat\.com/add|twitch\.tv|soundcloud\.com|"
    r"medium\.com/@|deviantart\.com|flickr\.com/photos)"
    r"/([A-Za-z0-9_.-]+)",
    re.I,
)

_IGNORED_HANDLE_PREFIXES = {
    "p", "reel", "tv", "stories", "explore", "about", "accounts", "login",
    "signup", "status", "share", "search", "i", "watch", "playlist", "results",
    "feed", "trending", "embed", "upload", "discover", "topic", "live",
    "tags", "tag", "morelikethis", "groups", "pages", "photos",
}

_JUNK_HANDLES = {
    "groups", "morelikethis", "tag", "tags", "popular", "ideas", "people",
    "pin", "pins", "topic", "topics", "orgs", "post", "posts", "me", "home",
    "explore", "discover", "collections", "boards", "s", "feed", "featured",
    "search", "login", "signup", "status", "channel", "channels", "pages",
    "page", "account", "accounts", "settings", "notifications", "messages",
    "marketplace", "marketplaceapm", "marketplacevideos",
}


def _serp_web_query(session: requests.Session, q: str) -> list[dict]:
    if not REVERSE_SEARCH_API_KEY:
        return []
    resp = session.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "api_key": REVERSE_SEARCH_API_KEY, "q": q},
        timeout=30,
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("organic_results", [])


def _cse_web_query(session: requests.Session, q: str) -> list[dict]:
    if not (GOOGLE_CSE_KEY and GOOGLE_CSE_ID):
        raise RuntimeError("Google CSE not configured (GOOGLE_CSE_KEY / GOOGLE_CSE_ID)")
    resp = session.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": GOOGLE_CSE_KEY, "cx": GOOGLE_CSE_ID, "q": q, "num": 10},
        timeout=30,
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return [
        {"title": item.get("title", ""), "link": item.get("link", "")}
        for item in data.get("items", [])
    ]


def _web_query(session: requests.Session, q: str) -> tuple[list[dict], str]:
    errors = []
    for fn in (_serp_web_query, _cse_web_query):
        try:
            items = fn(session, q)
            if items:
                return items, ""
        except Exception as e:
            errors.append(str(e))
    return [], "; ".join(errors)[:300]


def _extract_name_from_titles(candidates: list[dict]) -> str:
    _EXCLUDE = {"has", "no", "not", "with", "for", "the", "and", "his", "her", "was", "are", "is", "will", "can", "may", "just", "new", "old", "all", "one", "two", "how", "why", "who", "what", "when", "where", "which", "that", "this", "from", "into", "over", "most", "best", "top", "only", "first", "last", "next", "day", "year", "time", "way", "see", "get", "got", "said", "says", "told", "says", "via", "vs", "de", "la", "le", "gets", "goes", "does", "says", "told", "tells", "makes", "takes", "gives", "shows", "says", "sees", "wants", "calls", "uses", "asks", "seems", "means", "needs", "feels", "says", "runs", "works", "wins", "loses", "dies", "born", "fired", "hired", "leaves", "joins", "moves", "says", "set", "puts", "cuts", "drops", "pulls", "pushes", "turns", "brings", "holds", "keeps", "lets", "pays", "sends", "sets", "throws", "uses", "wants"}
    from collections import Counter

    counts: Counter = Counter()
    for c in candidates[:15]:
        title = c.get("title") or ""
        for m in re.finditer(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", title):
            name = m.group(1)
            words = name.split()
            if len(words) != 2:
                continue
            if any(w.lower() in _EXCLUDE for w in words):
                continue
            if len(name) >= 5:
                counts[name] += 1
    if not counts:
        return ""
    return counts.most_common(1)[0][0]


def _profile_url_matches(url: str, domain: str) -> str | None:
    m = _PROFILE_PATH_RE.search(url)
    if not m:
        return None
    handle = m.group(1)
    if handle.lower() in _IGNORED_HANDLE_PREFIXES:
        return None
    if domain in ("twitter.com", "x.com") and handle == "i":
        return None
    return handle


_PLATFORM_QUERIES = {
    "X/Twitter": [
        "site:x.com/{handle}",
        "site:twitter.com/{handle}",
        "site:x.com \"{name}\"",
    ],
    "Instagram": [
        "site:instagram.com/{handle}",
        "site:instagram.com \"{name}\"",
    ],
    "Facebook": [
        "site:facebook.com/{handle}",
        "site:facebook.com \"{name}\"",
    ],
    "GitHub": [
        "site:github.com/{handle}",
        "github.com \"{name}\"",
    ],
    "LinkedIn": [
        "site:linkedin.com/in/{handle}",
        "site:linkedin.com/in \"{name}\"",
    ],
    "YouTube": [
        "site:youtube.com/@{handle}",
    ],
    "TikTok": [
        "site:tiktok.com/@{handle}",
        "site:tiktok.com \"{name}\"",
    ],
    "Pinterest": [
        "site:pinterest.com/{handle}",
    ],
    "Reddit": [
        "site:reddit.com/user/{handle}",
    ],
    "Telegram": [
        "site:t.me/{handle}",
    ],
    "Threads": [
        "site:threads.net/@{handle}",
        "site:threads.net \"{name}\"",
    ],
    "DeviantArt": [
        "site:deviantart.com/{handle}",
    ],
    "Flickr": [
        "site:flickr.com/photos/{handle}",
    ],
}


def _handle_variants(name: str) -> list[str]:
    parts = re.findall(r"[A-Za-z]+", name)
    low = [p.lower() for p in parts]
    if not low:
        return [name.lower()]
    variants = ["".join(low)]
    if len(low) >= 2:
        variants.append("_".join(low))
        variants.append("-".join(low))
        variants.append("_".join(p.capitalize() for p in low))
        variants.append("_".join(p.capitalize() for p in low) + "_")
    return list(dict.fromkeys(variants))


def discover_profiles_by_name(name: str, seen_urls: set[str]) -> dict[str, list[str]]:
    if not name or not REVERSE_SEARCH_API_KEY:
        return {}

    found: dict[str, set] = {}
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    discover_profiles_by_name.last_error = ""

    name_parts = name.lower().split()
    name_no_space = "".join(name_parts)
    variants = _handle_variants(name)

    # Skip platforms already covered once we hit an official profile for them.
    queried_queries: set[str] = set()
    calls = 0
    MAX_CALLS = 25
    for platform, domain in _SOCIAL_SITES:
        templates = _PLATFORM_QUERIES.get(platform, ["\"{name}\" {platform} profile"])
        for template in templates:
            run_variants = variants if "{handle}" in template else variants[:1]
            for variant in run_variants:
                q = template.format(name=name, handle=variant, platform=platform)
                if q in queried_queries:
                    continue
                queried_queries.add(q)
                if calls >= MAX_CALLS:
                    discover_profiles_by_name.last_error = "Discovery call limit reached."
                    return {p: sorted(u) for p, u in found.items()}
                calls += 1
                try:
                    organic, qerr = _web_query(session, q)
                except Exception as e:
                    discover_profiles_by_name.last_error = str(e)[:200]
                    continue
                if qerr:
                    discover_profiles_by_name.last_error = qerr
                official_hit = False
                for item in organic:
                    link = item.get("link", "")
                    if not link or link in seen_urls:
                        continue
                    handle = _profile_url_matches(link, domain)
                    if not handle:
                        continue
                    if handle.lower() in _JUNK_HANDLES:
                        continue
                    handle_lower = handle.lower()
                    canonical = _canon(platform, handle)
                    is_official = any(part in handle_lower for part in name_parts) or name_no_space in handle_lower
                    if is_official and canonical not in seen_urls:
                        seen_urls.add(canonical)
                        found.setdefault(platform, set()).add(canonical)
                        official_hit = True
                if official_hit:
                    break
            if platform in found:
                break
        total_found = sum(len(u) for u in found.values())
        if total_found >= 8:
            break

    return {p: sorted(u) for p, u in found.items()}
