from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCS_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "docs.yml"


def test_pages_workflow_excludes_adrs_before_building() -> None:
    workflow = DOCS_WORKFLOW.read_text()

    exclude_adrs = workflow.index("rm -rf -- docs/adr")
    build_docs = workflow.index("uv run zensical build --strict --clean")

    assert exclude_adrs < build_docs


def test_pages_workflow_tracks_docs_dependency_changes() -> None:
    workflow = DOCS_WORKFLOW.read_text()

    assert '      - "docs/**"' in workflow
    assert '      - "pyproject.toml"' in workflow
    assert '      - "uv.lock"' in workflow
