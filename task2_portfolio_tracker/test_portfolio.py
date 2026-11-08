import csv

import pytest

import portfolio
from portfolio import Position, PositionResult

SP500 = {
    "AAPL": {"name": "Apple Inc.", "sector": "Information Technology"},
    "XOM": {"name": "Exxon Mobil", "sector": "Energy"},
}


def scripted(*answers):
    replies = iter(answers)
    return lambda _prompt="": next(replies)


def make_result(ticker, buy, now, shares=1.0):
    invested, value = buy * shares, now * shares
    return PositionResult(
        ticker=ticker, sector="Unknown", shares=shares, buy_price=buy,
        current_price=now, invested=invested, market_value=value,
        gain_loss_pct=(value - invested) / invested * 100,
    )


# ------------------------------------------------------- input guards
@pytest.mark.parametrize("raw,expected", [
    ("aapl", "AAPL"), (" msft ", "MSFT"), ("brk.b", "BRK.B"),
    ("BF-B", "BF-B"),
])
def test_parse_ticker_accepts_valid(raw, expected):
    assert portfolio.parse_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "AAPL!", "TOOLONGX", "123", "A B"])
def test_parse_ticker_rejects_invalid(raw):
    with pytest.raises(ValueError):
        portfolio.parse_ticker(raw)


@pytest.mark.parametrize("raw", ["abc", "", "0", "-5", "nan", "inf", "1e99"])
def test_parse_number_rejects_bad_values(raw):
    with pytest.raises(ValueError):
        portfolio.parse_number(raw, "Shares", 1000)


def test_parse_number_accepts_commas():
    assert portfolio.parse_number("1,250.5", "Shares", 10_000) == 1250.5


def test_add_position_merges_with_average_cost():
    book = {}
    portfolio.add_position(book, "AAPL", 10, 150.0)
    portfolio.add_position(book, "AAPL", 10, 250.0)
    assert book["AAPL"].shares == 20
    assert book["AAPL"].buy_price == pytest.approx(200.0)


def test_collect_positions_validates_and_merges():
    answers = scripted(
        "ZZZZ",                    # not in the dataset
        "AAPL", "-5",              # negative shares
        "AAPL", "10", "abc",       # price is not a number
        "AAPL", "10", "150",       # valid
        "aapl", "10", "250",       # duplicate, merged
        "",                        # finish
    )
    book = portfolio.collect_positions(SP500, answers)
    assert list(book) == ["AAPL"]
    assert book["AAPL"].shares == 20
    assert book["AAPL"].buy_price == pytest.approx(200.0)


def test_collect_positions_survives_end_of_input():
    def no_input(_prompt=""):
        raise EOFError

    assert portfolio.collect_positions(SP500, no_input) == {}


# ------------------------------------------------------- data loading
def test_load_sp500_reads_symbols_and_sectors(tmp_path):
    path = tmp_path / "sp.csv"
    path.write_text(
        "\ufeffSymbol,Security,GICS Sector\n"
        "AAPL,Apple Inc.,Information Technology\n",
        encoding="utf-8",
    )
    assert portfolio.load_sp500(path)["AAPL"]["sector"] == (
        "Information Technology"
    )


def test_load_sp500_missing_file_returns_empty(tmp_path):
    assert portfolio.load_sp500(tmp_path / "nope.csv") == {}


def test_load_sp500_malformed_file_returns_empty(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("Ticker,Name\nAAPL,Apple\n")
    assert portfolio.load_sp500(path) == {}


def test_load_holdings_file_skips_bad_rows(tmp_path, capsys):
    path = tmp_path / "holdings.csv"
    path.write_text(
        "Ticker,Shares,Buy_Price\n"
        "AAPL,10,150\n"
        "bad!,1,1\n"
        "XOM,-3,100\n"
        "XOM,4,100\n"
    )
    book = portfolio.load_holdings_file(path, SP500)
    assert set(book) == {"AAPL", "XOM"}
    assert book["XOM"].shares == 4
    out = capsys.readouterr().out
    assert "Row 3 skipped" in out and "Row 4 skipped" in out


# --------------------------------------------------------- calculation
def test_evaluate_calculates_gain_and_sector():
    book = {"AAPL": Position(10, 150.0)}
    (result,) = portfolio.evaluate(book, lambda t: 200.0, SP500)
    assert result.invested == 1500 and result.market_value == 2000
    assert result.gain_loss_pct == pytest.approx(33.33, abs=0.01)
    assert result.sector == "Information Technology"


def test_evaluate_skips_tickers_without_a_price(capsys):
    book = {"AAPL": Position(1, 100.0), "XOM": Position(1, 100.0)}
    results = portfolio.evaluate(
        book, lambda t: 120.0 if t == "AAPL" else None, SP500
    )
    assert [r.ticker for r in results] == ["AAPL"]
    assert "Skipping XOM" in capsys.readouterr().out


def test_summarize_totals():
    results = [make_result("AAPL", 100, 150), make_result("XOM", 100, 50)]
    assert portfolio.summarize(results) == (200, 200, 0)


def test_summarize_empty_list_is_safe():
    assert portfolio.summarize([]) == (0, 0, 0.0)


def test_live_price_failure_returns_none(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("no yfinance")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert portfolio.get_live_price("AAPL") is None


# -------------------------------------------------------------- output
def test_save_csv_appends_a_log(tmp_path):
    path = tmp_path / "out.csv"
    results = [make_result("AAPL", 100, 110)]
    assert portfolio.save_csv(results, path) is True
    assert portfolio.save_csv(results, path) is True
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4                       # (1 holding + TOTAL) x 2
    assert rows[0]["ticker"] == "AAPL" and rows[1]["ticker"] == "TOTAL"
    assert rows[1]["gain_loss_pct"] == "10.0"


def test_save_csv_reports_unwritable_path(tmp_path, capsys):
    assert portfolio.save_csv([make_result("AAPL", 1, 2)], tmp_path) is False
    assert "Could not write" in capsys.readouterr().out


# ------------------------------------------------------------ main()
def test_main_demo_offline_end_to_end(tmp_path, capsys):
    out = tmp_path / "summary.csv"
    code = portfolio.main(["--demo", "--offline", "--output", str(out)])
    text = capsys.readouterr().out
    assert code == 0
    assert "AAPL" in text and "Overall" in text
    assert out.exists()


def test_main_without_input_exits_cleanly(tmp_path):
    def no_input(_prompt=""):
        raise EOFError

    assert portfolio.main(
        ["--output", str(tmp_path / "x.csv")], input_fn=no_input
    ) == 1


def test_main_missing_holdings_file(tmp_path):
    assert portfolio.main(["--file", str(tmp_path / "none.csv")]) == 1


def test_main_reports_unpriceable_portfolio(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio, "get_live_price", lambda t: None)
    code = portfolio.main(["--demo", "--output", str(tmp_path / "x.csv")])
    assert code == 1
