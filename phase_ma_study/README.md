# 涨跌阶段 · MA 综合分析

独立目录，不改动原 Web / 小程序。对 `data_cache/bars` 中缓存股票：

1. 计算 **MA5 / MA10 / MA20 / MA30**
2. 按时序切分 **上升 / 下降** 阶段
3. **横向**：单股多阶段拟合（天数↔收益、斜率↔收益等）
4. **纵向**：跨股同阶段分布与通用公式
5. 每个阶段导出 **K 线 + 四条均线 + 拟合曲线** 到 `stocks/{代码}/`
6. 汇总 **dashboard.html** 大屏浏览

## 运行

在 `quant_trade` 目录下：

```powershell
# 先小样本试跑（推荐）
.\.venv\Scripts\python.exe -m phase_ma_study.run --universe demo

# 主板低价池
.\.venv\Scripts\python.exe -m phase_ma_study.run --universe low20

# 全部缓存（很慢、图很多，建议加 limit 或提高出图门槛）
.\.venv\Scripts\python.exe -m phase_ma_study.run --limit 100
.\.venv\Scripts\python.exe -m phase_ma_study.run --min-pct-chart 8

# 只统计不出图
.\.venv\Scripts\python.exe -m phase_ma_study.run --universe low20 --no-charts
```

## 输出结构

```
phase_ma_study/output/
  dashboard.html          # 大屏（浏览器打开）
  dashboard_index.json
  reports/
    vertical.json         # 跨股纵向结论 + 公式
    all_phases.csv        # 全阶段明细表
    formulas.md           # 可读摘要
  stocks/
    000001/
      phases.json
      horizontal.json     # 该股横向分析
      rise_001_....png
      fall_001_....png
    ...
```

## 阶段判定（简要）

- 日状态：收盘与 MA20、MA5 相对位置 → 升 / 降 / 震荡  
- 同向片段合并（允许短暂震荡）  
- 过短片段丢弃（默认 ≥10 交易日）  
- 阶段内对 `ln(收盘)` 做一次 / 二次时间拟合  

## 升跌共性 / 指标相关 / 买卖点

对全部阶段补齐 RSI、MACD、布林、KDJ、ADX、量比、量额放大、换手、板块等，做升 vs 降区分度与段内相关：

```powershell
.\.venv\Scripts\python.exe -m phase_ma_study.correlate
```

打开：`phase_ma_study\output\correlation.html`  
明细：`output\reports\correlation_report.json`、`phase_features.csv`  
**完整文字手册（含买卖点含义说明、Canvas 打开方式、选股/买卖 Prompt）：**  
`output\reports\买卖点与选股Prompt手册.md`

说明：日线缓存无「主力资金」字段，报告用量额放大与换手作代理。

## 直接双击打开（推荐）

任务跑完后生成**静态内嵌目录**的 `dashboard.html`，可直接双击，无需服务器：

```powershell
.\.venv\Scripts\python.exe -m phase_ma_study.build_static
```

然后打开：`phase_ma_study\output\dashboard.html`

## 便携包（换电脑）

图片约 9GB，不能塞进单个 exe。做法是「exe + 数据同文件夹」：

```powershell
.\.venv\Scripts\python.exe -m phase_ma_study.pack_portable
```

会在 `output\` 下生成：
- `PhaseMAWeb.exe`：本地网页服务（推荐）。双击后浏览器打开大屏 / 相关分析
- `PhaseMAGallery.exe`：直接打开 `dashboard.html`

把整个 `output` 文件夹拷到别的电脑即可。仅打 exe、不重建 HTML：

```powershell
.\.venv\Scripts\python.exe -m phase_ma_study.pack_portable --skip-static
```

## 动态扫描（可选，分析进行中时用）

```powershell
.\.venv\Scripts\python.exe -m phase_ma_study.viewer
```

浏览器打开 http://127.0.0.1:8770/
