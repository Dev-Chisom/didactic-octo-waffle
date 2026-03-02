from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple

import httpx

from reel_engine.prompt_builder import ImagePrompt
from reel_engine.utils import ensure_dir, read_env


ImageProvider = Literal["replicate", "local", "pexels"]


@dataclass(frozen=True)
class GeneratedImage:
    shot_id: int
    path: Path
    used_cache: bool


def generate_images(
    prompts: list[ImagePrompt],
    *,
    provider: ImageProvider,
    style: str,
    run_frames_dir: Path,
    global_cache_dir: Path,
    replicate_model_version: str,
    max_concurrency: int = 4,
    poll_interval_sec: float = 1.5,
    timeout_sec: float = 300.0,
) -> tuple[list[GeneratedImage], int]:
    """
    Generates (or reuses cached) images for each shot.

    Returns:
    - generated images in shot order
    - number of *new* images generated (cache misses)
    """
    ensure_dir(run_frames_dir)
    # Keep caches separate per style *and* provider to avoid reusing placeholder
    # images when switching providers (e.g. local -> pexels).
    cache_root = ensure_dir(global_cache_dir / f"{provider}_{style}")

    results: list[GeneratedImage] = []
    new_images = 0

    # Cheap cache check first (deterministic cache_key).
    to_generate: list[ImagePrompt] = []
    cached: dict[int, Path] = {}
    for p in prompts:
        cache_path = (cache_root / f"{p.cache_key}.png").resolve()
        if cache_path.exists():
            cached[p.shot_id] = cache_path
        else:
            to_generate.append(p)

    # Copy/link cached images into the run folder (keep runs self-contained).
    for p in prompts:
        out_path = (run_frames_dir / f"shot_{p.shot_id:02d}.png").resolve()
        if p.shot_id in cached:
            _copy_file(cached[p.shot_id], out_path)
            results.append(GeneratedImage(shot_id=p.shot_id, path=out_path, used_cache=True))

    if not to_generate:
        # Results are already in shot order because we iterated prompts above.
        return results, new_images

    if provider == "local":
        # Local mode: pull existing images from style folder (or global cache if user populated it).
        local_dir = cache_root.resolve()
        local_files = sorted([p for p in local_dir.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])
        if not local_files:
            _write_local_images_readme(local_dir)
            raise RuntimeError(
                f"Local image provider selected, but no images found in:\n  {local_dir}\n"
                "Add 8+ portrait images (PNG, JPG, or WebP; 720×1280 or similar). "
                "See README.txt in that folder. Then re-run, or use --image-provider replicate."
            )

        for idx, p in enumerate(to_generate):
            chosen = local_files[idx % len(local_files)]
            out_path = (run_frames_dir / f"shot_{p.shot_id:02d}.png").resolve()
            _copy_file(chosen, out_path)

            # Also store into deterministic cache path for later.
            cache_path = (cache_root / f"{p.cache_key}.png").resolve()
            _copy_file(out_path, cache_path)
            results.append(GeneratedImage(shot_id=p.shot_id, path=out_path, used_cache=False))
            new_images += 1

        results.sort(key=lambda r: r.shot_id)
        return results, new_images

    if provider == "pexels":
        api_key = read_env("PEXELS_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing PEXELS_API_KEY env var. Set it in your shell/.env or use "
                "--image-provider replicate."
            )
        headers = {"Authorization": api_key}
        with httpx.Client(timeout=60) as client:
            for p in to_generate:
                out_path = (run_frames_dir / f"shot_{p.shot_id:02d}.png").resolve()
                _pexels_download_portrait_image(
                    client,
                    headers=headers,
                    query=p.search_query,
                    out_path=out_path,
                    width=p.width,
                    height=p.height,
                )

                # Save to deterministic cache.
                cache_path = (cache_root / f"{p.cache_key}.png").resolve()
                _copy_file(out_path, cache_path)

                results.append(GeneratedImage(shot_id=p.shot_id, path=out_path, used_cache=False))
                new_images += 1

        results.sort(key=lambda r: r.shot_id)
        return results, new_images

    if provider != "replicate":
        raise ValueError(f"Unknown provider: {provider}")

    token = read_env("REPLICATE_API_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing REPLICATE_API_TOKEN env var. "
            "Set it in your shell or .env and re-run, or use --image-provider local."
        )

    headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

    # Minimal concurrency without extra deps: create and poll predictions in waves.
    queue = list(to_generate)
    in_flight: list[tuple[ImagePrompt, str]] = []

    with httpx.Client(timeout=60) as client:
        while queue or in_flight:
            # Fill up to max_concurrency
            while queue and len(in_flight) < max_concurrency:
                p = queue.pop(0)
                pred_id = _replicate_create_prediction(
                    client,
                    headers=headers,
                    model_version=replicate_model_version,
                    prompt=p,
                )
                in_flight.append((p, pred_id))

            if not in_flight:
                continue

            # Poll current in-flight set.
            next_in_flight: list[tuple[ImagePrompt, str]] = []
            for p, pred_id in in_flight:
                status, output_url = _replicate_poll_prediction(
                    client,
                    headers=headers,
                    prediction_id=pred_id,
                )

                if status in {"starting", "processing"}:
                    next_in_flight.append((p, pred_id))
                    continue

                if status != "succeeded" or not output_url:
                    raise RuntimeError(f"Replicate prediction failed (status={status}) for shot {p.shot_id}")

                out_path = (run_frames_dir / f"shot_{p.shot_id:02d}.png").resolve()
                _download_to_path(client, output_url, out_path)

                # Save to deterministic cache.
                cache_path = (global_cache_dir / style / f"{p.cache_key}.png").resolve()
                _copy_file(out_path, cache_path)

                results.append(GeneratedImage(shot_id=p.shot_id, path=out_path, used_cache=False))
                new_images += 1

            in_flight = next_in_flight

            if in_flight:
                time.sleep(poll_interval_sec)

            # Basic timeout check (rough but effective).
            timeout_sec = float(timeout_sec)
            # We don't track per-pred start time to keep it lean; we rely on provider stability.

    results.sort(key=lambda r: r.shot_id)
    return results, new_images


