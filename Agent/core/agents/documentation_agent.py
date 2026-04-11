"""Documentation generation agent for README, changelog, and API docs."""

from __future__ import annotations

import ast
from collections import Counter
from datetime import date
from pathlib import Path
from typing import List

from core.agents.base import AgentContext, AgentResponse, SpecializedAgent
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult


class DocumentationAgent(SpecializedAgent):
    """Auto-generate documentation from code."""

    def __init__(self) -> None:
        super().__init__("documentation")
        self._keywords = [
            "documentation",
            "docs",
            "readme",
            "changelog",
            "api docs",
            "document code",
        ]

    async def generate_readme(self, codebase_path: str) -> str:
        """Generate README from code analysis."""
        root = Path(str(codebase_path or "").strip())
        if not root.exists() or not root.is_dir():
            raise ValueError("codebase_path must be an existing directory")

        files = [p for p in root.rglob("*") if p.is_file()]
        language_counts = Counter(self._detect_language(path) for path in files)
        language_counts.pop("Other", None)
        top_languages = language_counts.most_common(3)

        top_dirs = Counter(
            str(path.relative_to(root)).split("/", 1)[0]
            for path in files
            if str(path.relative_to(root)).strip()
        ).most_common(5)

        lines = [
            "# Project README",
            "",
            "## Overview",
            f"- Total files analyzed: {len(files)}",
            f"- Primary language(s): {', '.join(f'{name} ({count})' for name, count in top_languages) if top_languages else 'Unknown'}",
            "",
            "## Directory Highlights",
        ]
        if top_dirs:
            lines.extend(f"- `{name}`: {count} file(s)" for name, count in top_dirs)
        else:
            lines.append("- No files discovered.")

        lines.extend(
            [
                "",
                "## Getting Started",
                "- Install dependencies for the primary runtime.",
                "- Run the project test suite before shipping changes.",
                "- Keep README and changelog aligned with released behavior.",
            ]
        )
        return "\n".join(lines)

    async def update_changelog(self, commits: List[str]) -> str:
        """Update CHANGELOG.md."""
        grouped: dict[str, list[str]] = {
            "Added": [],
            "Changed": [],
            "Fixed": [],
            "Tests": [],
            "Docs": [],
            "Other": [],
        }
        for raw in commits or []:
            line = str(raw or "").strip()
            lowered = line.lower()
            if lowered.startswith("feat"):
                grouped["Added"].append(line)
            elif lowered.startswith("fix"):
                grouped["Fixed"].append(line)
            elif lowered.startswith("test"):
                grouped["Tests"].append(line)
            elif lowered.startswith("docs"):
                grouped["Docs"].append(line)
            elif lowered.startswith("refactor") or lowered.startswith("perf") or lowered.startswith("chore"):
                grouped["Changed"].append(line)
            else:
                grouped["Other"].append(line)

        stamp = date.today().isoformat()
        lines = [f"## {stamp}", ""]
        for heading in ("Added", "Changed", "Fixed", "Tests", "Docs", "Other"):
            lines.append(f"### {heading}")
            if grouped[heading]:
                lines.extend(f"- {entry}" for entry in grouped[heading])
            else:
                lines.append("- None")
            lines.append("")
        return "\n".join(lines).strip()

    async def generate_api_docs(self, module_path: str) -> str:
        """Generate API documentation."""
        path = Path(str(module_path or "").strip())
        if not path.exists() or not path.is_file():
            raise ValueError("module_path must be an existing file")

        source = path.read_text(encoding="utf-8")
        module_ast = ast.parse(source)
        module_doc = ast.get_docstring(module_ast) or "No module docstring."

        classes: list[tuple[str, str, list[str]]] = []
        functions: list[tuple[str, str, str]] = []

        for node in module_ast.body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                methods = [
                    fn.name
                    for fn in node.body
                    if isinstance(fn, ast.FunctionDef) and not fn.name.startswith("_")
                ]
                classes.append((node.name, ast.get_docstring(node) or "No class docstring.", methods))
            elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                functions.append(
                    (
                        node.name,
                        self._format_signature(node),
                        ast.get_docstring(node) or "No function docstring.",
                    )
                )

        lines = [
            f"# API Docs: {path.name}",
            "",
            "## Module",
            module_doc,
            "",
            "## Classes",
        ]
        if classes:
            for name, doc, methods in classes:
                lines.append(f"### `{name}`")
                lines.append(doc)
                lines.append(f"- Methods: {', '.join(methods) if methods else 'None'}")
                lines.append("")
        else:
            lines.append("- None")
            lines.append("")

        lines.append("## Functions")
        if functions:
            for name, signature, doc in functions:
                lines.append(f"### `{name}{signature}`")
                lines.append(doc)
                lines.append("")
        else:
            lines.append("- None")

        return "\n".join(lines).strip()

    async def can_handle(self, request: str, context: AgentContext) -> float:
        lowered = str(request or "").lower()
        matches = sum(1 for keyword in self._keywords if keyword in lowered)
        if matches == 0:
            return 0.0
        return min(1.0, 0.35 + (0.2 * min(matches, 3)))

    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        confidence = await self.can_handle(request.user_text, self._legacy_context_from_request(request))
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=confidence,
            reason="documentation_keyword_match",
            hard_constraints_passed=bool(str(request.user_text or "").strip()),
        )

    async def execute(self, request: str, context: AgentContext) -> AgentResponse:
        metadata = dict(context.custom_data or {})
        if metadata.get("codebase_path"):
            content = await self.generate_readme(str(metadata["codebase_path"]))
            return AgentResponse(
                display_text="README generated.",
                voice_text="README generated.",
                mode="direct",
                confidence=0.9,
                structured_data={"document_type": "readme", "content": content},
            )
        if metadata.get("commits"):
            content = await self.update_changelog(list(metadata["commits"]))
            return AgentResponse(
                display_text="Changelog entry generated.",
                voice_text="Changelog entry generated.",
                mode="direct",
                confidence=0.9,
                structured_data={"document_type": "changelog", "content": content},
            )
        if metadata.get("module_path"):
            content = await self.generate_api_docs(str(metadata["module_path"]))
            return AgentResponse(
                display_text="API docs generated.",
                voice_text="API docs generated.",
                mode="direct",
                confidence=0.9,
                structured_data={"document_type": "api_docs", "content": content},
            )
        return AgentResponse(
            display_text="Documentation intent accepted. Provide codebase_path, commits, or module_path.",
            voice_text="Documentation intent accepted.",
            mode="direct",
            confidence=0.8,
            structured_data={"accepted": True},
        )

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        metadata = dict(request.metadata or {})
        structured_payload = {
            "codebase_path": metadata.get("codebase_path"),
            "has_commits": bool(metadata.get("commits")),
            "module_path": metadata.get("module_path"),
        }
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text="Documentation intent validated.",
            voice_text=None,
            structured_payload=structured_payload,
            next_action="continue",
        )

    def get_capabilities(self) -> list:
        return [
            "Generate README from codebase structure",
            "Generate changelog entries from commit list",
            "Generate API docs from Python modules",
        ]

    @staticmethod
    def _detect_language(path: Path) -> str:
        suffix = path.suffix.lower()
        mapping = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".java": "Java",
            ".go": "Go",
            ".rs": "Rust",
            ".md": "Markdown",
            ".yml": "YAML",
            ".yaml": "YAML",
            ".json": "JSON",
        }
        return mapping.get(suffix, "Other")

    @staticmethod
    def _format_signature(node: ast.FunctionDef) -> str:
        args = [arg.arg for arg in node.args.args]
        return "(" + ", ".join(args) + ")"
