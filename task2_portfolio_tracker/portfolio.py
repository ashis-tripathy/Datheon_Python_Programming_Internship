"""Stock portfolio performance tracker (Task 2).

Usage:
    python portfolio.py --demo               # sample holdings, live prices
    python portfolio.py --demo --offline     # sample holdings, sample prices
    python portfolio.py --file holdings.csv  # holdings from a CSV file
    python portfolio.py                      # type holdings interactively
    python portfolio.py --demo --ai          # add the optional Gemini report
"""
import argparse
import csv
import math
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

BASE_DIR = Path(__file__).resolve().parent
SP500_PATH = BASE_DIR / "data" / "sp500_tickers.csv"
OUTPUT_PATH = BASE_DIR / "portfolio_summary.csv"

TICKER_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")  # AAPL, BRK.B, BF-B
MAX_SHARES = 1_000_000_000
MAX_PRICE = 10_000_000

DEMO_HOLDINGS = [
    ("AAPL", 10, 150.0),
    ("MSFT", 5, 300.0),
    ("XOM", 8, 100.0),
    ("JPM", 4, 180.0),
]
# Fixed prices for --offline runs (not real market data).
SAMPLE_PRICES = {
    "AAPL": 230.0, "MSFT": 420.0, "XOM": 110.0,
    "JPM": 220.0, "GOOGL": 175.0, "AMZN": 200.0,
}
CSV_COLUMNS = [
    "timestamp", "ticker", "sector", "shares", "buy_price",
    "current_price", "invested", "market_value", "gain_loss_pct",
]

PriceFn = Callable[[str], Optional[float]]


@dataclass
class Position:
    """One holding in the portfolio dictionary."""

    shares: float
    buy_price: float


@dataclass
class PositionResult:
    """A holding valued at the current price."""

    ticker: str
    sector: str
    shares: float
    buy_price: float
    current_price: float
    invested: float
    market_value: float
    gain_loss_pct: float


# ---------------------------------------------------------------- input
def parse_ticker(raw: str) -> str:
    """Validate a ticker symbol with a regular expression."""
    ticker = raw.strip().upper()
    if not TICKER_RE.match(ticker):
        raise ValueError(
            f"'{raw.strip()}' is not a valid ticker (e.g. AAPL, BRK.B)."
        )
    return ticker


def parse_number(raw: str, label: str, maximum: float) -> float:
    """Parse a positive, finite number no larger than `maximum`."""
    try:
        value = float(raw.strip().replace(",", ""))
    except ValueError:
        raise ValueError(f"{label} must be a number.") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    if value > maximum:
        raise ValueError(f"{label} is unrealistically large.")
    return value


def add_position(
    portfolio: dict[str, Position], ticker: str, shares: float, price: float
) -> None:
    """Add a holding. Repeated tickers merge using the average cost."""
    existing = portfolio.get(ticker)
    if existing is None:
        portfolio[ticker] = Position(shares, price)
        return
    total = existing.shares + shares
    cost = existing.shares * existing.buy_price + shares * price
    portfolio[ticker] = Position(total, cost / total)


def load_sp500(path: Path = SP500_PATH) -> dict[str, dict[str, str]]:
    """Load {symbol: {name, sector}} from the S&P 500 dataset."""
    if not path.exists():
        print(f"Note: {path.name} not found - ticker check skipped.")
        return {}
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            return {
                row["Symbol"].strip().upper(): {
                    "name": row.get("Security", ""),
                    "sector": row.get("GICS Sector") or "Unknown",
                }
                for row in csv.DictReader(handle)
            }
    except (OSError, KeyError, csv.Error, UnicodeDecodeError) as exc:
        print(f"Warning: cannot read {path.name} ({exc}); check skipped.")
        return {}


