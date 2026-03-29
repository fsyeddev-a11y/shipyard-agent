import pytest
from pathlib import Path
from shipyard.tools.verify import verify_checklist, _check_plan_files, _check_framework_files, VerificationResult
from shipyard.edit_engine.git import git_init_if_needed


@pytest.fixture
def project(tmp_path):
    """Create a temporary project with .shipyard/notes/."""
    git_init_if_needed(tmp_path)
    notes_dir = tmp_path / ".shipyard" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_verify_no_plan(project):
    """verify_checklist with no plan.md reports it missing."""
    import asyncio
    result = asyncio.run(verify_checklist(project_root=project))
    assert "plan.md exists" in result
    assert "✗" in result


def test_verify_plan_files_all_exist(project):
    """All files listed in plan.md exist — passes."""
    # Create plan with file paths
    plan = project / ".shipyard" / "notes" / "plan.md"
    plan.write_text("## Plan\n- Create `src/index.ts`\n- Create `src/utils.ts`\n")

    # Create the files
    (project / "src").mkdir()
    (project / "src" / "index.ts").write_text("// entry")
    (project / "src" / "utils.ts").write_text("// utils")

    result = VerificationResult()
    import asyncio
    asyncio.run(_check_plan_files(project, result))

    assert result.passed
    assert any("exist" in c["name"] for c in result.checks)


def test_verify_plan_files_some_missing(project):
    """Some files from plan.md missing — fails."""
    plan = project / ".shipyard" / "notes" / "plan.md"
    plan.write_text("## Plan\n- Create `src/index.ts`\n- Create `src/missing.ts`\n")

    (project / "src").mkdir()
    (project / "src" / "index.ts").write_text("// entry")
    # src/missing.ts NOT created

    result = VerificationResult()
    import asyncio
    asyncio.run(_check_plan_files(project, result))

    assert not result.passed
    assert any("missing" in c.get("detail", "").lower() for c in result.checks)


def test_verify_framework_files_all_present(project):
    """Vite entry files all present — passes."""
    web_dir = project / "packages" / "web"
    web_dir.mkdir(parents=True)
    (web_dir / "index.html").write_text("<html></html>")
    (web_dir / "vite.config.ts").write_text("export default {}")
    src_dir = web_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.tsx").write_text("// main")
    (src_dir / "index.css").write_text("@tailwind base;\n@tailwind components;\n@tailwind utilities;")

    result = VerificationResult()
    import asyncio
    asyncio.run(_check_framework_files(project, result))

    assert result.passed


def test_verify_framework_files_missing(project):
    """Vite entry files missing — fails."""
    web_dir = project / "packages" / "web"
    web_dir.mkdir(parents=True)
    # No index.html, no main.tsx, no index.css, no vite.config

    result = VerificationResult()
    import asyncio
    asyncio.run(_check_framework_files(project, result))

    assert not result.passed
    failures = [c for c in result.checks if not c["passed"]]
    assert len(failures) >= 3  # index.html, main.tsx, index.css at minimum


def test_verify_framework_css_no_tailwind(project):
    """index.css exists but no Tailwind directives — fails."""
    web_dir = project / "packages" / "web"
    src_dir = web_dir / "src"
    src_dir.mkdir(parents=True)
    (web_dir / "index.html").write_text("<html></html>")
    (web_dir / "vite.config.ts").write_text("export default {}")
    (src_dir / "main.tsx").write_text("// main")
    (src_dir / "index.css").write_text("body { margin: 0; }")  # No @tailwind

    result = VerificationResult()
    import asyncio
    asyncio.run(_check_framework_files(project, result))

    assert not result.passed
    assert any("tailwind" in c.get("detail", "").lower() for c in result.checks)


@pytest.mark.asyncio
async def test_verify_full_passing_project(project):
    """Full verify_checklist on a project with all files — mostly passes."""
    # Create plan
    plan = project / ".shipyard" / "notes" / "plan.md"
    plan.write_text("## Plan\n- Create `packages/web/src/App.tsx`\n")

    # Create web structure
    web_dir = project / "packages" / "web"
    src_dir = web_dir / "src"
    src_dir.mkdir(parents=True)
    (web_dir / "index.html").write_text("<html><body><div id='root'></div></body></html>")
    (web_dir / "vite.config.ts").write_text("export default {}")
    (src_dir / "main.tsx").write_text("// main entry")
    (src_dir / "index.css").write_text("@tailwind base;\n@tailwind components;\n@tailwind utilities;")
    (src_dir / "App.tsx").write_text("export default function App() { return <div/>; }")

    result = await verify_checklist(project_root=project)
    assert "plan.md exists" in result
    assert "All" in result or "exist" in result


@pytest.mark.asyncio
async def test_verify_summary_format(project):
    """verify_checklist returns formatted summary with check/cross marks."""
    plan = project / ".shipyard" / "notes" / "plan.md"
    plan.write_text("## Plan\nNo file paths here.\n")

    result = await verify_checklist(project_root=project)
    assert "Verification:" in result
    assert "checks passed" in result
