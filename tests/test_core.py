import numpy as np
import pandas as pd

from qt.indicators import rsi, macd
from qt.similarity import window_correlations, zscore
from qt.data import is_st, is_main_board
from qt.dashboard import board_of, price_band, rsi_zone, search_stocks
from qt.watchlist import add_watch, load_watchlist, remove_watch, save_watchlist


def test_rsi_bounds():
    close = pd.Series(np.linspace(10, 20, 80))
    values = rsi(close, 14).dropna()
    assert values.min() >= 0
    assert values.max() <= 100
    assert values.iloc[-1] > 50


def test_macd_gold_cross_shape():
    x = np.concatenate([np.linspace(20, 10, 40), np.linspace(10, 18, 40)])
    close = pd.Series(x)
    out = macd(close)
    assert "dif" in out.columns
    assert len(out) == len(close)


def test_window_corr_self():
    q = np.sin(np.linspace(0, np.pi, 20))
    series = np.concatenate([np.random.default_rng(0).normal(size=30), q, np.zeros(5)])
    corrs = window_correlations(q, series)
    assert np.nanmax(corrs) > 0.99
    assert np.allclose(zscore(q).std(), 1.0, atol=1e-6)


def test_board_and_st_filters():
    assert is_st("*ST 华钰")
    assert is_st("ST金科")
    assert not is_st("平安银行")
    assert is_main_board("002195")
    assert is_main_board("600519")
    assert not is_main_board("300750")
    assert not is_main_board("688981")
    assert not is_main_board("301000")


def test_dashboard_classifiers():
    assert board_of("600519") == "沪市主板"
    assert board_of("000001") == "深市主板"
    assert board_of("002195") == "中小板"
    assert price_band(4.2) == "5元以下"
    assert price_band(9.9) == "5–10元"
    assert price_band(12) == "10–15元"
    assert price_band(18.5) == "15–20元"
    assert rsi_zone(28) == "超卖"
    assert rsi_zone(55) == "中性"
    assert rsi_zone(81) == "超买"


def test_watchlist_roundtrip(tmp_path, monkeypatch):
    from qt import watchlist as wl

    monkeypatch.setattr(wl, "WATCH_PATH", tmp_path / "watchlist.json")
    save_watchlist([])
    out = add_watch("2195")
    assert out["added"] is True
    codes = [m["symbol"] for m in load_watchlist()]
    assert "002195" in codes
    remove_watch("002195")
    assert load_watchlist() == []


def test_search_empty_query():
    assert search_stocks("") == []


def test_ashare_commission_stamp_on_sell_only():
    from qt.backtest_engine import AShareCommission

    comm = AShareCommission()
    buy = comm._getcommission(100, 10.0, True)
    sell = comm._getcommission(-100, 10.0, True)
    assert buy == 5.0
    assert sell == 6.0


def test_lot_size_rounds_to_100():
    cash, price, percents, lot = 100000.0, 11.23, 95, 100
    size = int((cash * percents / 100.0) / price)
    size = (size // lot) * lot
    assert size >= lot
    assert size % lot == 0


def test_supertrend_flips_on_trend():
    from qt.indicators import supertrend

    n = 80
    idx = pd.bdate_range("2022-01-03", periods=n)
    close = pd.Series(np.linspace(8, 16, n), index=idx)
    df = pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )
    st = supertrend(df)
    assert st["dir"].dropna().iloc[-1] == 1
    assert st["line"].dropna().iloc[-1] < close.iloc[-1]


def test_rsi2_reacts_to_dip():
    from qt.indicators import rsi

    close = pd.Series(np.concatenate([np.linspace(10, 14, 40), [13.2, 12.4, 11.6, 11.1]]))
    values = rsi(close, 2).dropna()
    assert values.min() >= 0
    assert values.max() <= 100
    assert values.iloc[-1] < 20


def test_lookback_prefers_recent_window():
    idx = pd.bdate_range("2020-01-02", periods=80)
    close = pd.Series(
        np.concatenate([np.sin(np.linspace(0, 2 * np.pi, 20)), np.linspace(0, 1, 60)]),
        index=idx,
    )
    df = pd.DataFrame({"close": close})
    query = close.iloc[:20]
    from qt.similarity import best_window

    full = best_window(query, df, lookback_days=0)
    recent = best_window(query, df, lookback_days=20)
    assert full is not None
    assert recent is not None
    assert full["start"] == idx[0].strftime("%Y-%m-%d")
    assert recent["start"] == idx[-20].strftime("%Y-%m-%d")


def test_condition_conflicts():
    from qt.screener import condition_conflicts

    clash = condition_conflicts(
        [{"field": "rsi14", "op": ">", "value": 70}, {"field": "rsi14", "op": "<", "value": 30}]
    )
    assert clash
    ok = condition_conflicts(
        [
            {"field": "pe", "op": "<", "value": 25},
            {"field": "pe", "op": ">", "value": 0},
            {"field": "pct_20", "op": ">", "value": 5},
        ]
    )
    assert ok == []
    enum_clash = condition_conflicts(
        [
            {"field": "macd_cross", "op": "=", "value": "golden"},
            {"field": "macd_cross", "op": "=", "value": "dead"},
        ]
    )
    assert enum_clash
    equal_ok = condition_conflicts(
        [{"field": "rsi14", "op": ">=", "value": 30}, {"field": "rsi14", "op": "<=", "value": 30}]
    )
    assert equal_ok == []