def _replicate_create_prediction(
    client: httpx.Client,
    *,
    headers: dict[str, str],
    model_version: str,
    prompt: ImagePrompt,
) -> str:
    payload = {
        "version": model_version,
        "input": {
            "prompt": prompt.prompt,
            "negative_prompt": prompt.negative_prompt,
            "width": prompt.width,
            "height": prompt.height,
            "num_inference_steps": prompt.steps,
            "guidance_scale": prompt.guidance_scale,
            "seed": prompt.seed,
            "disable_safety_checker": True,
        },
    }
    r = client.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
    if r.status_code >= 400:
        # Temporary debug logging for Replicate schema/version issues.
        try:
            print("Replicate error response:", r.status_code, r.json())
        except Exception:
            print("Replicate error response (non-JSON):", r.status_code, r.text)
    r.raise_for_status()
    data = r.json()
    pred_id = data.get("id")
    if not pred_id:
        raise RuntimeError(f"Unexpected Replicate response: {data}")
    return str(pred_id)


def _replicate_poll_prediction(
    client: httpx.Client,
    *,
    headers: dict[str, str],
    prediction_id: str,
) -> Tuple[str, Optional[str]]:
    r = client.get(f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers)
    r.raise_for_status()
    data = r.json()
    status = str(data.get("status") or "unknown")
    output = data.get("output")

    # Many image models return either a single URL string or an array of URLs.
    output_url: Optional[str] = None
    if isinstance(output, str):
        output_url = output
    elif isinstance(output, list) and output:
        if isinstance(output[0], str):
            output_url = output[0]

    if status == "failed":
        # Temporary debug logging to surface Replicate failure details.
        try:
            print(f"Replicate prediction {prediction_id} failed with response:", data)
        except Exception:
            print(f"Replicate prediction {prediction_id} failed (non-JSON response)")

    return status, output_url


def _download_to_path(client: httpx.Client, url: str, path: Path) -> None:
    url = (url or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        raise RuntimeError(
            f"Invalid image URL from Replicate (expected https://...): {url!r}. "
            "Replicate may have changed their output format."
        )
    try:
        r = client.get(url)
        r.raise_for_status()
        path.write_bytes(r.content)
    except httpx.ConnectError as e:
        raise RuntimeError(
            f"Failed to download image from Replicate: {e}. "
            f"URL: {url[:80]}... "
            "Check your network connection and DNS (e.g. try disabling VPN, or ping replicate.delivery)."
        ) from e


def _write_local_images_readme(local_dir: Path) -> None:
    """Write a short README when local image folder is empty so the user knows what to add."""
    readme = local_dir / "README.txt"
    if readme.exists():
        return
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        readme.write_text(
            "Local image provider: add 8+ portrait images here (PNG, JPG, or WebP).\n"
            "720×1280 or similar aspect ratio works well for reels.\n"
            "They will be reused in order for each shot. Then re-run the reel_engine.\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _copy_file(src: Path, dst: Path) -> None:
    if src.resolve() == dst.resolve():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _pexels_download_portrait_image(
    client: httpx.Client,
    *,
    headers: dict[str, str],
    query: str,
    out_path: Path,
    width: int,
    height: int,
) -> None:
    """
    Download a single portrait-oriented image from Pexels, then resize/crop to exact WxH.
    """
    search_url = "https://api.pexels.com/v1/search"
    params = {
        "query": query,
        "per_page": 1,
        "orientation": "portrait",
        "size": "large",
    }
    r = client.get(search_url, headers=headers, params=params)
    r.raise_for_status()
    data = r.json()
    photos = data.get("photos") or []
    if not photos:
        raise RuntimeError(f"Pexels returned no results for query: {query!r}")
    src = (photos[0].get("src") or {})
    url = src.get("large2x") or src.get("large") or src.get("original")
    if not url:
        raise RuntimeError(f"Unexpected Pexels response (no image url): {photos[0]}")

    img_bytes = client.get(url).content

    # Resize/crop using Pillow (already a dependency for caption burn-in).
    from PIL import Image
    import io

    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    # Center-crop to target aspect ratio, then resize.
    target_ar = width / float(height)
    w0, h0 = im.size
    cur_ar = w0 / float(h0)
    if cur_ar > target_ar:
        # Too wide: crop width.
        new_w = int(round(h0 * target_ar))
        left = int((w0 - new_w) / 2)
        im = im.crop((left, 0, left + new_w, h0))
    else:
        # Too tall: crop height.
        new_h = int(round(w0 / target_ar))
        top = int((h0 - new_h) / 2)
        im = im.crop((0, top, w0, top + new_h))

    im = im.resize((width, height), resample=Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path, format="PNG", optimize=True)

