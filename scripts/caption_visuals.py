#!/usr/bin/env python3
"""OPTIONAL: caption extracted course visuals with Amazon Bedrock vision.

Generates a structured caption per image (caption text, concepts, visual
type, sensitivity flags, thumbnail readability) to seed each module's
``visuals/INDEX.md`` catalog. This script is entirely optional: the
INDEX.md workflow works just as well with hand-written or agent-written
captions (see the power's ``source-intake.md`` steering file). Nothing
else in the pipeline depends on it.

Requirements (all optional-tier):

- boto3: ``pip install boto3==1.42.54``
- AWS credentials with Bedrock model access in the chosen region
- A vision-capable Bedrock model id (e.g. an Anthropic Claude model)

Usage:
    python3 scripts/caption_visuals.py <visuals-dir> <cache-dir> <model-id> [--region us-east-1]

Output: one JSON object per image to stdout.
Cached responses are stored under <cache-dir> keyed by image sha256, so
re-runs after curation don't re-invoke Bedrock for unchanged images.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import sys

PROMPT = """You are curating a visual asset library for an e-learning course.

For the attached image, produce a JSON object with these fields:

{
  "caption": "one sentence, factual, describes what is visible. 10-25 words.",
  "concepts": ["list of 1-4 key concepts or topics this visual illustrates, lowercase"],
  "visual_type": "one of: title_slide, agenda, diagram, data_chart, heatmap, ui_screenshot, photo, text_slide, table, other",
  "has_sensitive_content": true_or_false,
  "sensitive_elements": ["list specific items if has_sensitive_content is true; e.g. customer name visible top-right. Empty list otherwise."],
  "readability_at_thumbnail": "good | fair | poor - would this be readable at 320x180?",
  "confidence": 0.0_to_1.0
}

Return ONLY the JSON object, no surrounding text. Be factual - do not infer content that isn't visible."""


def caption_one(path, cache_dir, model_id, region="us-east-1"):
    import boto3

    img_bytes = pathlib.Path(path).read_bytes()
    img_hash = hashlib.sha256(img_bytes).hexdigest()[:16]
    cache_file = cache_dir / f"{img_hash}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        data["_source"] = str(path)
        return data

    br = boto3.client("bedrock-runtime", region_name=region)
    ext = pathlib.Path(path).suffix.lstrip(".").lower()
    if ext == "jpg":
        ext = "jpeg"

    resp = br.converse(
        modelId=model_id,
        messages=[{
            "role": "user",
            "content": [
                {"image": {"format": ext, "source": {"bytes": img_bytes}}},
                {"text": PROMPT},
            ],
        }],
        inferenceConfig={"maxTokens": 500, "temperature": 0.1},
    )
    text = resp["output"]["message"]["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text.strip())
    data["_source"] = str(path)
    cache_file.write_text(json.dumps(data, indent=2))
    return data


def caption_many(image_paths, cache_dir, model_id, region="us-east-1", concurrency=4):
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(caption_one, p, cache_dir, model_id, region): p for p in image_paths}
        for f in concurrent.futures.as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                print(f"FAILED {futures[f]}: {e}", file=sys.stderr)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("visuals_dir", type=pathlib.Path, help="Directory of .png/.jpg images (searched recursively)")
    parser.add_argument("cache_dir", type=pathlib.Path, help="Cache directory for Bedrock responses")
    parser.add_argument("model_id", help="Vision-capable Bedrock model id")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    args = parser.parse_args()

    try:
        import boto3  # noqa: F401
    except ImportError:
        print(
            "ERROR: boto3 not installed (this optional script calls Amazon Bedrock).\n"
            "Install with: pip install boto3==1.42.54\n"
            "Or skip this script entirely and write INDEX.md captions by hand.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    paths = sorted(args.visuals_dir.rglob("*.png")) + sorted(args.visuals_dir.rglob("*.jpg"))
    if not paths:
        print(f"ERROR: no .png or .jpg images found under {args.visuals_dir}", file=sys.stderr)
        raise SystemExit(1)
    out = caption_many(paths, args.cache_dir, args.model_id, region=args.region)
    out.sort(key=lambda r: r["_source"])
    for r in out:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