def test_pattern_library_roundtrip(tmp_path, monkeypatch):
    from qt import library as lib

    monkeypatch.setattr(lib, "PATTERNS_PATH", tmp_path / "patterns.json")
    item = lib.save_pattern({"name": "冲高", "symbol": "002195", "start": "2023-01-01", "end": "2023-03-01"})
    assert item["id"]
    assert lib.get_pattern(item["id"])["name"] == "冲高"
    lib.delete_pattern(item["id"])
    assert lib.load_patterns() == []


def test_static_screen_can_drop_symbol(tmp_path, monkeypatch):
    from qt import library as lib

    monkeypatch.setattr(lib, "SCREENS_PATH", tmp_path / "screens.json")
    saved = lib.save_screen(
        {
            "name": "超卖",
            "mode": "static",
            "universe": "demo",
            "conditions": [],
            "hits": [{"symbol": "000001", "name": "平安银行"}, {"symbol": "002195", "name": "二三四五"}],
        }
    )
    out = lib.remove_screen_hit(saved["id"], "000001")
    codes = [h["symbol"] for h in out["hits"]]
    assert codes == ["002195"]
    added = lib.add_screen_hit(saved["id"], {"symbol": "600519", "name": "贵州茅台"})
    codes = [h["symbol"] for h in added["hits"]]
    assert codes == ["600519", "002195"]
    again = lib.add_screen_hit(saved["id"], {"symbol": "600519", "name": "贵州茅台"})
    assert [h["symbol"] for h in again["hits"]] == ["600519", "002195"]
    empty = lib.save_screen({"name": "空名单", "mode": "static", "universe": "demo", "conditions": [], "hits": []})
    assert empty["hits"] == []


def test_auction_gap_and_close_session():
    from qt.auction import classify_close_move, classify_gap, session_from_minutes

    assert classify_gap(2.4) == "大幅高开"
    assert classify_gap(0.1) == "平开"
    assert classify_close_move(-0.8) == "尾盘回落"
    idx = pd.to_datetime(
        ["2026-09-22 09:24", "2026-09-22 09:25", "2026-09-22 09:30", "2026-09-22 14:56", "2026-09-22 14:57", "2026-09-22 15:00"]
    )
    df = pd.DataFrame(
        {
            "open": [10.0, 10.1, 10.2, 10.3, 10.3, 10.4],
            "close": [10.0, 10.2, 10.2, 10.3, 10.35, 10.5],
            "high": [10.0, 10.2, 10.2, 10.3, 10.35, 10.5],
            "low": [10.0, 10.0, 10.2, 10.3, 10.3, 10.4],
            "volume": [100, 200, 300, 80, 50, 400],
            "amount": [1000, 2000, 3000, 800, 500, 4000],
        },
        index=idx,
    )
    rec = session_from_minutes(df, pre_close=10.0)
    assert rec["open_price"] == 10.2
    assert rec["open_gap_pct"] == 2.0
    assert rec["open_bias"] == "大幅高开"
    assert rec["close_price"] == 10.5
    assert rec["close_bias"] == "尾盘拉升"
    assert len(rec["open_path"]) == 2
    assert len(rec["close_path"]) == 2


def test_auction_tencent_minute_parse():
    from qt.auction import parse_tencent_m1

    df = parse_tencent_m1(
        [
            ["202609221456", "6.22", "6.20", "6.22", "6.20", "100", {}, "0.1"],
            ["202609221457", "6.20", "6.21", "6.21", "6.20", "200", {}, "0.2"],
            ["202609221500", "6.21", "6.25", "6.25", "6.21", "800", {}, "0.8"],
        ]
    )
    assert list(df.index.strftime("%H:%M")) == ["14:56", "14:57", "15:00"]
    assert float(df["close"].iloc[-1]) == 6.25


def test_auction_sina_minute_parse():
    from qt.auction import parse_sina_minutes

    raw = 'x([{"day":"2026-09-22 14:57:00","open":"6.21","high":"6.22","low":"6.21","close":"6.22","volume":"231400","amount":"1437494"}])'
    df = parse_sina_minutes(raw)
    assert list(df.index.strftime("%H:%M")) == ["14:57"]
    assert float(df["amount"].iloc[0]) == 1437494


def test_volume_ratio_excludes_today():
    from qt.indicators import volume_ratio

    vol = pd.Series([100, 100, 100, 100, 100, 200], dtype=float)
    ratio = volume_ratio(vol, 5)
    assert pd.isna(ratio.iloc[4])
    # 第6日：200 / mean(100×5) = 2
    assert abs(float(ratio.iloc[5]) - 2.0) < 1e-9


