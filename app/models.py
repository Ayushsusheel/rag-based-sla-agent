from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RetrievedEvidence:
    entity_id: str
    entity_type: str
    service_name: str
    topic_name: str
    page_num: int | None
    citation: str
    content: str
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)