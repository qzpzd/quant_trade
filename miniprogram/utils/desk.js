/** 与 Web 端 filteredStocks / 分组逻辑对齐 */

function isWatched(symbol, watchSet) {
  return !!(watchSet && watchSet.has(symbol));
}

function filteredStocks(stocks, filter, watchSet) {
  const cat = (filter && filter.cat) || "all";
  const query = String((filter && filter.q) || "")
    .trim()
    .toLowerCase();
  return (stocks || []).filter((s) => {
    if (query) {
      const hay = `${s.symbol} ${s.name || ""} ${s.industry || ""} ${(s.concepts || []).join(" ")}`.toLowerCase();
      if (!hay.includes(query) && !String(s.symbol).startsWith(query)) return false;
    }
    if (!cat || cat === "all") return true;
    if (cat === "limit_up") return !!s.limit_up;
    if (cat.startsWith("ind:")) return (s.industry || "未分类") === cat.slice(4);
    if (cat.startsWith("con:")) return (s.concepts || []).includes(cat.slice(4));
    if (cat === "watch") return isWatched(s.symbol, watchSet);
    if (cat === "buy") return s.alert === "buy" || s.stance_id === "buy";
    if (cat === "sell") return s.alert === "sell" || s.stance_id === "sell";
    if (cat === "bull") return s.stance === "偏多";
    if (cat === "bear") return s.stance === "偏空";
    if (cat === "hold") return s.stance === "观望";
    if (cat === "oversold") return s.rsi_zone === "超卖";
    if (cat === "overbought") return s.rsi_zone === "超买";
    if (cat === "up") return s.pct_chg > 0;
    if (cat === "down") return s.pct_chg < 0;
    if (cat === "sh") return s.board === "沪市主板";
    if (cat === "sz") return s.board === "深市主板";
    if (cat === "sme") return s.board === "中小板";
    if (cat === "p5") return s.band === "5元以下";
    if (cat === "p10") return s.band === "5–10元";
    if (cat === "p15") return s.band === "10–15元";
    if (cat === "p20") return s.band === "15–20元";
    return true;
  });
}

function buildFilterCats(mode, summary) {
  const sum = summary || {};
  if (mode === "industry") {
    const inds = Object.entries(sum.industries || {});
    return [
      { id: "all", label: "全部行业" },
      { id: "limit_up", label: `涨停 ${sum.limit_up || 0}` },
      ...inds.map(([k, n]) => ({ id: `ind:${k}`, label: `${k} ${n}` })),
    ];
  }
  if (mode === "concept") {
    const cons = Object.entries(sum.concepts || {});
    return [
      { id: "all", label: "全部概念" },
      { id: "limit_up", label: `涨停 ${sum.limit_up || 0}` },
      ...cons.map(([k, n]) => ({ id: `con:${k}`, label: `${k} ${n}` })),
    ];
  }
  return [
    { id: "all", label: "全部" },
    { id: "limit_up", label: `涨停 ${sum.limit_up || 0}` },
    { id: "watch", label: "自选" },
    { id: "buy", label: "偏多提醒" },
    { id: "sell", label: "偏空提醒" },
    { id: "bull", label: "偏多" },
    { id: "hold", label: "观望" },
    { id: "bear", label: "偏空" },
    { id: "oversold", label: "超卖" },
    { id: "overbought", label: "超买" },
    { id: "up", label: "上涨" },
    { id: "down", label: "下跌" },
    { id: "sh", label: "沪市主板" },
    { id: "sz", label: "深市主板" },
    { id: "sme", label: "中小板" },
    { id: "p5", label: "5元以下" },
    { id: "p10", label: "5–10元" },
    { id: "p15", label: "10–15元" },
    { id: "p20", label: "15–20元" },
  ];
}

function groupKeyForStock(s, mode) {
  if (mode === "concept") {
    const cons = s.concepts || [];
    return cons.length ? cons : ["未标注概念"];
  }
  return [s.industry || "未分类"];
}

/** 行业/概念：下拉单组显示，避免多行业整页重复 */
function buildGroups(rows, mode) {
  const map = new Map();
  (rows || []).forEach((s) => {
    groupKeyForStock(s, mode).forEach((g) => {
      if (!map.has(g)) map.set(g, []);
      map.get(g).push(s);
    });
  });
  return [...map.entries()]
    .sort((a, b) => b[1].length - a[1].length || String(a[0]).localeCompare(String(b[0]), "zh"))
    .map(([name, items]) => ({ name, count: items.length, items }));
}

function enrichCard(s, pct, chgClass) {
  const tags = [];
  if (s.limit_up) tags.push({ t: "涨停", cls: "limit" });
  if (s.industry && s.industry !== "未分类") tags.push({ t: s.industry, cls: "" });
  (s.concepts || []).slice(0, 1).forEach((c) => tags.push({ t: c, cls: "" }));
  if (s.stance) {
    tags.push({
      t: s.stance,
      cls: s.stance === "偏多" ? "buy" : s.stance === "偏空" ? "sell" : "",
    });
  }
  if (s.alert === "buy") tags.push({ t: "偏多提醒", cls: "buy" });
  if (s.alert === "sell") tags.push({ t: "偏空提醒", cls: "sell" });
  return {
    ...s,
    pctText: pct(s.pct_chg),
    pctClass: chgClass(s.pct_chg),
    tags,
  };
}

module.exports = {
  isWatched,
  filteredStocks,
  buildFilterCats,
  groupKeyForStock,
  buildGroups,
  enrichCard,
};
