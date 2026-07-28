"""CP-BACKTEST-HTTP-METADATA — parity metadata must survive the HTTP boundary.

The engine has computed parity and provenance metadata since F1-B' and F1-C, and
BacktestResponse has declared all of it as Optional since then. But the route
built the response by hand and named 18 of the 39 declared fields, so the other
21 reached callers as null — present in the JSON, because the route does not
exclude none, but empty. Measured on frozen candles: metadata non-null 0/21
before, 21/21 after, with every legacy metric and the equity/trades hashes
unchanged.

Everything here goes through the real ASGI stack: request validation, the real
router prefix, response-model validation and JSON serialization. Calling the
route function directly would prove nothing about serialization, which is
precisely where the fields were lost.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import textwrap

import httpx
import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine, BacktestReport
from app.collectors.binance_collector import BinanceCollector
from app.schemas.signal import BacktestResponse

pytestmark = pytest.mark.asyncio

LEGACY_FIELDS = [
    "total_trades", "wins", "losses", "breakevens", "expired", "win_rate",
    "loss_rate", "profit_factor", "sharpe_ratio", "sortino_ratio",
    "max_drawdown_pct", "average_return_pct", "average_rr", "expectancy_pct",
    "max_consecutive_wins", "max_consecutive_losses", "equity_curve", "trades_log",
]
META_FIELDS = [f for f in BacktestResponse.model_fields if f not in LEGACY_FIELDS]


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def _synthetic_candles(rows: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=rows, freq="h", tz="UTC")
    base = [100.0 + (i % 7) - (i % 3) for i in range(rows)]
    return pd.DataFrame(
        {
            "open": base,
            "high": [b + 1.0 for b in base],
            "low": [b - 1.0 for b in base],
            "close": [b + 0.5 for b in base],
            "volume": [1000.0 + i for i in range(rows)],
            "close_time": idx + pd.Timedelta(hours=1),
        },
        index=idx,
    )


def _sentinel_report() -> BacktestReport:
    """A report whose values are deliberately awkward.

    0, False, [] and None are the values a careless mapper turns into null or
    drops on a falsy check — so they are what the assertions are built on.
    """
    report = BacktestReport(
        total_trades=7, wins=3, losses=3, breakevens=1, expired=2,
        win_rate=42.86, loss_rate=42.86, profit_factor=1.23, sharpe_ratio=-0.5,
        sortino_ratio=None, max_drawdown_pct=1.75, average_return_pct=-0.12,
        average_rr=2.5, expectancy_pct=0.04, max_consecutive_wins=2,
        max_consecutive_losses=3,
        equity_curve=[{"t": "2026-01-01T00:00:00Z", "equity": 10000.0}],
        trades_log=[{"id": 1, "outcome": "win"}],
    )
    report.dropped_forming_bars = 0            # falsy, must not become null
    report.parity_limitations = []             # empty list, must stay a list
    report.confidence_distribution = {}        # empty dict, must stay a dict
    report.mtf_frames_available = 0
    report.candidates_rejected_by_confidence = 0
    report.candidates_holded_by_mtf = 0
    report.confidence_threshold = 65.0
    return report


@pytest.fixture
def route_path():
    from app.main import app
    for r in app.routes:
        if getattr(r, "path", "").endswith("/backtest"):
            return r.path
    pytest.fail("backtest route bulunamadi")


@pytest.fixture
def client(monkeypatch):
    """Real ASGI client with ONLY the auth dependencies overridden."""
    from app.main import app
    from app.auth.dependencies import get_current_user

    overridden = []
    for r in app.routes:
        if getattr(r, "path", "").endswith("/backtest"):
            for d in r.dependant.dependencies:
                fn = d.call
                if fn is get_current_user or "require_feature" in getattr(fn, "__qualname__", ""):
                    app.dependency_overrides[fn] = lambda: True
                    overridden.append(fn)

    async def fake_fetch(self, symbol, timeframe, limit=100, end_time_ms=None):
        return _synthetic_candles()

    monkeypatch.setattr(BinanceCollector, "fetch_ohlcv", fake_fetch)

    # Not entered as a context manager: several tests post twice, and an
    # AsyncClient cannot be reopened once closed. ASGITransport holds no
    # sockets, so nothing leaks by leaving it open.
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                            base_url="http://verify")
    for fn in overridden:
        app.dependency_overrides.pop(fn, None)


@pytest.fixture
def sentinel(monkeypatch):
    report = _sentinel_report()

    async def fake_run(self, **kw):
        return report

    monkeypatch.setattr(BacktestEngine, "run_backtest", fake_run)
    return report


async def _post(client, path, tf="1h"):
    return await client.post(path, json={"symbol": "BTCUSDT", "timeframe": tf},
                             timeout=120.0)


# --------------------------------------------------------------------------- #
# 1. every field reaches the JSON, with its own value
# --------------------------------------------------------------------------- #

async def test_every_metadata_field_reaches_the_json(client, route_path, sentinel):
    r = await _post(client, route_path)
    assert r.status_code == 200
    body = r.json()
    missing = [f for f in META_FIELDS if f not in body]
    assert not missing, f"JSON'da eksik metadata: {missing}"


async def test_every_metadata_value_equals_the_engine_report(client, route_path, sentinel):
    body = (await _post(client, route_path)).json()
    for f in META_FIELDS:
        assert body[f] == getattr(sentinel, f), (
            f"{f}: HTTP={body[f]!r} engine={getattr(sentinel, f)!r}")


async def test_every_legacy_value_equals_the_engine_report(client, route_path, sentinel):
    body = (await _post(client, route_path)).json()
    for f in LEGACY_FIELDS:
        assert body[f] == getattr(sentinel, f), (
            f"{f}: HTTP={body[f]!r} engine={getattr(sentinel, f)!r}")


async def test_field_names_are_carried_across_unchanged(client, route_path, sentinel):
    body = (await _post(client, route_path)).json()
    assert set(body) == set(BacktestResponse.model_fields), \
        "JSON alan kumesi sema ile birebir degil"


# --------------------------------------------------------------------------- #
# 2. the awkward values
# --------------------------------------------------------------------------- #

async def test_zero_is_not_turned_into_null(client, route_path, sentinel):
    """A falsy check in the mapper would drop these. `dropped_forming_bars == 0`
    means "nothing was cut", which is different from "we do not know"."""
    body = (await _post(client, route_path)).json()
    for f in ("dropped_forming_bars", "mtf_frames_available",
              "candidates_rejected_by_confidence", "candidates_holded_by_mtf"):
        assert body[f] == 0 and body[f] is not None, f"{f} sifir iken kayboldu"


async def test_empty_list_stays_a_list_and_empty_dict_stays_a_dict(client, route_path, sentinel):
    body = (await _post(client, route_path)).json()
    assert body["parity_limitations"] == [] and isinstance(body["parity_limitations"], list)
    assert body["confidence_distribution"] == {} and isinstance(body["confidence_distribution"], dict)


async def test_none_stays_none_and_is_not_confused_with_empty(client, route_path, sentinel):
    body = (await _post(client, route_path)).json()
    assert body["sortino_ratio"] is None
    assert body["parity_limitations"] is not None


async def test_a_float_stays_a_float(client, route_path, sentinel):
    body = (await _post(client, route_path)).json()
    assert isinstance(body["confidence_threshold"], float)
    assert body["confidence_threshold"] == 65.0


async def test_serialization_is_deterministic(client, route_path, sentinel):
    a = (await _post(client, route_path)).json()
    b = (await _post(client, route_path)).json()
    assert a == b


# --------------------------------------------------------------------------- #
# 3. the mapper cannot drift or leak
# --------------------------------------------------------------------------- #

async def test_the_report_carries_every_declared_response_field():
    """The drift guard. from_report raises on a missing attribute rather than
    defaulting to null — this is what keeps that raise unreachable in prod."""
    report_fields = {f.name for f in dataclasses.fields(BacktestReport)}
    missing = [f for f in BacktestResponse.model_fields if f not in report_fields]
    assert not missing, f"sema alani report'ta yok: {missing}"


async def test_report_only_fields_do_not_leak_into_the_api(client, route_path, sentinel):
    """The engine keeps bookkeeping the API contract never promised — planned and
    realized R, TP reach rates. A report-driven mapper would publish them."""
    report_only = {f.name for f in dataclasses.fields(BacktestReport)} - set(BacktestResponse.model_fields)
    assert report_only, "beklenen report-only alanlar kayboldu, test anlamsizlasti"
    body = (await _post(client, route_path)).json()
    leaked = [f for f in report_only if f in body]
    assert not leaked, f"sozlesmede olmayan alan sizdi: {leaked}"


async def test_values_reach_the_model_untransformed():
    """Identity against the report, checked BEFORE the model validates.

    Pydantic coerces on the way in — it turns the string "65.0" back into 65.0 —
    so a mapper that stringified every value would still emit a correct-looking
    response and only break the day a value stopped round-tripping. Identity is
    the only assertion that survives that, and it has to be made here, on the raw
    values, because after validation the transformation is invisible.
    """
    report = _sentinel_report()
    values = BacktestResponse.report_values(report)
    assert set(values) == set(BacktestResponse.model_fields)
    for name, value in values.items():
        original = getattr(report, name)
        assert value is original, (
            f"{name} rapordan degistirilerek alindi: {value!r} ({type(value).__name__}) "
            f"!= {original!r} ({type(original).__name__})")


async def test_from_report_raises_rather_than_silently_defaulting():
    class Partial:
        pass

    with pytest.raises(ValueError) as ei:
        BacktestResponse.from_report(Partial())
    assert "missing response fields" in str(ei.value)


async def test_the_route_does_not_hand_list_fields_any_more():
    """Structural, on the AST: a hand-written kwarg list is what dropped the
    fields, and re-introducing one would silently drop the next new field."""
    import app.api.routes.signals as R

    src = textwrap.dedent(inspect.getsource(R.backtest_endpoint))
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "BacktestResponse":
            pytest.fail("route hala elle BacktestResponse(...) kuruyor")
    calls = {getattr(n.func, "attr", None) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "from_report" in calls, "route from_report kullanmiyor"


async def test_metadata_is_not_hard_coded_in_the_route():
    import app.api.routes.signals as R

    src = inspect.getsource(R.backtest_endpoint)
    for literal in ("closed_candle_v1", "approximate", "not_applied", "exact", "65.0"):
        assert literal not in src, f"route metadata degerini hard-code ediyor: {literal}"


async def test_metadata_is_not_derived_from_the_request(client, route_path, sentinel):
    """Values must come from the report, not the payload. The sentinel report is
    identical for both requests, so identical metadata proves the source."""
    a = (await _post(client, route_path, "1h")).json()
    b = (await _post(client, route_path, "4h")).json()
    for f in META_FIELDS:
        assert a[f] == b[f], f"{f} istek payload'ina gore degisiyor"


# --------------------------------------------------------------------------- #
# 4. the rest of the contract is untouched
# --------------------------------------------------------------------------- #

async def test_openapi_documents_every_field():
    from app.main import app

    props = app.openapi()["components"]["schemas"]["BacktestResponse"]["properties"]
    missing = [f for f in BacktestResponse.model_fields if f not in props]
    assert not missing, f"OpenAPI'de eksik: {missing}"
    assert len(props) == len(BacktestResponse.model_fields)


@pytest.mark.parametrize("tf", ["1h", "4h"])
async def test_supported_timeframes_still_return_200(client, route_path, sentinel, tf):
    assert (await _post(client, route_path, tf)).status_code == 200


@pytest.mark.parametrize("tf", ["30m", "2h", "nonsense", "1H", ""])
async def test_unsupported_timeframes_still_return_422(client, route_path, sentinel, tf):
    r = await _post(client, route_path, tf)
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "literal_error"


async def test_no_silent_fallback_to_1h(client, route_path):
    """An unsupported timeframe must be refused, not quietly substituted — the
    engine must never even be reached."""
    called = []

    async def spy(self, **kw):
        called.append(kw.get("timeframe"))
        return _sentinel_report()

    import app.backtesting.engine as bt
    original = bt.BacktestEngine.run_backtest
    bt.BacktestEngine.run_backtest = spy
    try:
        r = await _post(client, route_path, "30m")
    finally:
        bt.BacktestEngine.run_backtest = original
    assert r.status_code == 422
    assert called == [], f"reddedilmesi gereken istek engine'e ulasti: {called}"


async def test_auth_and_feature_gate_are_still_declared_on_the_route():
    """Overriding a dependency in a test must not be able to hide its removal
    from the route."""
    from app.main import app
    from app.auth.dependencies import get_current_user

    for r in app.routes:
        if getattr(r, "path", "").endswith("/backtest"):
            names = [getattr(d.call, "__name__", "") for d in r.dependant.dependencies]
            calls = [d.call for d in r.dependant.dependencies]
            assert get_current_user in calls, "auth dependency route'tan kaldirilmis"
            assert len(names) >= 2, f"feature-gate dependency eksik: {names}"
            return
    pytest.fail("backtest route bulunamadi")


async def test_response_model_and_none_policy_are_unchanged():
    from app.main import app

    for r in app.routes:
        if getattr(r, "path", "").endswith("/backtest"):
            assert r.response_model is BacktestResponse
            assert r.response_model_exclude_none is False, \
                "exclude_none degistirildi — mevcut istemci sozlesmesi kirilir"
            assert r.response_model_exclude_unset is False
            return


async def test_a_legacy_client_reading_only_old_fields_still_works(client, route_path, sentinel):
    body = (await _post(client, route_path)).json()
    for f in LEGACY_FIELDS:
        assert f in body, f"legacy alan kayboldu: {f}"
    assert isinstance(body["equity_curve"], list)
    assert isinstance(body["trades_log"], list)
    assert body["total_trades"] == 7


# --------------------------------------------------------------------------- #
# 5. end to end through the real engine
# --------------------------------------------------------------------------- #

async def test_real_engine_metadata_survives_the_whole_chain(client, route_path):
    """No engine stub: synthetic candles go through the real backtest, the real
    route and the real serializer, and the parity labels come out intact."""
    body = (await _post(client, route_path)).json()
    assert body["backtest_input_version"] == "closed_candle_v1"
    assert body["overall_decision_parity"] == "approximate"
    assert body["adaptive_weights_parity"] == "not_applied"
    assert body["confidence_threshold"] == 65.0
    assert isinstance(body["parity_limitations"], list) and body["parity_limitations"]
    assert body["dropped_forming_bars"] is not None
    nulls = [f for f in META_FIELDS if body[f] is None]
    assert not nulls, f"gercek motor kosusunda null kalan metadata: {nulls}"
