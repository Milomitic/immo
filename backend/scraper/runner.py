"""Scraper runner - CLI entrypoint and scheduler."""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.config import settings
from app.database import async_session, init_db
from app.models.scrape_run import ScrapeRun
from app.utils.logging import setup_logging
from scraper.pipeline import (
    bump_last_seen,
    get_fresh_source_ids,
    process_items_batch,
)
from scraper.spiders.base import SearchParams
from scraper.spiders.casa import CasaSpider
from scraper.spiders.immobiliare import ImmobiliareSpider
from scraper.utils.rate_limiter import RateLimiter

logger = structlog.get_logger()

# Import optional spiders safely
try:
    from scraper.spiders.tecnocasa import TecnocasaSpider
except ImportError:
    TecnocasaSpider = None
try:
    from scraper.spiders.remax import RemaxSpider
except ImportError:
    RemaxSpider = None
try:
    from scraper.spiders.gabetti import GabettiSpider
except ImportError:
    GabettiSpider = None
try:
    from scraper.spiders.vistocasa import VistocasaSpider
except ImportError:
    VistocasaSpider = None


class _ProgressBar:
    """Simple ASCII progress bar that works in every terminal.

    Carries three independently updatable text slots so the single line
    stays informative:
      phase  — Ricerca | Elaborazione | OK | ERRORE
      detail — spider-supplied, e.g. "pag 3/50 (62 url)"
      stats  — runner-supplied after each DB flush, e.g. "+12 nuovi"

    In `parallel=True` mode the bar appends a newline per update instead
    of using carriage return, because parallel portals sharing a single
    stderr would otherwise garble each other's \\r-based redraws.

    Redraws during `advance()` are throttled to 4 Hz; state-change calls
    (set_phase, set_total, set_description, set_stats) always redraw.
    """

    _REDRAW_INTERVAL = 0.25

    def __init__(self, portal: str, parallel: bool = False):
        self._portal = portal
        self._parallel = parallel
        self._phase = ""
        self._detail = ""
        self._stats = ""
        self._total = 0
        self._done = 0
        self._start = time.time()
        self._last_draw = 0.0

    def set_phase(self, phase: str) -> None:
        label = {"search": "Ricerca", "fetch": "Elaborazione",
                 "done": "OK", "failed": "ERRORE"}.get(phase, phase)
        self._phase = label
        self._done = 0
        self._total = 0
        # Detail is per-phase (spider fills it in); stats carry across
        # phases so the final "OK" line keeps the running counts.
        self._detail = ""
        self._print_bar(force=True)

    def set_total(self, total: int) -> None:
        self._total = total
        self._print_bar(force=True)

    def set_description(self, text: str) -> None:
        # Strip portal prefix if the spider prepended it.
        if text.startswith(self._portal + " "):
            text = text[len(self._portal) + 1:]
        self._detail = text
        self._print_bar(force=True)

    def set_stats(self, text: str) -> None:
        self._stats = text
        self._print_bar(force=True)

    def advance(self, n: int = 1) -> None:
        self._done += n
        now = time.time()
        # Throttle tick redraws; always draw on completion.
        if self._total > 0 and self._done >= self._total:
            self._print_bar(force=True)
        elif now - self._last_draw >= self._REDRAW_INTERVAL:
            self._print_bar()

    def _print_bar(self, force: bool = False) -> None:
        elapsed = time.time() - self._start
        self._last_draw = time.time()
        tag = f"[{self._portal}]"

        if self._total > 0:
            pct = self._done / self._total
            filled = int(30 * pct)
            bar = "#" * filled + "-" * (30 - filled)
            line = f"{tag} {self._phase} [{bar}] {self._done}/{self._total}"
        else:
            # No total → spinner-style with elapsed time.
            line = f"{tag} {self._phase}..."

        if self._detail:
            line += f" {self._detail}"
        if self._stats:
            line += f" | {self._stats}"
        line += f" ({elapsed:.0f}s)"

        # Pad to clear any residue from a longer previous line.
        prefix = "\n" if self._parallel else "\r"
        sys.stderr.write(f"{prefix}{line:<110}")
        sys.stderr.flush()

    def finish(self, msg: str) -> None:
        elapsed = time.time() - self._start
        line = f"[{self._portal}] {msg} ({elapsed:.0f}s)"
        sys.stderr.write(f"\r{line:<110}\n")
        sys.stderr.flush()


SPIDERS: dict = {
    "immobiliare": ImmobiliareSpider,
    "casa": CasaSpider,
}
if TecnocasaSpider:
    SPIDERS["tecnocasa"] = TecnocasaSpider
if RemaxSpider:
    SPIDERS["remax"] = RemaxSpider
if GabettiSpider:
    SPIDERS["gabetti"] = GabettiSpider
if VistocasaSpider:
    SPIDERS["vistocasa"] = VistocasaSpider

BATCH_SIZE = 25


