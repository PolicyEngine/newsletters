"""Tests for scripts/lint-newsletters.sh."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lint-newsletters.sh"
SHA = "43919d6d0b6509a0407203fa7f268e90f9122968"
NEW = "2026-11-03-uk.html"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")


def image(ref, quote='"'):
    """Return an <img> tag loading a newsletters image at the given ref."""
    url = (
        "https://raw.githubusercontent.com/PolicyEngine/newsletters/"
        f"{ref}/assets/images/chart.png"
    )
    return f"<img src={quote}{url}{quote} alt={quote}Chart{quote}>"


def run_lint(tmp_path, files, env=None):
    """Write the files to tmp_path/editions and lint them there."""
    editions = tmp_path / "editions"
    editions.mkdir()
    for name, html in files.items():
        (editions / name).write_text(f"<html><body>\n{html}\n</body></html>\n")
    run_env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    run_env.update(env or {})
    return subprocess.run(
        [BASH, str(SCRIPT)],
        cwd=tmp_path,
        env=run_env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("ref", [SHA, SHA.upper()])
def test_new_edition_pinned_to_sha_passes_without_warning(tmp_path, ref):
    result = run_lint(tmp_path, {NEW: image(ref)})
    assert result.returncode == 0
    assert "WARNING" not in result.stdout


@pytest.mark.parametrize("ref", ["main", "master", "2026-11-03-uk", SHA[:7]])
def test_new_edition_not_pinned_warns_but_passes(tmp_path, ref):
    result = run_lint(tmp_path, {NEW: image(ref)})
    assert result.returncode == 0
    assert "WARNING" in result.stdout
    url = f"https://raw.githubusercontent.com/PolicyEngine/newsletters/{ref}/"
    assert f"\n2:{url}" in result.stdout


UNPINNED_URL = "https://raw.githubusercontent.com/PolicyEngine/newsletters/main/assets/images/c.png"
PINNED_URL = UNPINNED_URL.replace("/main/", f"/{SHA}/")


@pytest.mark.parametrize(
    "html, warns",
    [
        (image("main", quote="'"), True),
        (f'<img src = "{UNPINNED_URL}" alt="Chart">', True),
        (f'<img alt="Chart"\nsrc="{UNPINNED_URL}">', True),
        (f'<img src=\n"{UNPINNED_URL}" alt="Chart">', True),
        (f'<img SRC="{UNPINNED_URL}" alt="Chart">', True),
        (f"<img src={UNPINNED_URL} alt=Chart>", True),
        (f'<img data-src="{UNPINNED_URL}" alt="Chart">', False),
        (f"<a href=\"https://example.com/?src='{UNPINNED_URL}'\">Link</a>", False),
        (f"<a title=\"An example src='{UNPINNED_URL}'\">Link</a>", False),
        (f'<img alt="Chart from src=\'{UNPINNED_URL}\'" src="{PINNED_URL}">', False),
        (f'<a href="{UNPINNED_URL}">Link</a>', False),
        (f'<!-- <img src="{UNPINNED_URL}"> -->', False),
    ],
)
def test_warning_reads_src_attributes_as_html(tmp_path, html, warns):
    result = run_lint(tmp_path, {NEW: html})
    assert result.returncode == 0
    assert ("WARNING" in result.stdout) is warns


@pytest.mark.parametrize(
    "name, warns",
    [
        ("2026-09-07-us.html", False),
        ("2026-09-08-us-v2.html", True),
        ("2027-01-01-uk.html", True),
        ("welcome.html", True),
    ],
)
def test_warning_applies_from_the_first_pinned_edition(tmp_path, name, warns):
    result = run_lint(tmp_path, {name: image("main")})
    assert result.returncode == 0
    assert ("WARNING" in result.stdout) is warns


@pytest.mark.parametrize("separator, line", [("\n", 3), (" ", 2)])
def test_warning_lists_only_unpinned_images(tmp_path, separator, line):
    result = run_lint(tmp_path, {NEW: image(SHA) + separator + image("main")})
    assert result.returncode == 0
    assert f"\n{line}:https://raw.githubusercontent.com/" in result.stdout
    assert SHA not in result.stdout


def test_github_actions_annotation(tmp_path):
    result = run_lint(tmp_path, {NEW: image("main")}, env={"GITHUB_ACTIONS": "true"})
    assert result.returncode == 0
    assert f"::warning file=editions/{NEW},line=2::" in result.stdout


def test_missing_python_skips_the_warning(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("grep", "dirname"):
        (bin_dir / tool).symlink_to(shutil.which(tool))
    result = run_lint(tmp_path, {NEW: image("main")}, env={"PATH": str(bin_dir)})
    assert result.returncode == 0, result.stderr
    assert "python3 not found" in result.stdout
    assert "WARNING" not in result.stdout


def test_refs_heads_is_an_error_that_points_to_sha_pinning(tmp_path):
    result = run_lint(tmp_path, {"2024-01-01.html": image("refs/heads/main")})
    assert result.returncode == 1
    assert "full 40-character commit SHA" in result.stdout
    assert "/master/ or /main/" not in result.stdout


VERCEL_LINK = '<a href="https://ballot-measures-2026.vercel.app/us/x">Dashboard</a>'


@pytest.mark.parametrize(
    "name, fails",
    [
        ("2026-10-29-us.html", False),
        ("2026-10-30-us.html", True),
        ("2027-01-01-uk.html", True),
        ("welcome.html", True),
    ],
)
def test_hosting_link_is_an_error_from_30_october_2026(tmp_path, name, fails):
    result = run_lint(tmp_path, {name: VERCEL_LINK})
    assert (result.returncode == 1) is fails
    assert ("hosting address" in result.stdout) is fails
    if fails:
        assert "\n2:ballot-measures-2026.vercel.app" in result.stdout


def test_hosting_link_github_actions_annotation(tmp_path):
    result = run_lint(tmp_path, {NEW: VERCEL_LINK}, env={"GITHUB_ACTIONS": "true"})
    assert result.returncode == 1
    assert f"::error file=editions/{NEW},line=2::" in result.stdout


def test_policyengine_org_links_pass(tmp_path):
    html = '<a href="https://www.policyengine.org/us/ballot-measures-2026">D</a>'
    result = run_lint(tmp_path, {NEW: html})
    assert result.returncode == 0
    assert "hosting address" not in result.stdout
