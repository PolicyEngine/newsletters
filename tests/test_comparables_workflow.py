"""Exercise the comparables workflow's actual shell block with Git filenames."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SELECTOR = ROOT / "scripts" / "select_changed_editions.py"
GIT = shutil.which("git")
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(not GIT or not BASH, reason="needs git and bash")


def workflow_script():
    """Read the checked-in step, so tests cannot drift from CI selection."""
    step = WORKFLOW.read_text(encoding="utf-8").split(
        "      - name: Every analysis a changed edition links has a fresh "
        "comparables search\n",
        1,
    )[1]
    body = step.split("        run: |\n", 1)[1]
    lines = []
    for line in body.splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:])
    return "\n".join(lines)


def git(repo, *args):
    return subprocess.check_output([GIT, *args], cwd=repo, text=True).strip()


def run_workflow(tmp_path, names, base=None, fail=None):
    """Commit synthetic changes and capture every argument reaching the checker."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Workflow test")
    git(repo, "config", "user.email", "workflow@example.com")
    git(repo, "config", "core.quotePath", "true")
    (repo / "README.md").write_text("Baseline\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Baseline")
    baseline = git(repo, "rev-parse", "HEAD")
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Changed\n", encoding="utf-8")
    if names:
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "Changed files")

    scripts = repo / "scripts"
    scripts.mkdir(exist_ok=True)
    shutil.copyfile(SELECTOR, scripts / SELECTOR.name)
    package = tmp_path / "fake" / "newsletter_uploader"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "comparables.py").write_text(
        "import json, os, sys\n"
        "with open(os.environ['CHECKER_LOG'], 'a', encoding='utf-8') as output:\n"
        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(int(os.environ.get('CHECKER_EXIT', '0')))\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python"
    python.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "if os.environ.get('FAIL_SELECTOR') and "
        "sys.argv[1].endswith('select_changed_editions.py'):\n"
        "    print('selector failed', file=sys.stderr)\n"
        "    sys.exit(24)\n"
        f"os.execv({sys.executable!r}, [{sys.executable!r}] + sys.argv[1:])\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    if fail == "diff":
        wrapper = bin_dir / "git"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\n"
            "if sys.argv[1] == 'diff':\n"
            "    print('diff failed', file=sys.stderr)\n"
            "    sys.exit(23)\n"
            f"os.execv({GIT!r}, [{GIT!r}] + sys.argv[1:])\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    checker_log = tmp_path / "checker.jsonl"
    env = dict(
        os.environ,
        BASE_SHA=baseline if base is None else base,
        RUNNER_TEMP=str(runner_temp),
        CHECKER_LOG=str(checker_log),
        CHECKER_EXIT="7" if fail == "checker" else "0",
        FAIL_SELECTOR="1" if fail == "selector" else "",
        PYTHONPATH=str(package.parent),
        PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
    )
    result = subprocess.run(
        [BASH, "-c", workflow_script()],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = (
        [
            json.loads(line)
            for line in checker_log.read_text(encoding="utf-8").splitlines()
        ]
        if checker_log.exists()
        else []
    )
    return result, calls


def test_git_quoted_names_reach_the_checker_without_changes(tmp_path):
    names = [
        "editions/2026-11-03-uk-é.html",
        "editions/2026-11-03-us-\ttab.htm",
        "editions/2026-11-03-us-\nline-social.md",
        "editions/nested/2026-11-03-us space.HTML",
    ]
    result, calls = run_workflow(tmp_path, names + ["notes.txt"])
    assert result.returncode == 0, result.stderr
    assert len(calls) == 1
    assert calls[0][0] == "--require-dates"
    assert set(calls[0][1:]) == set(names)


@pytest.mark.parametrize("base", ["", "0" * 40])
def test_first_push_checks_editions_against_the_empty_tree(tmp_path, base):
    name = "editions/2026-11-03-uk-é.html"
    result, calls = run_workflow(tmp_path, [name], base=base)
    assert result.returncode == 0, result.stderr
    assert calls == [["--require-dates", name]]


@pytest.mark.parametrize("names", [[], ["docs/notes.md"]])
def test_no_edition_change_skips_only_the_checker(tmp_path, names):
    result, calls = run_workflow(tmp_path, names)
    assert result.returncode == 0, result.stderr
    assert "No edition changed; nothing to check." in result.stdout
    assert calls == []


@pytest.mark.parametrize(
    "name",
    ["social-posts-é.md", "posts/2026-11-03-us-\tsocial\n.md"],
)
def test_misplaced_social_names_fail_even_when_git_quotes_them(tmp_path, name):
    result, calls = run_workflow(tmp_path, [name])
    assert result.returncode != 0
    assert "social posts go in editions/" in result.stdout
    assert calls == []


def test_missing_base_commit_fails_before_selection(tmp_path):
    result, calls = run_workflow(tmp_path, [], base="f" * 40)
    assert result.returncode != 0
    assert "cannot read the base commit" in result.stdout
    assert "No edition changed" not in result.stdout
    assert calls == []


@pytest.mark.parametrize("failure", ["diff", "selector"])
def test_failed_diff_or_selection_does_not_become_a_successful_noop(tmp_path, failure):
    result, calls = run_workflow(tmp_path, [], fail=failure)
    assert result.returncode != 0
    assert f"{failure} failed" in result.stderr
    assert "No edition changed" not in result.stdout
    assert calls == []


def test_checker_failure_fails_the_job(tmp_path):
    name = "editions/2026-11-03-uk-é.html"
    result, calls = run_workflow(tmp_path, [name], fail="checker")
    assert result.returncode != 0
    assert calls == [["--require-dates", name]]