async def run_spider(
    portal: str,
    city: str,
    listing_type: str,
    reporter: _ProgressBar | None = None,
) -> None:
    """Run a single spider and process results."""
    spider_cls = SPIDERS.get(portal)
    if not spider_cls:
        sys.stderr.write(f"[{portal}] Portale sconosciuto\n")
        return

    if reporter is None:
        reporter = _ProgressBar(portal)

    rate_limiter = RateLimiter(requests_per_minute=settings.SCRAPE_RATE_LIMIT_RPM)
    spider = spider_cls(
        rate_limiter=rate_limiter,
        delay_min=settings.SCRAPE_REQUEST_DELAY_MIN,
        delay_max=settings.SCRAPE_REQUEST_DELAY_MAX,
        concurrency=getattr(settings, "SCRAPE_CONCURRENCY", 4),
        progress=reporter,
    )

    now = datetime.now(timezone.utc).isoformat()

    async with async_session() as db:
        run = ScrapeRun(
            portal=portal, status="running", started_at=now,
            config=json.dumps({"city": city, "listing_type": listing_type}),
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    fresh_ids: set[str] = set()
    if hasattr(settings, "SCRAPE_FRESH_HOURS"):
        fresh_ids = await get_fresh_source_ids(portal, settings.SCRAPE_FRESH_HOURS)

    params = SearchParams(city=city, listing_type=listing_type, fresh_source_ids=fresh_ids)
    found = 0
    new = 0
    updated = 0
    duplicate = 0
    skipped = 0
    errors = 0
    error_details: list[str] = []
    batch: list = []

    async def flush() -> None:
        nonlocal new, updated, duplicate, skipped, errors
        if not batch:
            return
        try:
            counts = await process_items_batch(batch, run_id)
            new += counts.get("new", 0)
            updated += counts.get("updated", 0)
            duplicate += counts.get("duplicate", 0)
            skipped += counts.get("skipped", 0)
        except Exception as e:
            errors += len(batch)
            error_details.append(f"batch_error: {e}")
        finally:
            batch.clear()
            reporter.set_stats(
                f"+{new} nuovi, {updated} agg, {duplicate} dup"
            )

    try:
        async for item in spider.run(params):
            found += 1
            batch.append(item)
            if len(batch) >= BATCH_SIZE:
                await flush()
        await flush()
    except Exception as e:
        errors += 1
        error_details.append(f"Spider error: {str(e)}")
    finally:
        await spider.close()

    if spider.fresh_skipped_ids:
        try:
            await bump_last_seen(portal, spider.fresh_skipped_ids)
            skipped += len(spider.fresh_skipped_ids)
        except Exception:
            pass

    finished_at = datetime.now(timezone.utc).isoformat()
    async with async_session() as db:
        result = await db.get(ScrapeRun, run_id)
        if result:
            result.status = "completed" if errors == 0 else "completed_with_errors"
            result.finished_at = finished_at
            result.listings_found = found
            result.listings_new = new
            result.listings_updated = updated
            result.errors = errors
            result.error_details = json.dumps(error_details) if error_details else None
            await db.commit()

    reporter.finish(f"FATTO: {found} trovati, {new} nuovi, {updated} agg, {duplicate} dup, {errors} err")


async def run_all_spiders(city: str, listing_type: str) -> None:
    portal_enabled = {
        "immobiliare": settings.SCRAPE_IMMOBILIARE_ENABLED,
        "casa": settings.SCRAPE_CASA_ENABLED,
        "tecnocasa": getattr(settings, "SCRAPE_TECNOCASA_ENABLED", False),
        "remax": getattr(settings, "SCRAPE_REMAX_ENABLED", False),
        "gabetti": getattr(settings, "SCRAPE_GABETTI_ENABLED", False),
        "vistocasa": getattr(settings, "SCRAPE_VISTOCASA_ENABLED", False),
    }
    active = [p for p, enabled in portal_enabled.items() if enabled and p in SPIDERS]

    if not active:
        print("Nessun portale abilitato.")
        return

    sys.stderr.write(f"\n=== Immo Scraper ===\n")
    sys.stderr.write(f"Portali: {', '.join(active)} | Citta: {city} | Tipo: {listing_type}\n\n")

    # Phase A: immobiliare first (canonical). Single portal → in-place
    # \r-style bar.
    if "immobiliare" in active:
        await run_spider("immobiliare", city, listing_type)

    # Phase B: rest in parallel. Because parallel portals share stderr,
    # we pass `parallel=True` to switch each bar to newline-mode so their
    # updates interleave as readable log lines instead of garbling a
    # single \r-redrawn line.
    rest = [p for p in active if p != "immobiliare"]
    if rest:
        sys.stderr.write(f"\n--- Fase 2: {', '.join(rest)} in parallelo ---\n")
        reporters = {p: _ProgressBar(p, parallel=True) for p in rest}
        await asyncio.gather(
            *(run_spider(p, city, listing_type, reporters[p]) for p in rest),
            return_exceptions=True,
        )

    sys.stderr.write(f"\nScraping completato.\n")


async def main(portal: str | None = None, city: str | None = None) -> None:
    log_path = Path(__file__).resolve().parents[1] / "scraper.log"
    setup_logging(log_file=log_path)
    await init_db()

    target_city = city or settings.SCRAPE_DEFAULT_CITY
    listing_type = settings.SCRAPE_DEFAULT_LISTING_TYPE

    if portal:
        sys.stderr.write(f"\n=== Immo Scraper ===\n")
        sys.stderr.write(f"Portale: {portal} | Citta: {target_city}\n\n")
        await run_spider(portal, target_city, listing_type)
    else:
        await run_all_spiders(target_city, listing_type)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Immo Scraper")
    parser.add_argument("--portal", type=str, help="Portal to scrape")
    parser.add_argument("--city", type=str, help="City to search")
    args = parser.parse_args()

    asyncio.run(main(portal=args.portal, city=args.city))
