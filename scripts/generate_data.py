from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.data_generator import generate_dataset


if __name__ == "__main__":
    target = Path("data/generated")
    payloads = generate_dataset(target)
    print(
        "Generated PackGraph Lab dataset:",
        {
            "materials": len(payloads["materials"]),
            "suppliers": len(payloads["suppliers"]),
            "relationships": len(payloads["relationships"]),
            "snapshots": len(payloads["quarterly_snapshots"]),
        },
    )
