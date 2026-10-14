"""Give listings without a position an approximate one, outside a scan.

    python -m scraper.geolocate            # own data first, then Nominatim
    python -m scraper.geolocate --offline  # own data only

Every scan already does this at the end; this is for the backlog.
"""

import argparse
import asyncio
import sys

from app.database import init_db
from app.services.geolocate import locate_missing_listings
from app.utils.logging import setup_logging


async def main(offline: bool) -> None:
    setup_logging()
    await init_db()
    located = await locate_missing_listings(use_network=not offline)
    if not located:
        sys.stderr.write("Nessun annuncio senza posizione.\n")
        return
    for precision, count in sorted(located.items()):
        sys.stderr.write(f"{precision:>8}: {count}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="use our own data only, no Nominatim")
    asyncio.run(main(parser.parse_args().offline))
