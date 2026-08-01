"""Unit tests for FEAT-009 research workflow prompt templates.

Spec source: specs/011-news-deduplication/spec.md (User Story 3, FR-012..FR-014, SC-004)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Repo root: backend/tests/unit/this_file -> parents[3] = repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_DIR = REPO_ROOT / "AI_PROMPTS" / "research"

EXPECTED_TEMPLATES = [
    "01_context_injection.md",
    "02_research_generation.md",
    "03_adversarial_critique.md",
    "04_synthesis.md",
    "05_implementation_brief.md",
]


def test_research_prompt_directory_exists() -> None:
    """FR-012 / SC-004: AI_PROMPTS/research/ directory is present."""
    assert RESEARCH_DIR.is_dir(), f"Missing research prompts directory: {RESEARCH_DIR}"


@pytest.mark.parametrize("filename", EXPECTED_TEMPLATES)
def test_research_prompt_template_exists(filename: str) -> None:
    """FR-012: each of the five version-controlled prompt templates exists."""
    path = RESEARCH_DIR / filename
    assert path.is_file(), f"Missing template: {path}"
    content = path.read_text(encoding="utf-8")
    assert content.strip(), f"Template is empty: {filename}"


@pytest.mark.parametrize("filename", EXPECTED_TEMPLATES)
def test_research_prompt_uses_placeholder_variables(filename: str) -> None:
    """FR-014: templates use {{VARIABLE}} placeholders."""
    content = (RESEARCH_DIR / filename).read_text(encoding="utf-8")
    placeholders = re.findall(r"\{\{[A-Z0-9_]+\}\}", content)
    assert placeholders, f"{filename} should contain at least one {{VARIABLE}} placeholder"


@pytest.mark.parametrize("filename", EXPECTED_TEMPLATES)
def test_research_prompt_has_xml_style_section_tags(filename: str) -> None:
    """FR-014: templates include explicit XML-style section tags."""
    content = (RESEARCH_DIR / filename).read_text(encoding="utf-8")
    # At least one of the structural tags required by the spec
    has_structure = any(
        tag in content
        for tag in (
            "<input>",
            "<expected_output>",
            "<instructions>",
            "<validation_rules>",
        )
    )
    assert has_structure, f"{filename} missing XML-style section tags"


def test_research_prompts_cover_full_workflow_sequence() -> None:
    """US3 SC1: sequential stages Context → Generation → Critique → Synthesis → Brief."""
    stage_markers = {
        "01_context_injection.md": ("context", "research_sessions"),
        "02_research_generation.md": ("research", "research_ideas"),
        "03_adversarial_critique.md": ("critique",),
        "04_synthesis.md": ("synthesis",),
        "05_implementation_brief.md": ("implementation", "decision"),
    }
    for filename, markers in stage_markers.items():
        content = (RESEARCH_DIR / filename).read_text(encoding="utf-8").lower()
        assert any(m in content for m in markers), f"{filename} missing stage marker among {markers}"


def test_research_prompts_reference_feat008_schema_entities() -> None:
    """FR-013: templates guide output that maps to FEAT-008 research tables."""
    all_content = "\n".join(
        (RESEARCH_DIR / name).read_text(encoding="utf-8").lower() for name in EXPECTED_TEMPLATES
    )
    # At least some FEAT-008 entity names should appear across the set
    feat008_hints = (
        "research_sessions",
        "research_ideas",
        "research_critiques",
        "research_syntheses",
        "research_decisions",
        "research_rollout",
    )
    hits = [h for h in feat008_hints if h in all_content]
    assert len(hits) >= 2, f"Expected FEAT-008 schema references; found {hits}"