def collect_positions(
    sp500: dict, input_fn: Callable[[str], str] = input
) -> dict[str, Position]:
    """Ask the user for holdings until an empty ticker is entered."""
    portfolio: dict[str, Position] = {}
    print("Enter your holdings. Press Enter on an empty ticker to finish.\n")
    while True:
        try:
            raw = input_fn("Ticker: ")
            if not raw.strip():
                break
            ticker = parse_ticker(raw)
            if sp500 and ticker not in sp500:
                raise ValueError(f"{ticker} is not in the S&P 500 dataset.")
            shares = parse_number(input_fn("  Shares: "), "Shares", MAX_SHARES)
            price = parse_number(
                input_fn("  Buy price: "), "Buy price", MAX_PRICE
            )
        except ValueError as exc:
            print(f"  Invalid input: {exc}\n")
            continue
        except EOFError:
            break
        add_position(portfolio, ticker, shares, price)
    return portfolio


def load_holdings_file(path: Path, sp500: dict) -> dict[str, Position]:
    """Read holdings from a CSV with columns ticker, shares, buy_price."""
    portfolio: dict[str, Position] = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for number, raw_row in enumerate(csv.DictReader(handle), start=2):
            row = {
                (key or "").strip().lower(): (value or "")
                for key, value in raw_row.items()
            }
            try:
                ticker = parse_ticker(row.get("ticker", ""))
                if sp500 and ticker not in sp500:
                    raise ValueError(f"{ticker} is not in the S&P 500 data.")
                shares = parse_number(
                    row.get("shares", ""), "Shares", MAX_SHARES
                )
                price = parse_number(
                    row.get("buy_price", ""), "Buy price", MAX_PRICE
                )
            except ValueError as exc:
                print(f"Row {number} skipped: {exc}")
                continue
            add_position(portfolio, ticker, shares, price)
    return portfolio


# --------------------------------------------------------------- prices
def get_live_price(ticker: str) -> Optional[float]:
    """Latest close from Yahoo Finance, or None if it cannot be fetched."""
    try:
        import yfinance  # optional: --offline works without it

        history = yfinance.Ticker(ticker.replace(".", "-")).history(
            period="5d"
        )
    except Exception:  # network or library problems must not crash the run
        return None
    if history.empty:
        return None
    return float(history["Close"].iloc[-1])


def get_sample_price(ticker: str) -> Optional[float]:
    """Fixed demo price used by --offline."""
    return SAMPLE_PRICES.get(ticker)


# ----------------------------------------------------------- calculation
def evaluate(
    portfolio: dict[str, Position], price_fn: PriceFn, sp500: dict
) -> list[PositionResult]:
    """Value every holding; tickers without a price are skipped."""
    results = []
    for ticker, position in portfolio.items():
        price = price_fn(ticker)
        if price is None or price <= 0:
            print(f"Skipping {ticker}: could not get a price.")
            continue
        invested = position.shares * position.buy_price
        value = position.shares * price
        results.append(PositionResult(
            ticker=ticker,
            sector=sp500.get(ticker, {}).get("sector", "Unknown"),
            shares=position.shares,
            buy_price=position.buy_price,
            current_price=price,
            invested=invested,
            market_value=value,
            gain_loss_pct=(value - invested) / invested * 100,
        ))
    return results


def summarize(results: list[PositionResult]) -> tuple[float, float, float]:
    """Return (total invested, total market value, overall % change)."""
    invested = sum(r.invested for r in results)
    value = sum(r.market_value for r in results)
    pct = (value - invested) / invested * 100 if invested else 0.0
    return invested, value, pct


# --------------------------------------------------------------- output
def print_report(results: list[PositionResult]) -> None:
    header = (
        f"{'Ticker':<8}{'Shares':>9}{'Buy':>10}{'Now':>10}"
        f"{'Value':>13}{'P/L %':>9}"
    )
    print(f"\n{header}\n{'-' * len(header)}")
    for r in results:
        print(
            f"{r.ticker:<8}{r.shares:>9.2f}{r.buy_price:>10.2f}"
            f"{r.current_price:>10.2f}{r.market_value:>13,.2f}"
            f"{r.gain_loss_pct:>8.2f}%"
        )
    invested, value, pct = summarize(results)
    print("-" * len(header))
    print(f"Invested {invested:,.2f} | Value {value:,.2f} | "
          f"Overall {pct:+.2f}%")


