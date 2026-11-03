# 形迹 QuantTrade

A 股研究终端：回测、买卖点、走势预测、形态匹配、条件选股。

行情来自 akshare（东方财富），仅供研究，不构成投资建议。

## 启动

```bash
# Windows（推荐用本机 venv）
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8765

# macOS / Linux
python -m pip install -r requirements.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8765
```

## 桌面便携包（Web，不含小程序）

把 Web 终端打成可双击运行的文件夹（内置运行环境 + `web/` + `data_cache/`）。**不含** `miniprogram`。

```powershell
# Windows（在本机执行）
.\.venv\Scripts\python.exe -m pack_desktop
.\.venv\Scripts\python.exe -m pack_desktop --zip
# 产物：dist\QuantTrade-win\  （双击 QuantTrade.exe）
```

```bash
# macOS（必须在 Mac 上执行，无法在 Windows 交叉编译）
chmod +x scripts/pack_mac.sh
./scripts/pack_mac.sh
# 或：python -m pack_desktop --zip
# 产物：dist/QuantTrade-mac/
```

`--no-data` 可跳过复制行情缓存以减小体积。

> 注意：`.venv` 需在当前系统创建。Mac 上建的 venv（`bin/python3`）不能在 Windows 直接运行，应使用 `Scripts\python.exe`。

浏览器打开 http://127.0.0.1:8765

首次打开会拉取当前股票的日线并写入 `data_cache/`。形态匹配和条件选股默认可用「核心样本」（约 24 只活跃股）。要扫沪深300 / 中证500，请先点「同步成分股行情」。

### 准实时行情

盘中（约 9:15–15:05）前端会：

- 按自选 / 当前股票 / 首页可见卡片批量拉**现价**（约 8 秒，东财推送接口，短缓存）
- 顶栏显示「准实时 · 交易中」与刷新时刻
- 竞价页打开时顺带刷新**分钟线**（约 60 秒）

日线 K 线、回测、阶段图仍基于本地缓存；交易日 **16:30** 或点「立即更新缓存」同步到最新日线。这不是券商 Level-2 推送。

相关 API：`/api/live/status`、`/api/live/spot`、`/api/live/quote/{code}`、`/api/live/minutes/{code}`。

原命令行回测仍可用：`python main.py`

## 功能

| 模块 | 做什么 |
|---|---|
| 回测 | 八种策略（趋势/RSI/布林/MACD + SuperTrend/海龟/Dual Thrust/RSI2）+ A股手数/印花税；对比买入持有、夏普、回撤、胜率 |
| 买卖点 | 均线/RSI/MACD/布林/KDJ/SuperTrend/海龟/Dual Thrust/RSI2 触发点 + 当前多空倾向 |
| 走势预测 | 历史相似窗口的后续路径（中位与四分位）再与趋势外推合成 |
| 形态匹配 | 选定一段走势，在样本池里找标准化后最像的窗口 |
| 条件选股 | RSI、金叉、均线排列、量比、PE 等条件组合 |

## 内置选股策略

条件选股页新增了若干「底部反转 / 量价 / 基本面」形态，可在快捷预设一键选用，也可在条件列表里组合：

| 预设 | 条件 | 说明 |
|---|---|---|
| 底部首板涨停/大涨 | `first_limit_up = yes` | 最近一根大涨（≥7%），启动前处于底部、且此前无同级别大涨 |
| 大阳线缩量回踩 | `bull_pullback = yes` | 放量大阳线后连续 2~6 日缩量回踩，收盘贴近 MA10/MA20 |
| 底部放量启动 | `vol_breakout = yes` | 股价历史低位 + 放量前量能安静 + 最近突然放量 |
| 低估值 | `pe>0 且 pe<20 且 pb<2` | 估值偏低（仅用实时 PE/PB） |
| 绩优低估值 | `pe>0 且 pe<20 且 pb<3 且 roe>10 且 净利润同比>0` | 业绩好 + 估值低（ROE/增速来自东财业绩报表缓存） |

基本面字段 `roe`（净资产收益率）、`net_profit_yoy`（净利润同比）、`revenue_yoy`（营收同比）、`gross_margin`（销售毛利率）来自东财业绩报表，按 24 小时缓存于 `data_cache/fundamental.pkl`，首次使用会自动拉取；网络不可用时这些字段缺失，对应条件（如「绩优低估值」）将不命中，属于正常降级。

> 以上阈值都是经验启发式，可按需在代码 `qt/selection.py` 顶部常量里调整。选股结果不构成投资建议。

预测是形态类比，不是对未来价格的保证。高价股（如贵州茅台）在默认 10 万资金下可能买不足 1 手（100 股），回测会没有成交，请加大资金。
