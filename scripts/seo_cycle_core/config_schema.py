"""Optional Pydantic schema for seo-cycle.yaml (validate-config.py --strict).

Pydantic is NOT a hard dependency: `schema_errors()` returns a clear hint when
it is missing. Models cover the sections whose shape the scripts rely on and
allow extra keys everywhere — the config is large and evolves faster than the
schema, so unknown keys are never an error.
"""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via schema_errors fallback
    PYDANTIC_AVAILABLE = False


if PYDANTIC_AVAILABLE:

    class _Base(BaseModel):
        model_config = ConfigDict(extra="allow")

    class Project(_Base):
        name: str
        domain: str = ""
        url: str = ""

    class Locale(_Base):
        language: str = ""
        country: str = ""

    class Engine(_Base):
        name: str
        priority: int | float | None = None

    class LoggingSection(_Base):
        enabled: bool = True
        dir: str = "seo/logs"
        level: str = "INFO"
        stderr_level: str = "WARNING"

    class LoopTarget(_Base):
        max_attempts: int = Field(default=5, ge=1, le=20)

    class GovernanceLoop(_Base):
        enabled: bool = True
        max_attempts: int = Field(default=5, ge=1, le=20)
        no_progress_after: int = Field(default=2, ge=2, le=10)
        escalate: bool = True
        targets: dict[str, LoopTarget] = {}

    class Governance(_Base):
        loop: GovernanceLoop = GovernanceLoop()

    class AdsPlatform(_Base):
        enabled: bool = False

    class AdsApply(_Base):
        max_changes_per_run: int = Field(default=20, ge=1, le=500)
        max_daily_budget: float = Field(default=0, ge=0)

    class AdsSection(_Base):
        enabled: bool = False
        primary_platform: str = "auto"
        policy: str = "approval_only"
        yandex_direct: AdsPlatform = AdsPlatform()
        google_ads: AdsPlatform = AdsPlatform()
        apply: AdsApply = AdsApply()

    class RagEmbedding(_Base):
        mode: str = "auto"

    class RagSection(_Base):
        chunk_chars: int = Field(default=1200, ge=100, le=20000)
        chunk_overlap: int = Field(default=150, ge=0, le=5000)
        sources: list[str] = []
        embedding: RagEmbedding = RagEmbedding()

    class KpiGoals(_Base):
        monthly_organic_clicks: float = Field(default=0, ge=0)
        monthly_leads: float = Field(default=0, ge=0)
        keywords_in_top10: float = Field(default=0, ge=0)

    class KpiSection(_Base):
        enabled: bool = False
        tolerance_pct: float = Field(default=20, ge=0, le=100)
        lead_conversion_rate: float = Field(default=0.02, ge=0, le=1)
        months_to_target: int = Field(default=6, ge=1, le=60)
        goals: KpiGoals = KpiGoals()

    class SeoCycleConfig(_Base):
        project: Project
        locale: Locale = Locale()
        engines: list[Engine] = []
        project_type: str = ""
        region_profile: str = ""
        logging: LoggingSection = LoggingSection()
        governance: Governance = Governance()
        ads: AdsSection = AdsSection()
        rag: RagSection = RagSection()
        kpi: KpiSection = KpiSection()

    _VALID_ADS_POLICIES = {"report_only", "approval_only"}
    _VALID_RAG_MODES = {"auto", "off", "required"}

    def schema_errors(cfg: dict[str, Any]) -> list[str]:
        try:
            model = SeoCycleConfig.model_validate(cfg)
        except ValidationError as exc:
            return [
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            ]
        errors = []
        if model.ads.policy not in _VALID_ADS_POLICIES:
            errors.append(f"ads.policy: must be one of {sorted(_VALID_ADS_POLICIES)}")
        if model.rag.embedding.mode not in _VALID_RAG_MODES:
            errors.append(f"rag.embedding.mode: must be one of {sorted(_VALID_RAG_MODES)}")
        return errors

else:

    def schema_errors(cfg: dict[str, Any]) -> list[str]:  # noqa: ARG001
        return ["--strict requires pydantic: pip3 install pydantic"]