def save_csv(results: list[PositionResult], path: Path = OUTPUT_PATH) -> bool:
    """Append this run to the CSV log, followed by a TOTAL row."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_new = not path.exists()
    invested, value, pct = summarize(results)
    try:
        with open(path, "a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            if is_new:
                writer.writeheader()
            for result in results:
                row = {
                    key: round(val, 2) if isinstance(val, float) else val
                    for key, val in asdict(result).items()
                }
                writer.writerow({"timestamp": stamp, **row})
            writer.writerow({
                "timestamp": stamp,
                "ticker": "TOTAL",
                "invested": round(invested, 2),
                "market_value": round(value, 2),
                "gain_loss_pct": round(pct, 2),
            })
    except OSError as exc:
        print(f"Could not write {path.name}: {exc}")
        return False
    print(f"\nSaved to {path}")
    return True


def run_ai_report(results: list[PositionResult]) -> None:
    """Optional Gemini report (needs analyst.py and GEMINI_API_KEY)."""
    try:
        from google import genai
        from analyst import AnalysisError, analyze_portfolio
        from telemetry import summarize as summarize_telemetry
    except ImportError as exc:
        print(f"AI report skipped: {exc}")
        return
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("AI report skipped: GEMINI_API_KEY is not set.")
        return
    try:
        analysis = analyze_portfolio(
            [asdict(r) for r in results], genai.Client(api_key=key)
        )
    except AnalysisError as exc:
        print(f"AI report unavailable: {exc}")
        return
    print(f"\n--- AI analysis (risk {analysis.risk_level}, "
          f"diversification {analysis.diversification_score}/10) ---")
    print(analysis.summary)
    for item in analysis.insights:
        print(f"  {item.ticker:<6}{item.verdict:<5} {item.comment}")
    print("\nLLM telemetry:", summarize_telemetry())


# ------------------------------------------------------------------ CLI
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Track the performance of a stock portfolio."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--demo", action="store_true", help="use built-in sample holdings"
    )
    source.add_argument(
        "--file", metavar="CSV",
        help="read holdings from a CSV (ticker,shares,buy_price)",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="use built-in sample prices instead of live prices",
    )
    parser.add_argument(
        "--ai", action="store_true", help="add the optional Gemini analysis"
    )
    parser.add_argument(
        "--output", default=str(OUTPUT_PATH), help="CSV log file to append to"
    )
    return parser.parse_args(argv)


def main(
    argv: Optional[list[str]] = None,
    input_fn: Callable[[str], str] = input,
) -> int:
    """Entry point. Returns a process exit code."""
    args = parse_args(argv)
    sp500 = load_sp500()
    try:
        if args.demo:
            portfolio: dict[str, Position] = {}
            for ticker, shares, price in DEMO_HOLDINGS:
                add_position(portfolio, ticker, shares, price)
        elif args.file:
            portfolio = load_holdings_file(Path(args.file), sp500)
        else:
            portfolio = collect_positions(sp500, input_fn)
    except OSError as exc:
        print(f"Error: cannot read the holdings file: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    if not portfolio:
        print("No holdings to report. Use --demo, --file, or type holdings.")
        return 1
    if args.offline:
        print("(Using built-in sample prices.)")
    price_fn = get_sample_price if args.offline else get_live_price
    results = evaluate(portfolio, price_fn, sp500)
    if not results:
        print("No positions could be priced.")
        return 1
    print_report(results)
    save_csv(results, Path(args.output))
    if args.ai:
        run_ai_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
