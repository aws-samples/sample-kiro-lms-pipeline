#!/usr/bin/env python3
"""
Validate a built SCORM 1.2 package zip.

Checks that the zip is structurally sound before it goes anywhere near an
LMS:

1. ``imsmanifest.xml`` sits at the zip root (not inside a subdirectory).
2. ``index.html`` sits at the zip root (single-page SCO entry point).
3. The manifest parses as XML.
4. The manifest declares SCORM 1.2 (``<schemaversion>1.2</schemaversion>``).
5. The manifest declares an ``<adlcp:masteryscore>`` on the SCO item.
   Without it many LMSs treat any exit as completion.
6. Every ``<file href="...">`` referenced by the manifest exists in the zip.
7. No per-page HTML files exist (``pages/`` directory or multiple root
   ``.html`` files). The single-page SCO architecture requires exactly one
   HTML entry point so LMSInitialize is called once per session.

Usage:
    python scripts/validate-scorm.py path/to/package.zip

Exits non-zero with a report on stderr when any check fails.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import defusedxml.ElementTree as ET

ADLCP_NS = "http://www.adlnet.org/xsd/adlcp_rootv1p2"
IMSCP_NS = "http://www.imsproject.org/xsd/imscp_rootv1p1p2"


def validate(zip_path: Path) -> list[str]:
    """Run all checks against the zip; return a list of error messages."""
    errors: list[str] = []

    if not zip_path.is_file():
        return [f"Package not found: {zip_path}"]

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        return [f"Not a valid zip file: {zip_path} ({exc})"]

    with zf:
        names = set(zf.namelist())

        # 1. Manifest at the zip root.
        if "imsmanifest.xml" not in names:
            nested = [n for n in names if n.endswith("imsmanifest.xml")]
            hint = f" (found nested at {nested[0]})" if nested else ""
            errors.append(f"imsmanifest.xml missing from zip root{hint}")
            return errors

        # 2. index.html at the zip root.
        if "index.html" not in names:
            errors.append("index.html missing from zip root")

        # 3. Manifest parses as XML. Reject DTD/entity declarations up
        #    front: the stdlib parser would expand them (XXE / entity
        #    bombs), and no valid SCORM 1.2 manifest needs a DTD.
        manifest_bytes = zf.read("imsmanifest.xml")
        if b"<!DOCTYPE" in manifest_bytes or b"<!ENTITY" in manifest_bytes:
            errors.append(
                "imsmanifest.xml contains a DTD or entity declaration; "
                "refusing to parse it"
            )
            return errors
        try:
            manifest_root = ET.fromstring(manifest_bytes)
        except ET.ParseError as exc:
            errors.append(f"imsmanifest.xml is not well-formed XML: {exc}")
            return errors

        # 4. SCORM 1.2 schema version.
        version = manifest_root.find(f".//{{{IMSCP_NS}}}schemaversion")
        if version is None or (version.text or "").strip() != "1.2":
            found = version.text.strip() if version is not None and version.text else "none"
            errors.append(f"Manifest schemaversion must be '1.2' (found: {found})")

        # 5. Mastery score present on the SCO item.
        mastery = manifest_root.find(f".//{{{ADLCP_NS}}}masteryscore")
        if mastery is None:
            errors.append(
                "Manifest is missing <adlcp:masteryscore>; without it many "
                "LMSs treat any exit from the SCO as completion"
            )

        # 6. Every file referenced by the manifest exists in the zip.
        for file_el in manifest_root.iter(f"{{{IMSCP_NS}}}file"):
            href = file_el.get("href")
            if href and href not in names:
                errors.append(f"Manifest references missing file: {href}")

        # 7. Single-page SCO: exactly one root HTML file, no pages/ dir.
        if any(n.startswith("pages/") for n in names):
            errors.append(
                "Found pages/ directory; the single-page SCO must inline all "
                "lesson bodies into index.html"
            )
        root_html = [n for n in names if "/" not in n and n.endswith(".html")]
        extra_html = sorted(set(root_html) - {"index.html"})
        if extra_html:
            errors.append(
                "Found extra root HTML files (single-page SCO expects only "
                f"index.html): {', '.join(extra_html)}"
            )

    return errors


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} path/to/package.zip", file=sys.stderr)
        sys.exit(2)

    zip_path = Path(sys.argv[1])
    errors = validate(zip_path)

    if errors:
        print(f"FAIL: {zip_path}", file=sys.stderr)
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {zip_path} is a valid single-page SCORM 1.2 package")


if __name__ == "__main__":
    main()
