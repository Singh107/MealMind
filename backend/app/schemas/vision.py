from typing import Literal
from pydantic import Field
from app.schemas.recipes import Contract, Name


class DetectionProposal(Contract):
    display_name: Name
    confidence: Literal['high', 'medium', 'low']
    visible_state: Literal['raw', 'cooked', 'dry', 'canned'] | None = None
    uncertainty: str = Field(max_length=300)


class VisionProposal(Contract):
    detections: list[DetectionProposal] = Field(max_length=30)


class IngredientDetection(DetectionProposal):
    normalized_name: str
    canonical_name: str | None
    food_state: str | None
    identity_status: Literal['recognized', 'unresolved', 'conflicting']
    merged_count: int = 1


class ImageIngredientAnalysis(Contract):
    analysis_id: str
    detections: list[IngredientDetection]
    warnings: list[str]
    provider: str
    model: str
