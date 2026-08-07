"""Unit tests for validate-scorm.py package checks."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

# Loaded once by tests/preflight/conftest.py (hyphenated script filename)
import validate_scorm

validate = validate_scorm.validate


VALID_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="sample-manifest" version="1.0"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="org-sample">
    <organization identifier="org-sample">
      <title>Sample Course</title>
      <item identifier="item-sample" identifierref="res-sample">
        <title>Sample Course</title>
        <adlcp:masteryscore>100</adlcp:masteryscore>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res-sample" type="webcontent"
              adlcp:scormtype="sco" href="index.html">
      <file href="index.html"/>
      <file href="assets/css/course.css"/>
    </resource>
  </resources>
</manifest>
"""


def make_zip(tmp_path: Path, files: dict[str, str]) -> Path:
    zip_path = tmp_path / "package.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return zip_path


def valid_files() -> dict[str, str]:
    return {
        "imsmanifest.xml": VALID_MANIFEST,
        "index.html": "<html></html>",
        "assets/css/course.css": "body {}",
    }


class TestValidateScorm:
    def test_valid_package_passes(self, tmp_path):
        zip_path = make_zip(tmp_path, valid_files())
        assert validate(zip_path) == []

    def test_missing_zip_reports_error(self, tmp_path):
        errors = validate(tmp_path / "nope.zip")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_not_a_zip_reports_error(self, tmp_path):
        bogus = tmp_path / "package.zip"
        bogus.write_text("not a zip")
        errors = validate(bogus)
        assert len(errors) == 1
        assert "Not a valid zip" in errors[0]

    def test_manifest_missing_from_root(self, tmp_path):
        files = valid_files()
        files["nested/imsmanifest.xml"] = files.pop("imsmanifest.xml")
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("imsmanifest.xml missing from zip root" in e for e in errors)
        assert any("nested/imsmanifest.xml" in e for e in errors)

    def test_index_html_missing(self, tmp_path):
        files = valid_files()
        del files["index.html"]
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("index.html missing" in e for e in errors)

    def test_malformed_manifest_xml(self, tmp_path):
        files = valid_files()
        files["imsmanifest.xml"] = "<manifest><unclosed>"
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("not well-formed XML" in e for e in errors)

    def test_manifest_with_doctype_rejected(self, tmp_path):
        files = valid_files()
        files["imsmanifest.xml"] = (
            '<?xml version="1.0"?>\n'
            '<!DOCTYPE manifest [<!ENTITY x SYSTEM "file:///etc/passwd">]>\n'
            + VALID_MANIFEST.split("?>", 1)[1]
        )
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("DTD or entity declaration" in e for e in errors)

    def test_wrong_schema_version(self, tmp_path):
        files = valid_files()
        files["imsmanifest.xml"] = VALID_MANIFEST.replace(
            "<schemaversion>1.2</schemaversion>",
            "<schemaversion>2004 3rd Edition</schemaversion>",
        )
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("schemaversion must be '1.2'" in e for e in errors)

    def test_missing_mastery_score(self, tmp_path):
        files = valid_files()
        files["imsmanifest.xml"] = VALID_MANIFEST.replace(
            "<adlcp:masteryscore>100</adlcp:masteryscore>", ""
        )
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("masteryscore" in e for e in errors)

    def test_manifest_references_missing_file(self, tmp_path):
        files = valid_files()
        del files["assets/css/course.css"]
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("missing file: assets/css/course.css" in e for e in errors)

    def test_pages_directory_rejected(self, tmp_path):
        files = valid_files()
        files["pages/lesson-01.html"] = "<html></html>"
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("pages/ directory" in e for e in errors)

    def test_extra_root_html_rejected(self, tmp_path):
        files = valid_files()
        files["lesson-02.html"] = "<html></html>"
        zip_path = make_zip(tmp_path, files)
        errors = validate(zip_path)
        assert any("extra root HTML" in e and "lesson-02.html" in e for e in errors)
