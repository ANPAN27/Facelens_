#!/usr/bin/env python3
import argparse
import json
import re
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.prompt import Prompt, IntPrompt
from rich.console import Console

from config import (
    RESULTS_DIR, SIMILARITY_THRESHOLD_HIGH, SIMILARITY_THRESHOLD_MEDIUM, FACE_FIRST_SEARCH,
    FACE_PROFILE_VERIFY,
)
from utils.image import validate_image, load_image, compute_file_hash, resolve_image_path
from utils.logger import (
    banner, step_header, step_done, step_fail, info, warn, error,
    match_table, blockchain_result, completion_banner, console,
)
from face.detector import FaceDetector, crop_face_only
from face.encoder import FaceEncoder
from face.quality import compute_face_quality
from search.reverse_search import search_image
from candidates.extractor import extract_candidates
from candidates.processor import CandidateProcessor
from ranking.ranker import rank_candidates
from verification.verifier import VerificationResult
from blockchain.client import BlockchainClient
from profiles.extractor import extract_social_profiles

TOTAL_STEPS = 9


def _prompt_subject_name() -> str:
    try:
        if not sys.stdin.isatty():
            return ""
        console.print("[bold]No web face match found for this image.[/bold]")
        value = input(
            "  Do you know this person's name? (e.g. \"Tushar Pamnani\", Enter to skip): "
        ).strip()
        return value
    except Exception:
        return ""


