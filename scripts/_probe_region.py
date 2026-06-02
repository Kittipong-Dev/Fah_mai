"""Probe Supabase pooler regions to find where this project lives.
Tries session-pooler (5432) across common AWS regions and prints the one that
authenticates. Password stays out of stdout.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

REF = urlparse(os.environ["SUPABASE_URL"]).hostname.split(".")[0]
PWD = os.environ["SUPABASE_PASSWORD"]

REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-central-2", "eu-north-1",
    "ap-southeast-1", "ap-southeast-2", "ap-south-1",
    "ap-northeast-1", "ap-northeast-2", "ap-east-1",
    "sa-east-1", "ca-central-1",
]
PREFIXES = ["aws-0", "aws-1"]

print(f"project ref: {REF}\n")
for prefix in PREFIXES:
    for region in REGIONS:
        host = f"{prefix}-{region}.pooler.supabase.com"
        user = f"postgres.{REF}"
        try:
            conn = psycopg.connect(
                host=host, port=5432, user=user, password=PWD,
                dbname="postgres", connect_timeout=6,
            )
            conn.close()
            print(f"\n*** FOUND: host={host} port=5432 user={user} ***")
            print(f'DATABASE_URL=postgresql+psycopg://{user}:<PWD>@{host}:5432/postgres')
            sys.exit(0)
        except psycopg.OperationalError as e:
            msg = str(e).splitlines()[0]
            if "tenant" in msg.lower() and "not found" in msg.lower():
                print(f"  miss  {host}")
            else:
                # tenant exists here but something else (wrong pwd, etc.) -> report loudly
                print(f"  ??    {host}: {msg}")
        except Exception as e:  # noqa: BLE001
            print(f"  err   {host}: {str(e).splitlines()[0]}")

print("\nNo region authenticated. Project may be PAUSED, or password/ref differs.")
sys.exit(1)
