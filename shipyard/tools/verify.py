import asyncio
import re
from pathlib import Path

from pydantic import BaseModel, Field


class VerifyChecklistInput(BaseModel):
    pass  # No input needed — reads plan.md automatically


class VerificationResult:
    def __init__(self):
        self.checks: list[dict] = []
        self.passed: bool = True

    def add(self, name: str, passed: bool, detail: str = ""):
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            self.passed = False

    def summary(self) -> str:
        lines = []
        passed_count = sum(1 for c in self.checks if c["passed"])
        total = len(self.checks)
        lines.append(f"Verification: {passed_count}/{total} checks passed\n")

        for c in self.checks:
            icon = "✓" if c["passed"] else "✗"
            line = f"  {icon} {c['name']}"
            if c["detail"]:
                line += f" — {c['detail']}"
            lines.append(line)

        if self.passed:
            lines.append("\nAll checks passed. You may write STATUS: COMPLETE.")
        else:
            lines.append("\nSome checks FAILED. Fix the issues before writing STATUS: COMPLETE.")

        return "\n".join(lines)


async def verify_checklist(
    project_root: Path,
) -> str:
    """
    Run automated verification checks:
    1. Check all files from plan.md exist on disk
    2. Try starting servers (if package.json has start/dev scripts) — crash = fail
    3. Try curling API endpoints if a backend server starts

    Call this BEFORE writing STATUS: COMPLETE.
    """
    result = VerificationResult()

    # 1. Check files from plan.md
    await _check_plan_files(project_root, result)

    # 2. Check critical framework files
    await _check_framework_files(project_root, result)

    # 3. Try starting backend server
    await _check_server(project_root, result)

    return result.summary()


async def _check_plan_files(project_root: Path, result: VerificationResult):
    """Extract file paths from plan.md and check they exist."""
    plan_path = project_root / ".shipyard" / "notes" / "plan.md"
    if not plan_path.exists():
        result.add("plan.md exists", False, "No plan found at .shipyard/notes/plan.md")
        return

    result.add("plan.md exists", True)
    plan_content = plan_path.read_text(encoding="utf-8")

    # Extract file paths from plan — look for patterns like `packages/api/src/index.ts`
    file_patterns = re.findall(r'`((?:packages|src)/[a-zA-Z0-9_./-]+\.[a-zA-Z]+)`', plan_content)
    # Also look for backtick-free paths
    file_patterns += re.findall(r'(?:^|\s)((?:packages|src)/[a-zA-Z0-9_./-]+\.(?:ts|tsx|js|json|html|css))', plan_content)
    # Deduplicate
    file_paths = list(set(file_patterns))

    if not file_paths:
        result.add("Files from plan", True, "No specific file paths found in plan to verify")
        return

    missing = []
    for fp in file_paths:
        full = project_root / fp
        if not full.exists():
            missing.append(fp)

    if missing:
        result.add(
            f"Files from plan ({len(file_paths) - len(missing)}/{len(file_paths)} exist)",
            False,
            f"Missing: {', '.join(missing[:10])}"
        )
    else:
        result.add(f"All {len(file_paths)} files from plan exist", True)


async def _check_framework_files(project_root: Path, result: VerificationResult):
    """Check for critical framework files that are commonly missed."""
    # Look for web/frontend packages
    web_dirs = list(project_root.glob("packages/web")) + list(project_root.glob("packages/frontend"))

    for web_dir in web_dirs:
        name = web_dir.name

        # Vite required files
        index_html = web_dir / "index.html"
        result.add(f"{name}/index.html", index_html.exists(),
                   "Required for Vite to serve the app" if not index_html.exists() else "")

        # Find main entry point
        main_tsx = web_dir / "src" / "main.tsx"
        main_ts = web_dir / "src" / "main.ts"
        has_main = main_tsx.exists() or main_ts.exists()
        result.add(f"{name}/src/main.tsx", has_main,
                   "React entry point required" if not has_main else "")

        # CSS with Tailwind
        index_css = web_dir / "src" / "index.css"
        if index_css.exists():
            content = index_css.read_text()
            has_tailwind = "@tailwind" in content
            result.add(f"{name}/src/index.css has Tailwind", has_tailwind,
                       "Missing @tailwind directives" if not has_tailwind else "")
        else:
            result.add(f"{name}/src/index.css", False, "Missing — Tailwind styles won't load")

        # Vite config
        vite_config = web_dir / "vite.config.ts"
        result.add(f"{name}/vite.config.ts", vite_config.exists(),
                   "Vite configuration required" if not vite_config.exists() else "")


async def _check_server(project_root: Path, result: VerificationResult):
    """Try starting the backend server and curling it."""
    # Find API/backend package
    api_dirs = list(project_root.glob("packages/api")) + list(project_root.glob("packages/backend"))

    for api_dir in api_dirs:
        name = api_dir.name
        pkg_json = api_dir / "package.json"

        if not pkg_json.exists():
            result.add(f"{name}/package.json", False)
            continue

        # Find the entry point
        entry = None
        for candidate in ["src/index.ts", "src/server.ts", "src/app.ts", "index.ts"]:
            if (api_dir / candidate).exists():
                entry = candidate
                break

        if not entry:
            result.add(f"{name} entry point", False, "No src/index.ts or similar found")
            continue

        # Try starting the server in background
        try:
            proc = await asyncio.create_subprocess_shell(
                f"npx tsx {entry}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(api_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=4)
                # Process exited — it crashed
                output = stderr.decode("utf-8", errors="replace") + stdout.decode("utf-8", errors="replace")
                result.add(f"{name} server starts", False,
                           f"Crashed: {output[:200]}")
            except asyncio.TimeoutError:
                # Still running — good
                result.add(f"{name} server starts", True, "Server started without crashing")

                # Try curling it
                try:
                    curl_proc = await asyncio.create_subprocess_shell(
                        "curl -s -o /dev/null -w '%{http_code}' http://localhost:3001/api/documents",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    curl_out, _ = await asyncio.wait_for(curl_proc.communicate(), timeout=5)
                    status = curl_out.decode().strip()
                    if status == "200":
                        result.add("API responds to GET /api/documents", True)
                    else:
                        result.add("API responds to GET /api/documents", False, f"HTTP {status}")
                except Exception as e:
                    result.add("API responds to GET /api/documents", False, str(e))

                # Kill the server
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass

        except Exception as e:
            result.add(f"{name} server starts", False, str(e))