def test_turnover_as_percent_normalizes_ratio():
    from qt.data import _turnover_as_percent

    ratio = pd.Series([0.003, 0.005, 0.008, 0.004])
    pct = _turnover_as_percent(ratio)
    assert abs(float(pct.iloc[1]) - 0.5) < 1e-9
    already = pd.Series([0.3, 0.5, 1.2, 0.8])
    same = _turnover_as_percent(already)
    assert abs(float(same.iloc[2]) - 1.2) < 1e-9
    # 已规范化后再跑不应翻倍
    again = _turnover_as_percent(pct)
    assert abs(float(again.iloc[1]) - 0.5) < 1e-9


def test_blend_window_scores_weights_and_fallback():
    from qt.similarity import blend_window_scores

    price = np.array([1.0, 0.5, np.nan])
    volume = np.array([0.0, 1.0, 0.5])
    turnover = np.array([1.0, 0.0, 0.5])
    blended = blend_window_scores(price, volume, turnover)
    # 0.65*1 + 0.25*0 + 0.10*1 = 0.75
    assert abs(blended[0] - 0.75) < 1e-9
    # 0.65*0.5 + 0.25*1 + 0.10*0 = 0.575
    assert abs(blended[1] - 0.575) < 1e-9
    assert np.isnan(blended[2])
    price_only = blend_window_scores(price, None, None)
    assert abs(price_only[0] - 1.0) < 1e-9
    assert abs(price_only[1] - 0.5) < 1e-9


def test_best_window_returns_flow_corrs():
    from qt.similarity import best_window

    idx = pd.bdate_range("2024-01-02", periods=40)
    close = pd.Series(np.linspace(10, 14, 40) + np.sin(np.linspace(0, 3, 40)), index=idx)
    volume = pd.Series(np.linspace(1e6, 2e6, 40) + 1e5 * np.sin(np.linspace(0, 4, 40)), index=idx)
    turnover = pd.Series(np.linspace(1, 3, 40) + 0.2 * np.cos(np.linspace(0, 2, 40)), index=idx)
    df = pd.DataFrame({"close": close, "volume": volume, "turnover": turnover})
    query = df.iloc[5:25]
    hit = best_window(query, df, lookback_days=0)
    assert hit is not None
    assert "corr" in hit and "corr_price" in hit
    assert hit["corr_price"] is not None
    assert hit["corr_volume"] is not None
    assert hit["corr_turnover"] is not None
    # Without turnover column, volume weight still applies and turnover is None
    hit2 = best_window(query[["close", "volume"]], df[["close", "volume"]])
    assert hit2 is not None
    assert hit2["corr_turnover"] is None
    assert hit2["corr_volume"] is not None


def test_frame_from_saved_restores_flow():
    from qt.similarity import frame_from_saved

    item = {
        "query_dates": [f"2024-01-{i:02d}" for i in range(2, 12)],
        "query_close": list(range(10, 20)),
        "query_volume": list(range(100, 110)),
        "query_turnover": [1.1 + i * 0.1 for i in range(10)],
        "symbol": "000001",
        "start": "2024-01-02",
        "end": "2024-01-11",
    }
    frame = frame_from_saved(item)
    assert list(frame.columns) == ["close", "volume", "turnover"]
    assert len(frame) == 10
    assert float(frame["volume"].iloc[0]) == 100


def test_bottom_pattern_detectors():
    from qt.indicators import enrich
    from qt.selection import is_bull_pullback, is_first_limit_up, is_volume_breakout

    def frame(close, vol=None):
        n = len(close)
        idx = pd.bdate_range("2024-01-02", periods=n)
        c = pd.Series(close, index=idx, dtype=float)
        v = pd.Series(vol if vol is not None else [1e6] * n, index=idx, dtype=float)
        return pd.DataFrame(
            {
                "open": c.shift(1).fillna(c.iloc[0]),
                "high": c * 1.02,
                "low": c * 0.98,
                "close": c,
                "volume": v,
                "turnover": 1.0,
            },
            index=idx,
        )

    # 底部首板：先阴跌后一根大涨
    c = list(np.linspace(20, 10, 70)) + [10.6, 11.9]
    assert is_first_limit_up(enrich(frame(c)))

    # 大阳线后缩量回踩到均线
    c = [10] * 40 + [10.0, 11.0, 10.6, 10.3, 10.15]
    v = [1e6] * 40 + [1e6, 3e6, 1.2e6, 0.9e6, 0.8e6]
    assert is_bull_pullback(enrich(frame(c, v)))

    # 底部历史低量后突然放量
    c = [20 - (i / 129) * 12 for i in range(130)] + [8.0, 8.2, 8.4]
    v = [0.5e6] * 130 + [3e6, 2.5e6, 2.2e6]
    assert is_volume_breakout(enrich(frame(c, v)))


def test_screener_new_fields_registered():
    from qt.screener import ENUM_FIELDS, SCREEN_FIELDS

    ids = {f["id"] for f in SCREEN_FIELDS}
    for nf in (
        "first_limit_up",
        "bull_pullback",
        "vol_breakout",
        "dist_sma20",
        "roe",
        "net_profit_yoy",
        "revenue_yoy",
        "gross_margin",
    ):
        assert nf in ids
    assert all(f in ENUM_FIELDS for f in ("first_limit_up", "bull_pullback", "vol_breakout"))

