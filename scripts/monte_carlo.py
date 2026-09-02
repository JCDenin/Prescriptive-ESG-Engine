"""Batch-generate Monte Carlo test datasets as CSV files.

Examples:
    python scripts/monte_carlo.py                      # one 10,000-row dataset
    python scripts/monte_carlo.py --rows 10000 --count 5
    python scripts/monte_carlo.py --seed 42            # reproducible
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.simulator import simulate  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "data"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rows", type=int, default=10000)
    ap.add_argument("--count", type=int, default=1, help="number of datasets")
    ap.add_argument("--seed", type=int, default=None,
                    help="base seed; dataset i uses seed+i (omit for random)")
    ap.add_argument("--demo", action="store_true",
                    help="demo-mode priors (reliably visible findings)")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    for i in range(args.count):
        seed = None if args.seed is None else args.seed + i
        df, params = simulate(n_rows=args.rows, seed=seed, demo_mode=args.demo)
        out = OUT_DIR / f"mc_dataset_seed{params['seed']}.csv"
        df.to_csv(out, index=False)
        print(f"{out.name}: {len(df)} rows | world = "
              f"{json.dumps({k: v for k, v in params.items() if k not in ('seed', 'n_rows')})}")


if __name__ == "__main__":
    main()
