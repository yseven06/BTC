"""
Analysis result database model.

Stores the output of each analysis engine run against an asset,
including the numerical score, directional bias, and key findings.
"""

import enum
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class EngineType(str, enum.Enum):
    """Available analysis engine types."""
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    ONCHAIN = "onchain"
    MACRO = "macro"
    VALUATION = "valuation"
    QUANTITATIVE = "quantitative"
    INTERMARKET = "intermarket"


class AnalysisBias(str, enum.Enum):
    """Directional bias from analysis."""
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    SLIGHTLY_BULLISH = "slightly_bullish"
    NEUTRAL = "neutral"
    SLIGHTLY_BEARISH = "slightly_bearish"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"


class AnalysisResult(Base):
    """
    Individual engine analysis result.

    Each row represents the output of a single analysis engine
    for a specific asset at a specific point in time.

    Attributes:
        id: Unique UUID primary key.
        asset_id: Foreign key to the analysed asset.
        engine_type: Which engine produced this result.
        result_data: Full JSON output from the engine.
        score: Normalised score (-100 to 100).
        bias: Directional bias classification.
        key_findings: List of important observations.
        analyzed_at: When the analysis was performed.
    """

    __tablename__ = "analysis_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine_type = Column(
        Enum(EngineType, name="engine_type", create_constraint=True),
        nullable=False,
        index=True,
    )
    result_data = Column(JSON, nullable=True, default=dict)
    score = Column(Numeric(precision=6, scale=2), nullable=True)
    bias = Column(
        Enum(AnalysisBias, name="analysis_bias", create_constraint=True),
        nullable=True,
    )
    key_findings = Column(JSON, nullable=True, default=list)
    analyzed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    asset = relationship("Asset", back_populates="analysis_results")

    def __repr__(self) -> str:
        return (
            f"<AnalysisResult(id={self.id}, asset_id={self.asset_id}, "
            f"engine={self.engine_type}, score={self.score})>"
        )
