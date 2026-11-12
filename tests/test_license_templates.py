"""The license templates the skill copies must exist and carry only known placeholders."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "templates" / "licenses"
INDEX = (ROOT / "README.md").read_text(encoding="utf-8")


def referenced_templates():
    paths = set(re.findall(r"`((?:open-source|docs-assets|dco|paid)/[^`]+)`", INDEX))
    assert paths, "templates/licenses/README.md lists no templates"
    return sorted(paths)


def test_every_listed_template_exists():
    missing = [p for p in referenced_templates() if not (ROOT / p).is_file()]
    assert not missing, missing


def test_every_template_is_listed():
    listed = set(referenced_templates())
    on_disk = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and p.name != "README.md"}
    assert on_disk == listed


def test_simple_licenses_have_only_holder_and_year_placeholders():
    for name in ["open-source/MIT.txt", "open-source/BSD-2-Clause.txt", "open-source/BSD-3-Clause.txt"]:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert set(re.findall(r"<[A-Z ]+>", text)) == {"<YEAR>", "<COPYRIGHT HOLDER>"}, name


def test_standard_texts_have_no_placeholders():
    for name in ["open-source/Apache-2.0.txt", "docs-assets/CC-BY-4.0.txt", "docs-assets/CC0-1.0.txt",
                 "paid/Elastic-2.0.txt", "paid/PolyForm-Noncommercial-1.0.0.md", "dco/DCO"]:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"<[A-Z][A-Z ]+>", text), name