def run_search(
    image_path: str,
    max_results: int = 20,
    search_full_image: bool = False,
    known_name: str = "",
):
    banner()

    image_path, mapped = resolve_image_path(image_path)
    if mapped:
        info(f"Mapped Windows path to: {image_path}")

    console.print(f"[bold]Input Image:[/bold] {image_path}")
    console.print()

    # Step 1: Load image
    step_header(1, TOTAL_STEPS, "Loading image")
    valid, msg = validate_image(image_path)
    if not valid:
        step_fail("Loading image", msg)
        sys.exit(1)
    image = load_image(image_path)
    step_done(f"Image loaded ({image.shape[1]}x{image.shape[0]})")
    console.print()

    # Step 2: Face detection
    step_header(2, TOTAL_STEPS, "Detecting faces")
    detector = FaceDetector()
    faces = detector.detect_faces(image)
    if not faces:
        step_fail("Detecting faces", "No usable face detected.")
        sys.exit(1)

    if len(faces) == 1:
        selected_face = faces[0]
        step_done(f"Faces detected: 1, Confidence: {selected_face['confidence']:.1%}")
    else:
        step_done(f"Faces detected: {len(faces)}")
        console.print()
        console.print(f"[bold]{len(faces)} faces detected.[/bold]")
        console.print()
        for i, f in enumerate(faces, 1):
            x1, y1, x2, y2 = f["bbox"]
            console.print(f"  [{i}] Face at ({x1},{y1})-({x2},{y2}) confidence={f['confidence']:.1%}")
        console.print()
        choice = IntPrompt.ask("Select face number", default=1)
        if choice < 1 or choice > len(faces):
            error("Invalid selection.")
            sys.exit(1)
        selected_face = faces[choice - 1]
        console.print(f"  Selected face #{choice}")
    console.print()

    # Step 3: Face embedding
    step_header(3, TOTAL_STEPS, "Generating face embedding")
    encoder = FaceEncoder()
    try:
        embedding, enc_info = encoder.encode_from_detection(image, selected_face["bbox"])
    except Exception as e:
        step_fail("Generating face embedding", str(e))
        sys.exit(1)
    step_done("Model: ArcFace")
    console.print()

    # Step 4: Reverse image search
    step_header(4, TOTAL_STEPS, "Reverse image search")
    crop_path = None
    if FACE_FIRST_SEARCH and not search_full_image:
        crop = crop_face_only(image, selected_face["bbox"], selected_face.get("landmarks"))
        if crop.size > 0:
            crop_path = os.path.join(
                RESULTS_DIR,
                f"face_only_{time.strftime('%Y%m%d_%H%M%S')}.jpg",
            )
            import cv2

            cv2.imwrite(crop_path, crop)
            info("Face-only search: query restricted to the face (background removed).")
        else:
            warn("Face crop empty — searching full image.")
    search_result = search_image(
        image_path, max_results=max_results, face_crop_path=crop_path
    )
    raw_results = search_result["results"]
    step_done(f"Results discovered: {len(raw_results)}")
    info(f"Provider: {search_result['provider']}")
    info(f"Searched with: {search_result['searched_image'].replace(',', ' + ')}")
    if search_result.get("warning"):
        warn(f"Search provider issue: {search_result['warning']}")
    console.print()

    if not raw_results:
        warn("No publicly indexed visual matches found.")
        if search_result.get("warning"):
            warn(
                "This looks like a search-API problem, not a missing person: "
                "check your SerpAPI key/quota (REVERSE_SEARCH_API_KEY in .env) "
                "or retry later."
            )
        _finalize_no_results(image_path)
        return

    # Step 5: Candidate extraction & image analysis
    step_header(5, TOTAL_STEPS, "Processing candidate images")
    candidates = extract_candidates(raw_results)
    processor = CandidateProcessor()
    processed = processor.process(candidates)
    images_analyzed = sum(1 for c in processed if c.get("local_path"))
    faces_found = sum(1 for c in processed if c.get("face_detected"))
    step_done(f"Images analyzed: {images_analyzed}, Faces detected: {faces_found}")
    if processed and faces_found == 0:
        if crop_path and search_result["searched_image"] != "face-crop":
            warn("Face-only query found no public image match.")
            warn("The full-image results also contained no face photos — only product/ad pages.")
        else:
            warn("All results were product/ad pages (e.g. eyeglasses), not photos of this face.")
            warn("These are not the person — all product results are discarded.")
    elif processed:
        info(f"Rejected {len(processed) - faces_found} non-face results (products, ads, logos).")
    console.print()

    # Step 6: Face comparison & ranking
    step_header(6, TOTAL_STEPS, "Face comparison")
    if faces_found == 0:
        warn("No web search returned this person's face anywhere on the public internet.")
        warn(
            "Until a public photo of this face exists, no tool (Google, Lens, PimEyes) "
            "can link this image to a social profile automatically."
        )
        step_done("(no faces to compare)")
        ranked = []
    else:
        ranked = rank_candidates(embedding, processed)
        step_done()
    console.print()

    if ranked:
        match_table(ranked[:10])
    elif faces_found > 0:
        warn("No candidate faces exceeded the similarity threshold.")
    console.print()

    # Step 7: Extract social media profiles (face-matching results only)
    step_header(7, TOTAL_STEPS, "Extracting social media profiles")
    face_results = [c for c in processed if c.get("face_detected")]
    social_profiles = extract_social_profiles(face_results)
    _JUNK = {
        "groups", "tag", "tags", "popular", "ideas", "people", "pin", "pins",
        "topic", "topics", "orgs", "post", "posts", "me", "home", "explore",
        "discover", "collections", "boards", "s", "feed", "featured", "search",
        "login", "signup", "status", "channel", "channels", "pages", "page",
        "account", "accounts", "settings", "notifications", "messages",
        "marketplace", "marketplaceapm", "marketplacevideos", "photo", "photos",
    }
    _PRODUCT_DOMAINS = {
        "selecteyewear.com", "smartbuyglasses.com", "tomfordfashion.com",
        "andreopticas.com", "fashionopticaldallas.com", "coolframes.com",
        "designerframesoutlet.com", "specsavers.com", "oakley.com", "firmoo.com",
        "gentseyewear.com", "neweraeyecare.com", "ebay.com", "farfetch.com",
    }
    _PRODUCT_DOMAIN_HINTS = ("eyewear", "glasses", "optical", "lens", "frames", "shop")
    from urllib.parse import urlparse as _urlparse

    filtered_profiles: dict[str, set] = {}
    for plat, urls in social_profiles.items():
        for u in urls:
            handle = u.rstrip("/").split("/")[-1].lstrip("@")
            domain = _urlparse(u).netloc.lower()
            if handle.lower() in _JUNK or handle.lower().startswith("marketplace."):
                continue
            if domain in _PRODUCT_DOMAINS:
                continue
            if any(h in domain for h in _PRODUCT_DOMAIN_HINTS):
                continue
            filtered_profiles.setdefault(plat, set()).add(u)
    social_profiles = {p: sorted(u) for p, u in filtered_profiles.items()}
    profile_count = sum(len(v) for v in social_profiles.values())

    # Subject name: user-supplied (--name) wins; otherwise infer from the
    # titles of pages that actually contained a matched face. Name-based
    # discovery guards against product names: it only searches a name when
    # (a) a face really matched, or (b) the user supplied the identity.
    from search.social_discovery import discover_profiles_by_name, _extract_name_from_titles

    subject_name = known_name.strip()
    inferred = False
    if not subject_name and raw_results:
        subject_name = _extract_name_from_titles(raw_results)
        inferred = bool(subject_name)

    if not subject_name and not face_results and not social_profiles:
        subject_name = _prompt_subject_name()

    if subject_name:
        seen_urls = set()
        for urls in social_profiles.values():
            seen_urls.update(urls)
        for r in face_results:
            if r.get("url"):
                seen_urls.add(r["url"])
        if known_name.strip():
            info(f"Searching social platforms for (user-supplied name): {subject_name}")
        elif inferred:
            info(f"Searching social platforms for: {subject_name}")
        discovered = discover_profiles_by_name(subject_name, seen_urls)
        for plat, urls in discovered.items():
            social_profiles.setdefault(plat, []).extend(u for u in urls if u not in social_profiles.get(plat, []))
        disp_error = getattr(discover_profiles_by_name, "last_error", "")
        if not discovered and disp_error:
            warn(f"Social discovery was blocked: {disp_error}")

        # Name-aware filtering: drop off-topic handles (a random saved tweet
        # like JFowlerESPN when looking for "Elon Musk") and dedupe impersonator
        # accounts that mirror one base handle with numeric suffixes (the
        # elonmusk.1723803 pattern). Keeps the cleanest profile per base.
        _NumericSuffix = re.compile(r"[.\-_]\d{4,}.*$")
        tokens = {w.lower() for w in re.split(r"\W+", subject_name) if len(w) >= 3}
        cleaned: dict[str, list[str]] = {}
        for plat, urls in social_profiles.items():
            per_base: dict[str, list[str]] = {}
            for u in urls:
                handle = u.rstrip("/").split("/")[-1].lstrip("@")
                base = (_NumericSuffix.sub("", handle).lower()
                        .replace("_", "").replace("-", "").replace(".", ""))
                if tokens and not any(t in base for t in tokens):
                    continue
                if handle.lower() in _JUNK:
                    continue
                clean = not _NumericSuffix.search(handle)
                bucket = per_base.setdefault(base or handle.lower(), [])
                bucket.append((u, clean))
            flat: list[tuple[str, bool]] = []
            for bucket in per_base.values():
                bucket.sort(key=lambda x: (not x[1], len(x[0])))
                flat.append(bucket[0])
            flat.sort(key=lambda x: (not x[1], len(x[0])))
            cleaned[plat] = [u for u, _ in flat[:3]]
        social_profiles = {p: sorted(u) for p, u in cleaned.items() if u}
        profile_count = sum(len(v) for v in social_profiles.values())
    elif face_results:
        warn("Named social discovery skipped (subject name not inferable).")
    step_done(f"Profiles found: {profile_count}")
    if social_profiles:
        _print_profiles(social_profiles)
    elif not face_results:
        warn("No web image matched a face — no profiles to attribute.")
        if not known_name.strip():
            warn(
                "Tip: if you know who this is, run with --name \"Person's Name\" "
                "to search their socials directly."
            )
    else:
        warn("No social media profile links found in face-matching results.")
    console.print()

    # Face-to-profile verification: compare this photo's face against each
    # discovered profile's avatar/photo to confirm the person behind the link.
    profile_face_checks = []
    if social_profiles and FACE_PROFILE_VERIFY:
        step_header(7, TOTAL_STEPS, "Verifying faces on profile pages")
        from search.profile_face import verify_profile_faces

        profile_face_checks = verify_profile_faces(
            embedding, social_profiles, encoder, detector, max_checks=12
        )
        matched = [c for c in profile_face_checks if c["status"] == "matched"]
        step_done(
            f"Profiles checked: {len(profile_face_checks)}, "
            f"face matches: {len(matched)}"
        )
        if profile_face_checks:
            face_verify_table(profile_face_checks)
        else:
            warn("Could not fetch any profile avatar to compare.")
        console.print()

    # Step 8: Hash generation
    step_header(8, TOTAL_STEPS, "Generating verification hash")
    input_hash = compute_file_hash(image_path)
    verification = VerificationResult(input_hash, ranked)
    verification.faces_detected = len(faces)
    verification.social_profiles = social_profiles
    verification.profile_face_checks = profile_face_checks
    step_done(f"SHA-256: {verification.record_hash[:16]}...")
    console.print()

    # Step 9: Blockchain recording
    step_header(9, TOTAL_STEPS, "Recording blockchain proof")
    client = BlockchainClient()
    if client.is_ready():
        if ranked:
            top = ranked[0]
            candidate_hash = top.get("url", "")
            similarity = top.get("face_similarity", 0.0)
            matched = True
        else:
            candidate_hash = ""
            similarity = 0.0
            matched = False
        result = client.record_verification(
            verification.record_hash,
            input_hash,
            candidate_hash,
            similarity,
            matched,
        )
        if result["success"]:
            verification.set_blockchain("sepolia", result["transaction_hash"])
            step_done()
            blockchain_result("sepolia", result["transaction_hash"])
        else:
            step_fail("Blockchain recording", result["error"])
            warn("Verification completed. Blockchain recording failed.")
    else:
        if not client.is_ready():
            warn("Blockchain client not configured. Skipping on-chain recording.")
            info("Set PRIVATE_KEY and CONTRACT_ADDRESS in .env to enable.")
        step_done("(skipped)")
    console.print()

    # Save result
    _save_result(verification)
    completion_banner()


