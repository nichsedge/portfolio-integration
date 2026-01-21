import os
import json
import asyncio
import time
from pathlib import Path
import datetime

from ksei.client import KSEIClient
from ksei.utils import FileAuthStore

import logging

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def fetch_and_dump_portfolios(
    username: str,
    password: str,
    auth_path: str = "./auth",
    output_dir: str = "/home/al/Projects/.data/portfolio",
    write_output: bool = True,
):
    auth_store = FileAuthStore(directory=auth_path)
    client = KSEIClient(auth_store=auth_store, username=username, password=password)

    res = await client.get_all_portfolios_async()

    if res is None:
        raise AssertionError("get_all_portfolios_async() returned None")
    if not isinstance(res, (dict, list)):
        raise AssertionError(f"Unexpected response type: {type(res)}")

    if write_output:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        out_file = Path(output_dir) / f"{current_date}_raw_ksei.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"Wrote portfolios to: {out_file.resolve()}")

    return res


async def main():
    username = os.getenv("KSEI_USERNAME")
    password = os.getenv("KSEI_PASSWORD")
    auth_path = os.getenv("KSEI_AUTH_PATH", "./auth")
    output_dir = os.getenv("KSEI_OUTPUT_DIR", "/home/al/Projects/.data/portfolio")
    write_output = os.getenv("KSEI_WRITE_OUTPUT", "1") not in ("0", "false", "False")

    if not username or not password:
        raise SystemExit(
            "KSEI_USERNAME and KSEI_PASSWORD environment variables must be set"
        )

    start_time = time.time()
    await fetch_and_dump_portfolios(
        username=username,
        password=password,
        auth_path=auth_path,
        output_dir=output_dir,
        write_output=write_output,
    )
    end_time = time.time()
    print(f"Execution time: {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())
