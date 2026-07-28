from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os


@dataclass
class Settings:
    project_name: str = "PackGraph Lab"
    graph_backend: str = "neo4j"
    packgraph_data_dir: Path = Path("./data/generated")
    packgraph_runtime_dir: Path = Path("./data/runtime")
    packgraph_staging_dir: Path = Path("./data/staging")
    private_data_dir: Path = Path("./private_data")
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "packgraph123"
    neo4j_database: str = "neo4j"
    neo4j_auto_ingest: bool = False
    project_memory_path: Path = Path("./data/staging/project_memory.json")
    review_candidates_path: Path = Path("./data/staging/agent_review_candidates.json")
    agent_audit_path: Path = Path("./data/runtime/agent_audit.jsonl")


@lru_cache
def get_settings() -> Settings:
    settings = Settings(
        graph_backend=os.getenv("GRAPH_BACKEND", "neo4j"),
        packgraph_data_dir=Path(os.getenv("PACKGRAPH_DATA_DIR", "./data/generated")),
        packgraph_runtime_dir=Path(os.getenv("PACKGRAPH_RUNTIME_DIR", "./data/runtime")),
        packgraph_staging_dir=Path(os.getenv("PACKGRAPH_STAGING_DIR", "./data/staging")),
        private_data_dir=Path(os.getenv("PACKGRAPH_PRIVATE_DATA_DIR", "./private_data")),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "packgraph123"),
        neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
        neo4j_auto_ingest=os.getenv("NEO4J_AUTO_INGEST", "false").lower() in {"1", "true", "yes", "on"},
        project_memory_path=Path(os.getenv("PACKGRAPH_PROJECT_MEMORY_PATH", "./data/staging/project_memory.json")),
        review_candidates_path=Path(os.getenv("PACKGRAPH_REVIEW_CANDIDATES_PATH", "./data/staging/agent_review_candidates.json")),
        agent_audit_path=Path(os.getenv("PACKGRAPH_AGENT_AUDIT_PATH", "./data/runtime/agent_audit.jsonl")),
    )
    settings.packgraph_data_dir.mkdir(parents=True, exist_ok=True)
    settings.packgraph_runtime_dir.mkdir(parents=True, exist_ok=True)
    settings.packgraph_staging_dir.mkdir(parents=True, exist_ok=True)
    settings.private_data_dir.mkdir(parents=True, exist_ok=True)
    if not settings.project_memory_path.exists():
        settings.project_memory_path.write_text(
            '{"saved_entities":[],"saved_suppliers":[],"prior_questions":[],"compared_entities":[],"user_assumptions":[],"uploaded_file_references":[],"investigation_notes":[]}',
            encoding="utf-8",
        )
    if not settings.review_candidates_path.exists():
        settings.review_candidates_path.write_text("[]", encoding="utf-8")
    return settings
