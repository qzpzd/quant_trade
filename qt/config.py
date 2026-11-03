from pathlib import Path

from qt.paths import app_root

ROOT = app_root()
CACHE_DIR = ROOT / "data_cache"
BARS_DIR = CACHE_DIR / "bars"
CACHE_DIR.mkdir(exist_ok=True)
BARS_DIR.mkdir(exist_ok=True)
AUCTION_DIR = CACHE_DIR / "auction"
AUCTION_DIR.mkdir(exist_ok=True)

DEFAULT_START = "20180101"
LOW_PRICE_MAX = 20.0
MAIN_BOARD_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")
INDEX_UNIVERSES = {
    "hs300": ("000300", "沪深300"),
    "zz500": ("000905", "中证500"),
    "sz50": ("000016", "上证50"),
}

FALLBACK_UNIVERSE = [
    ("000001", "平安银行"),
    ("000002", "万科A"),
    ("000333", "美的集团"),
    ("000651", "格力电器"),
    ("000725", "京东方A"),
    ("000858", "五粮液"),
    ("002027", "分众传媒"),
    ("002129", "中环股份"),
    ("002195", "二三四五"),
    ("002230", "科大讯飞"),
    ("002415", "海康威视"),
    ("002475", "立讯精密"),
    ("002594", "比亚迪"),
    ("300059", "东方财富"),
    ("300750", "宁德时代"),
    ("600000", "浦发银行"),
    ("600036", "招商银行"),
    ("600276", "恒瑞医药"),
    ("600519", "贵州茅台"),
    ("600887", "伊利股份"),
    ("601012", "隆基绿能"),
    ("601318", "中国平安"),
    ("601888", "中国中免"),
    ("603259", "药明康德"),
]

# A-share convention: commission both sides, stamp duty on sells.
DEFAULT_COMMISSION = 0.00025
DEFAULT_STAMP = 0.001
DEFAULT_MIN_COMM = 5.0
DEFAULT_LOT = 100
DEFAULT_CASH = 100_000.0
