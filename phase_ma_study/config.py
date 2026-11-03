"""涨跌阶段 + MA5/10/20/30 综合分析（独立于 Web/小程序）。"""

from __future__ import annotations

from pathlib import Path

# 本包根目录：quant_trade/phase_ma_study
PACKAGE_DIR = Path(__file__).resolve().parent
# 默认输出：quant_trade/phase_ma_study/output
DEFAULT_OUTPUT = PACKAGE_DIR / "output"

# 均线周期
MA_PERIODS = (5, 10, 20, 30)

# 阶段最短交易日数
MIN_PHASE_DAYS = 10
# 阶段最小涨跌幅（绝对值，%）——低于此不单独出图，但仍计入统计
MIN_PHASE_PCT_FOR_CHART = 5.0
# 合并碎片阶段：相邻同向间隔不超过 N 日则合并
MERGE_GAP_DAYS = 3

# 拟合多项式最高阶
POLY_DEGREE = 2
