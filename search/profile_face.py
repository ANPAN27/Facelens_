import html
import io
import re
import time

import cv2
import numpy as np
import requests

from config import DOWNLOAD_TIMEOUT
from face.matcher import cosine_similarity
from ranking.ranker import classify_match

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Sarari/537.36",
}

_OG_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                    re.I)
_OG_RE2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                     re.I)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def _profile_image_url(session: requests.Session, platform: str, handle: str, url: str) -> str | None:
    handle_clean = handle.lstrip("@")
    domain = (url.split("/")[2] if len(url.split("/")) > 2 else "").lower()

    if "github" in domain:
        return f"https://github.com/{handle_clean}.png"

    if "reddit" in domain:
        try:
            j = session.get(
                f"https://www.reddit.com/user/{handle_clean}/about.json",
                timeout=DOWNLOAD_TIMEOUT,
                headers={"User-Agent": "facelens-cli/1.0"},
            ).json()
            icon = (j.get("data") or {}).get("icon_img") or (j.get("data") or {}).get("snoovatar_img")
            if icon:
                return icon.split("?")[0]
        except Exception:
            pass

    try:
        resp = session.get(url, timeout=DOWNLOAD_TIMEOUT)
        m = _OG_RE.search(resp.text) or _OG_RE2.search(resp.text)
        if m:
            return html.unescape(m.group(1))
    except Exception:
        pass

    return None


def verify_profile_faces(
    input_embedding: np.ndarray,
    social_profiles: dict[str, list[str]],
    encoder,
    detector,
    max_checks: int = 10,
) -> list[dict]:
    """Compare the input face's embedding against each discovered profile's
    avatar/profile photo. Returns checks sorted by face similarity (highest first)."""
    session = _session()
    checks: list[dict] = []

    for platform, urls in social_profiles.items():
        for url in urls:
            if len(checks) >= max_checks:
                break
            handle = url.rstrip("/").split("/")[-1].lstrip("@")
            image_url = None
            status = "fetch-failed"
            similarity = None
            try:
                image_url = _profile_image_url(session, platform, handle, url)
                if not image_url:
                    status = "no-image"
                else:
                    img_resp = session.get(image_url, timeout=DOWNLOAD_TIMEOUT)
                    img_array = np.frombuffer(img_resp.content, dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is None:
                        status = "unreadable-image"
                    else:
                        try:
                            emb, _info = encoder.encode(img)
                        except Exception:
                            status = "no-face-in-avatar"
                        else:
                            sim = cosine_similarity(input_embedding, emb)
                            similarity = round(float(sim), 4)
                            status = "matched" if similarity >= 0.50 else "low-similarity"
            except Exception as e:
                status = f"error:{type(e).__name__}"
            checks.append({
                "platform": platform,
                "url": url,
                "image_url": image_url,
                "face_similarity": similarity,
                "classification": classify_match(similarity) if similarity is not None else "",
                "status": status,
            })
            time.sleep(0.2)

    # confident matches and matches first, no-image/no-face last
    def sort_key(c):
        if c["status"] == "matched":
            return (0, -(c["face_similarity"] or 0))
        if c["status"] == "low-similarity":
            return (1, -(c["face_similarity"] or 0))
        if c["status"] == "no-face-in-avatar":
            return (2, 0)
        if c["status"] == "no-image":
            return (3, 0)
        return (4, 0)

    checks.sort(key=sort_key)
    return checks