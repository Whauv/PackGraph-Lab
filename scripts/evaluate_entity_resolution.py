from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.entity_resolution_agent import EntityResolutionAgent


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Evaluate PackGraph entity-resolution precision and recall.")
    parser.add_argument(
        "--dataset",
        default=str(settings.er_eval_dataset_path),
        help="Path to the labeled entity-resolution evaluation dataset.",
    )
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    agent = EntityResolutionAgent(get_settings())
    tp = fp = fn = 0
    for item in dataset:
        result = agent.compare_records(item["left"], item["right"])
        predicted_match = result["decision"] != "reject_match"
        expected_match = bool(item["expected_match"])
        if predicted_match and expected_match:
            tp += 1
        elif predicted_match and not expected_match:
            fp += 1
        elif not predicted_match and expected_match:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    payload = {
        "dataset": args.dataset,
        "backend": agent.active_backend,
        "examples": len(dataset),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
    }
    print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    main()
