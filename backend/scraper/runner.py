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
from app.models.scrape_run import ScrapeError, ScrapeRun
from app.services.alert_service import send_alert_digest
from app.services.scrape_service import enabled_portals
from app.utils.logging import setup_logging
from scraper.pipeline import (
    bump_last_seen,
    cities_of_source_ids,
    deactivate_stale_listings,
    get_known_source_ids,
    process_items_batch,
    refresh_source_urls,
    update_prices_from_observations,
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
        self._phase_key = ""  # canonical: search|fetch|done|failed
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
        # Canonical key kept separately — the DB heartbeat and the
        # frontend toast key off "search"/"fetch"/"done"/"failed", not
        # the localized terminal label.
        self._phase_key = phase
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


async def _persist_progress_loop(
    run_id: str,
    reporter: "_ProgressBar",
    stop_event: asyncio.Event,
    interval: float = 2.0,
) -> None:
    """Heartbeat task: copies reporter._phase/_done/_total onto the
    ScrapeRun row every ``interval`` seconds. The frontend polls those
    values to render progress + ETA, so this is the bridge between the
    sync reporter and the async DB layer.

    Runs until ``stop_event`` is set. Errors are swallowed — we never
    want a transient DB hiccup to take down the spider.
    """
    from app.database import async_session as _session
    from app.models.scrape_run import ScrapeRun as _Run

    while not stop_event.is_set():
        try:
            async with _session() as db:
                row = await db.get(_Run, run_id)
                if row is not None:
                    row.progress_done = reporter._done
                    row.progress_total = reporter._total
                    row.phase = reporter._phase_key or None
                    row.last_progress_at = datetime.now(timezone.utc).isoformat()
                    await db.commit()
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def run_spider(
    portal: str,
    city: str,
    listing_type: str,
    reporter: _ProgressBar | None = None,
    job_id: str | None = None,
) -> None:
    """Run a single spider and process results.

    ``job_id`` ties this run to its sibling per-portal runs so the
    status endpoint can aggregate one logical scrape job. Standalone
    invocations (CLI single portal) get their own fresh id.
    """
    import uuid as _uuid
    if job_id is None:
        job_id = _uuid.uuid4().hex

    spider_cls = SPIDERS.get(portal)
    if not spider_cls:
        sys.stderr.write(f"[{portal}] Portale sconosciuto\n")
        return

    if reporter is None:
        reporter = _ProgressBar(portal)

    rpm = settings.SCRAPE_RATE_LIMITS.get(portal, settings.SCRAPE_RATE_LIMIT_RPM)
    rate_limiter = RateLimiter(requests_per_minute=rpm)
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
            phase="search",
            last_progress_at=now,
            job_id=job_id,
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    # Start the heartbeat task — keeps the DB row's progress fields in
    # sync with the sync reporter without intrusively rewiring the
    # spider/reporter callbacks.
    progress_stop = asyncio.Event()
    progress_task = asyncio.create_task(_persist_progress_loop(run_id, reporter, progress_stop))

    # Fetch every source_id we've ever recorded for this portal — the
    # spider will skip the detail-page round-trip for any of these. The
    # first observation is treated as immutable, so subsequent runs only
    # bump last_seen_at; existing rows are never overwritten.
    known_ids = await get_known_source_ids(portal)

    params = SearchParams(city=city, listing_type=listing_type, known_source_ids=known_ids)
    found = 0
    new = 0
    updated = 0
    duplicate = 0
    skipped = 0
    errors = 0
    error_details: list[str] = []
    batch: list = []
    # Cities this run observed: the only ones its coverage says anything about.
    seen_cities: set[str] = set()

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

    spider_crashed = False
    try:
        async for item in spider.run(params):
            found += 1
            if item.city:
                seen_cities.add(item.city.lower())
            batch.append(item)
            if len(batch) >= BATCH_SIZE:
                await flush()
        await flush()
    except Exception as e:
        spider_crashed = True
        errors += 1
        error_details.append(f"Spider error: {e}")
        spider.record_error("spider", None, None, f"{type(e).__name__}: {e}")
    finally:
        await spider.close()

    price_changes = 0
    if spider.known_skipped_ids:
        try:
            await bump_last_seen(portal, spider.known_skipped_ids)
            skipped += len(spider.known_skipped_ids)
        except Exception as e:
            spider.record_error("spider", None, None, f"bump_last_seen failed: {e}")
        try:
            await refresh_source_urls(portal, spider.observed_urls)
        except Exception as e:
            spider.record_error("spider", None, None, f"url refresh failed: {e}")
        # Diff search-card prices vs stored prices for known listings.
        # Only price/price_previous/price_changed_at are touched — the
        # content snapshot stays immutable.
        if spider.observed_prices:
            try:
                pc = await update_prices_from_observations(portal, spider.observed_prices)
                price_changes = pc.get("changed", 0)
                if price_changes:
                    reporter.set_stats(
                        f"+{new} nuovi, {updated} agg, {duplicate} dup, {price_changes} prezzi variati"
                    )
            except Exception as e:
                spider.record_error("spider", None, None, f"price diff failed: {e}")

    # Deactivate listings that vanished from the portal — but only when this
    # run saw the whole catalog. With truncated pagination, a blocked portal
    # or a crash, "not seen" just means "not reached".
    coverage_complete = spider.coverage_complete and not spider_crashed and spider.listings_seen > 0
    deactivated = 0
    if coverage_complete:
        try:
            seen_cities |= await cities_of_source_ids(portal, spider.known_skipped_ids)
            deactivated = await deactivate_stale_listings(
                portal, settings.LISTING_INACTIVE_DAYS, seen_cities
            )
        except Exception as e:
            spider.record_error("spider", None, None, f"deactivation failed: {e}")

    # Stop the heartbeat task before the final write so the two don't
    # race on the same row.
    progress_stop.set()
    try:
        await asyncio.wait_for(progress_task, timeout=3.0)
    except (asyncio.TimeoutError, Exception):
        pass

    # "gone" = a listing removed between search and detail fetch —
    # informational, not a run failure.
    failures = [e for e in spider.errors if e["kind"] != "gone"]
    errors += len(failures)
    ok = errors == 0

    finished_at = datetime.now(timezone.utc).isoformat()
    async with async_session() as db:
        result = await db.get(ScrapeRun, run_id)
        if result:
            result.status = "completed" if ok else "completed_with_errors"
            result.finished_at = finished_at
            result.listings_found = found
            result.listings_new = new
            result.listings_updated = updated
            result.listings_deactivated = deactivated
            result.listings_seen = spider.listings_seen
            result.coverage_complete = coverage_complete
            result.errors = errors
            result.error_details = json.dumps(error_details) if error_details else None
            # Final progress write — set done = total so the UI shows
            # 100% even if the heartbeat missed the last tick.
            result.phase = "done" if ok else "failed"
            result.last_progress_at = finished_at
            if result.progress_total:
                result.progress_done = result.progress_total
            db.add_all(
                ScrapeError(run_id=run_id, portal=portal, created_at=finished_at, **err)
                for err in spider.errors
            )
            await db.commit()

    summary = (
        f"FATTO: {spider.listings_seen} visti, {found} nuovi-dettaglio, {new} nuovi, "
        f"{updated} agg, {duplicate} dup, {errors} err"
    )
    if price_changes:
        summary += f", {price_changes} prezzi variati"
    if deactivated:
        summary += f", {deactivated} disattivati"
    if not coverage_complete:
        summary += " (copertura parziale)"
    reporter.finish(summary)


async def run_all_spiders(city: str, listing_type: str) -> None:
    import uuid as _uuid
    # One job_id for the whole invocation — every per-portal run carries
    # it so /api/scrape/status can aggregate exactly this job.
    job_id = _uuid.uuid4().hex

    active = [p for p in enabled_portals() if p in SPIDERS]

    if not active:
        print("Nessun portale abilitato.")
        return

    sys.stderr.write("\n=== Immo Scraper ===\n")
    sys.stderr.write(f"Portali: {', '.join(active)} | Citta: {city} | Tipo: {listing_type}\n\n")

    # Phase A: immobiliare first (canonical). Single portal → in-place
    # \r-style bar.
    if "immobiliare" in active:
        await run_spider("immobiliare", city, listing_type, job_id=job_id)

    # Phase B: rest in parallel. Because parallel portals share stderr,
    # we pass `parallel=True` to switch each bar to newline-mode so their
    # updates interleave as readable log lines instead of garbling a
    # single \r-redrawn line.
    rest = [p for p in active if p != "immobiliare"]
    if rest:
        sys.stderr.write(f"\n--- Fase 2: {', '.join(rest)} in parallelo ---\n")
        reporters = {p: _ProgressBar(p, parallel=True) for p in rest}
        await asyncio.gather(
            *(run_spider(p, city, listing_type, reporters[p], job_id=job_id) for p in rest),
            return_exceptions=True,
        )

    sys.stderr.write("\nScraping completato.\n")


async def main(portal: str | None = None, city: str | None = None) -> None:
    log_path = Path(__file__).resolve().parents[1] / "scraper.log"
    setup_logging(log_file=log_path)
    await init_db()

    target_city = city or settings.SCRAPE_DEFAULT_CITY
    listing_type = settings.SCRAPE_DEFAULT_LISTING_TYPE

    if portal:
        sys.stderr.write("\n=== Immo Scraper ===\n")
        sys.stderr.write(f"Portale: {portal} | Citta: {target_city}\n\n")
        await run_spider(portal, target_city, listing_type)
    else:
        await run_all_spiders(target_city, listing_type)

    # Saved-search digest (no-op unless SMTP is configured). A mail failure
    # must not turn a good scrape into a failed process.
    try:
        sent = await send_alert_digest()
        if sent:
            sys.stderr.write(f"Avvisi: e-mail inviata per {sent} ricerche salvate.\n")
    except Exception as e:
        logger.exception("alert_digest_failed")
        sys.stderr.write(f"Avvisi: invio e-mail fallito ({e}).\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Immo Scraper")
    parser.add_argument("--portal", type=str, help="Portal to scrape")
    parser.add_argument("--city", type=str, help="City to search")
    args = parser.parse_args()

    asyncio.run(main(portal=args.portal, city=args.city))