def _finalize_no_results(image_path: str):
    input_hash = compute_file_hash(image_path)
    verification = VerificationResult(input_hash, [])
    verification.faces_detected = 0
    _save_result(verification)
    completion_banner()


def _print_profiles(social_profiles: dict):
    console.print()
    console.print("[bold cyan]  SOCIAL MEDIA PROFILES (copy any link into your browser)[/bold cyan]")
    console.print()
    idx = 0
    for platform in sorted(social_profiles):
        for url in social_profiles[platform]:
            idx += 1
            console.print(f"   [bold]{platform:<12}[/bold] {url}")
    console.print()


def face_verify_table(checks: list[dict]):
    console.print()
    console.print("[bold yellow]  FACE MATCH ON PROFILE PAGES — is the face in your photo the same "
                  "person on these profiles?[/bold yellow]")
    console.print()
    for c in checks[:12]:
        sim = c.get("face_similarity")
        if sim is None:
            sim_text = "not measured"
        else:
            sim_text = f"{sim:.1%}"
        cls = c.get("classification") or "--"
        status = c.get("status", "")
        if sim is not None and sim >= 0.90:
            mark = "[green]MATCH[/green]"
        elif sim is not None and sim >= 0.80:
            mark = "[yellow]LIKELY[/yellow]"
        elif sim is not None:
            mark = "[red]unlikely[/red]"
        else:
            mark = "[dim]--[/dim]"
        console.print(
            f"   {mark}  {sim_text:<12} {cls:<6} {c.get('platform',''):<12} "
            f"{c.get('url','')}  [{status}]"
        )
    console.print()


