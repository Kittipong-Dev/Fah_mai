# -*- coding: utf-8 -*-
"""FahMai team-agent entrypoint.

    python main.py answer "<question id or text>"
    python main.py submit [--limit N]      # resumable batch -> submission.csv
    python main.py eval                    # regression compare vs data/ground_truth.csv

All logic lives in the `fahmai.agents` package; this file is just the CLI shim.
"""
from fahmai.agents.runner import cli

if __name__ == "__main__":
    raise SystemExit(cli())
