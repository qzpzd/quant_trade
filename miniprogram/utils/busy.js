/** 对齐 Web 端 startBusyPulse：假进度脉冲到 ~92%，结束到 100% */

function createBusy(page) {
  let timer = null;
  let t0 = 0;

  function set( partial) {
    if (page && typeof page.setData === "function") page.setData(partial);
  }

  return {
    start(text) {
      if (timer) clearInterval(timer);
      t0 = Date.now();
      set({
        busyShow: true,
        busyText: text || "正在计算…",
        busyPct: 3,
        busyPctText: "3%",
      });
      timer = setInterval(() => {
        const sec = (Date.now() - t0) / 1000;
        const pct = Math.min(92, 3 + 89 * (1 - Math.exp(-sec / 6)));
        const r = Math.round(pct);
        set({ busyPct: r, busyPctText: `${r}%`, busyText: text || "正在计算…" });
      }, 250);
    },

    /** 真实进度（同步任务轮询） */
    update(text, pct) {
      const has = pct != null && isFinite(Number(pct));
      const r = has ? Math.min(100, Math.max(0, Math.round(Number(pct)))) : null;
      set({
        busyShow: true,
        busyText: text || "正在计算…",
        busyPct: r != null ? r : 0,
        busyPctText: r != null ? `${r}%` : "",
      });
    },

    stop(finalText) {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      if (finalText) {
        set({ busyShow: true, busyText: finalText, busyPct: 100, busyPctText: "100%" });
        setTimeout(() => set({ busyShow: false, busyPctText: "" }), 450);
      } else {
        set({ busyShow: false, busyPctText: "" });
      }
    },

    /** 轮询 /api/universe/sync/status，直到 done/error */
    async pollSync(api, { intervalMs = 600, onTick } = {}) {
      const phaseLabel = (phase) => {
        if (phase === "alerts") return "扫描买卖点";
        if (phase === "dashboard") return "生成大屏";
        if (phase === "sectors") return "更新行业概念";
        return "更新日线";
      };
      this.update("正在启动缓存更新…", 1);
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await new Promise((r) => setTimeout(r, intervalMs));
        let st;
        try {
          st = await api.get("/api/universe/sync/status");
        } catch (e) {
          this.stop("同步状态读取失败");
          throw e;
        }
        if (typeof onTick === "function") onTick(st);
        if (!st || st.status === "done") {
          this.stop("同步完成");
          return st;
        }
        if (st.status === "error") {
          this.stop(st.error || "同步失败");
          throw new Error(st.error || "同步失败");
        }
        if (st.status === "running") {
          const phase = st.phase || "bars";
          let done = Number(st.done) || 0;
          let total = Number(st.total) || 0;
          if (phase === "alerts" || phase === "dashboard" || phase === "sectors") {
            done = Number(st.scan_done) || 0;
            total = Number(st.scan_total) || 0;
          }
          const pct = total > 0 ? (done / total) * 100 : null;
          const text = `${phaseLabel(phase)} ${st.key || ""}  ${done}/${total}  提醒 ${st.alert_buys || 0}/${st.alert_sells || 0}`;
          this.update(text, pct != null ? pct : 8);
        }
      }
    },
  };
}

/** 页面 data 初始字段 */
function busyData() {
  return {
    busyShow: false,
    busyText: "",
    busyPct: 0,
    busyPctText: "",
  };
}

module.exports = { createBusy, busyData };