def _save_result(verification: VerificationResult):
    results_dir = RESULTS_DIR
    results_dir.mkdir(exist_ok=True)
    existing = list(results_dir.glob("result_*.json"))
    next_num = len(existing) + 1
    save_path = results_dir / f"result_{next_num:03d}.json"

    with open(save_path, "w") as f:
        json.dump(verification.to_dict(), f, indent=2)

    console.print(f"\n  [dim]Results saved to: {save_path}[/dim]\n")


def run_verify(record_path: str):
    record_path, mapped = resolve_image_path(record_path)
    if mapped:
        info(f"Mapped Windows path to: {record_path}")

    with open(record_path) as f:
        data = json.load(f)

    console.print("[bold]Verification Record:[/bold]")
    console.print(json.dumps(data, indent=2))
    console.print()

    client = BlockchainClient()
    if not client.is_ready():
        warn("Blockchain client not configured. Cannot verify on-chain.")
        return

    record_hash = data.get("verification_hash", "")
    result = client.get_verification(record_hash)
    if result:
        console.print("[bold green]On-chain record found:[/bold green]")
        console.print(json.dumps(result, indent=2))
    else:
        warn("No on-chain record found for this hash.")


def run_blockchain_lookup(record_hash: str):
    client = BlockchainClient()
    if not client.is_ready():
        warn("Blockchain client not configured.")
        return

    result = client.get_verification(record_hash)
    if result:
        console.print("[bold green]Verification record:[/bold green]")
        console.print(json.dumps(result, indent=2))
    else:
        warn("No record found for this hash.")


def _join_spaced(arg_value):
    return " ".join(arg_value)


def main():
    parser = argparse.ArgumentParser(
        prog="facelens",
        description="FaceLens CLI — AI Face Search & Verification System",
    )
    subparsers = parser.add_subparsers(dest="command")

    search_parser = subparsers.add_parser("search", help="Search for a face in public web content")
    search_parser.add_argument(
        "--image",
        nargs="+",
        required=True,
        help="Path to input image (paths with spaces may be quoted, or passed unquoted)",
    )
    search_parser.add_argument("--limit", type=int, default=20, help="Maximum results to process")
    search_parser.add_argument(
        "--search-full-image",
        action="store_true",
        help="Search the full image instead of the face-only masked crop (default)",
    )
    search_parser.add_argument(
        "--name",
        default="",
        help="Person's name to search social platforms for (skips name inference)",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify a saved result on blockchain")
    verify_parser.add_argument(
        "--record",
        nargs="+",
        required=True,
        help="Path to result JSON file (paths with spaces may be quoted, or passed unquoted)",
    )

    blockchain_parser = subparsers.add_parser("blockchain", help="Look up a blockchain record")
    blockchain_parser.add_argument("--hash", required=True, help="Record hash to look up")

    args = parser.parse_args()

    if args.command == "search":
        run_search(
            _join_spaced(args.image),
            args.limit,
            args.search_full_image,
            known_name=args.name,
        )
    elif args.command == "verify":
        run_verify(_join_spaced(args.record))
    elif args.command == "blockchain":
        run_blockchain_lookup(args.hash)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
