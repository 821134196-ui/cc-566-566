/* 城市道路积雪撒盐与路段复核系统 —— Vue 3 单文件应用（无构建） */
const { createApp } = Vue;

const STATUS_LABEL = {
  untreated: "未清理", salted: "已撒盐", in_review: "待复核", open: "已开放",
};
const VEH_STATUS_LABEL = { idle: "待命", working: "作业中", broken: "故障" };
const ENTITY_LABEL = {
  segment: "路段状态", dispatch: "派车单", work_record: "作业回传",
  review: "复核结论", breakdown: "车辆故障",
};
const ROLE_LABEL = {
  dispatcher: "调度员", operator: "作业人员", reviewer: "复核员", manager: "管理人员",
};
const DISPATCH_STATUS_LABEL = {
  active: "作业中", completed: "已完成/待复核", interrupted: "故障中断", cancelled: "已取消",
};
const ACTION_LABEL = {
  dispatch_created: "创建派车",
  created: "派车单建立",
  uploaded: "作业回传",
  duplicate_upload_ignored: "重复回传被忽略（未计盐量）",
  status_change: "路段状态变化",
  submit_review: "申请复核",
  completed: "撒盐完成",
  interrupted: "作业中断",
  resume: "恢复作业",
  reported: "登记车辆故障",
  resolved: "故障处理完成",
  review_passed: "复核通过 · 路段开放",
  review_rejected: "复核驳回 · 退回补盐",
};

createApp({
  data() {
    return {
      token: localStorage.getItem("snow_token") || "",
      user: JSON.parse(localStorage.getItem("snow_user") || "null"),
      // 地图数据
      segments: [],
      vehicles: [],
      positions: [],
      generatedAt: "",
      selectedId: null,
      detail: null,
      timeline: [],
      activeTab: "segments",
      filterStatus: "all",
      now: "",
      // 表单
      dispatchForm: { segment_id: null, vehicle_id: null, salt_planned_kg: 800, note: "" },
      workForms: {},                 // 按派车单 id 保存表单草稿
      lastSubmit: {},                // 上次成功回传负载（用于演示“重复回传”）
      breakdownForms: {},            // 故障表单
      resolving: {},                 // 故障解除输入
      reviewForms: {},               // 按路段保存复核表单
      showBreakdownFor: {},
      dispatches: [],
      // UI
      flash: { type: "", text: "" },
      photoPreview: null,
      loading: false,
      timer: null,
      loginPassword: "123456",
      loginError: "",
      quickUser: "",
    };
  },

  computed: {
    perms() { return this.user?.perms || {}; },
    isLogin() { return !!this.user; },

    visibleTabs() {
      const tabs = [{ key: "segments", icon: "🗺️", label: "路段进度" }];
      if (this.perms.can_dispatch) tabs.push({ key: "dispatch", icon: "🚚", label: "派车调度" });
      if (this.perms.can_work) tabs.push({ key: "work", icon: "🧂", label: "车辆作业" });
      if (this.perms.can_review) tabs.push({ key: "review", icon: "✅", label: "路段复核" });
      return tabs;
    },

    stats() {
      const c = { untreated: 0, salted: 0, in_review: 0, open: 0 };
      this.segments.forEach(s => { c[s.status] = (c[s.status] || 0) + 1; });
      c.total = this.segments.length;
      c.openPct = c.total ? Math.round(c.open / c.total * 100) : 0;
      c.saltTotal = this.segments.reduce((a, s) => a + s.salt_total_kg, 0);
      return c;
    },

    filteredSegments() {
      const list = this.segments.slice().sort((a, b) => {
        const order = { in_review: 0, salted: 1, untreated: 2, open: 3 };
        if (order[a.status] !== order[b.status]) return order[a.status] - order[b.status];
        return a.road_level - b.road_level || a.id - b.id;
      });
      if (this.filterStatus === "all") return list;
      return list.filter(s => s.status === this.filterStatus);
    },

    inReviewSegments() {
      return this.segments.filter(s => s.status === "in_review");
    },

    // 当前登录作业员负责的车辆的派车单
    myDispatches() {
      const myVehicleIds = new Set(
        this.vehicles.filter(v => v.operator_id === this.user?.id).map(v => v.id)
      );
      return this.dispatches.filter(d =>
        myVehicleIds.has(d.vehicle_id) &&
        (d.status === "active" || d.status === "interrupted"));
    },

    reviewSegments() {
      return this.inReviewSegments;
    },
  },

  methods: {
    statusLabel(s) { return STATUS_LABEL[s] || s; },
    vehStatusLabel(s) { return VEH_STATUS_LABEL[s] || s; },
    entityLabel(t) { return ENTITY_LABEL[t] || t; },
    roleLabel(r) { return ROLE_LABEL[r] || r; },
    dStatusLabel(s) { return DISPATCH_STATUS_LABEL[s] || s; },
    actionLabel(a) { return ACTION_LABEL[a] || a; },
    labelPos(s) {
      // 取折线中点作为路名标签位置，并做轻微偏移避免压住线条
      const g = s.geometry;
      const mid = g[Math.floor(g.length / 2)];
      return { x: mid[0] * 100, y: mid[1] * 100 - 3.2 };
    },
    segById(id) { return this.segments.find(s => s.id === id); },
    vehById(id) { return this.vehicles.find(v => v.id === id); },
    posOf(vehicleId) { return this.positions.find(p => p.vehicle_id === vehicleId); },
    fmtTime(t) {
      if (!t) return "—";
      const d = new Date(t);
      return d.toLocaleString("zh-CN", { hour12: false });
    },
    fmtNum(n) { return Number(n || 0).toLocaleString("zh-CN", { maximumFractionDigits: 1 }); },

    segPoints(s) { return s.geometry.map(p => p.map(v => v * 100).join(",")).join(" "); },

    vehTransform(p) { return `translate(${p.x * 100},${p.y * 100})`; },

    // ---------- API ----------
    async api(path, options = {}) {
      const headers = Object.assign({}, options.headers || {});
      if (this.token) headers["Authorization"] = "Bearer " + this.token;
      if (options.json !== undefined) {
        headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(options.json);
        delete options.json;
      }
      const resp = await fetch(path, Object.assign({ headers }, options));
      if (resp.status === 401) {
        this.doLogout();
        throw new Error("登录已失效");
      }
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || `请求失败（${resp.status}）`);
      }
      return data;
    },

    setFlash(type, text) {
      this.flash = { type, text };
      if (type === "ok") setTimeout(() => { this.flash = { type: "", text: "" }; }, 3500);
    },

    // ---------- 登录 ----------
    async doLogin(username) {
      const password = this.loginPassword || "123456";
      try {
        const data = await this.api("/api/auth/login", {
          method: "POST", json: { username, password },
        });
        this.token = data.token;
        this.user = data.user;
        localStorage.setItem("snow_token", data.token);
        localStorage.setItem("snow_user", JSON.stringify(data.user));
        this.loginPassword = "";
        this.activeTab = "segments";
        await this.refreshAll();
        this.startPolling();
      } catch (e) {
        this.loginError = e.message;
      }
    },

    doLogout() {
      this.token = ""; this.user = null;
      localStorage.removeItem("snow_token");
      localStorage.removeItem("snow_user");
      if (this.timer) { clearInterval(this.timer); this.timer = null; }
    },

    async restoreSession() {
      if (!this.token) return;
      try {
        this.user = await this.api("/api/auth/me");
        // 以服务端返回为准（含最新角色/权限），同时回写本地缓存
        localStorage.setItem("snow_user", JSON.stringify(this.user));
        await this.refreshAll();
        this.startPolling();
      } catch (e) {
        this.doLogout();
      }
    },

    startPolling() {
      if (this.timer) clearInterval(this.timer);
      this.timer = setInterval(() => this.loadMap(true), 5000);
    },

    // ---------- 数据加载 ----------
    async refreshAll() {
      await Promise.all([this.loadMap(), this.loadDispatches()]);
      if (this.selectedId) await this.selectSegment(this.selectedId, true);
    },

    async loadMap(silent = false) {
      try {
        const data = await this.api("/api/map");
        this.segments = data.segments;
        this.vehicles = data.vehicles;
        this.positions = data.positions;
        this.generatedAt = data.generated_at;
        this.now = this.fmtTime(new Date().toISOString());
      } catch (e) {
        if (!silent) this.setFlash("error", "地图加载失败：" + e.message);
      }
    },

    async loadDispatches() {
      try {
        this.dispatches = await this.api("/api/dispatches");
      } catch (e) { /* 忽略轮询异常 */ }
    },

    async selectSegment(id, silent = false) {
      this.selectedId = id;
      this.loading = true;
      try {
        const [detail, timeline] = await Promise.all([
          this.api(`/api/segments/${id}/detail`),
          this.api(`/api/segments/${id}/timeline`),
        ]);
        this.detail = detail;
        this.timeline = timeline;
        if (!this.reviewForms[id]) {
          this.reviewForms[id] = { snow_cleared: true, surface_safe: true, note: "" };
        }
      } catch (e) {
        if (!silent) this.setFlash("error", e.message);
      } finally {
        this.loading = false;
      }
    },

    closeDetail() {
      this.selectedId = null; this.detail = null; this.timeline = [];
    },

    switchTab(key) {
      this.activeTab = key;
      this.setFlash("", "");
      if (key === "dispatch" && this.dispatchForm.segment_id == null) {
        const first = this.segments.find(s =>
          ["untreated", "salted"].includes(s.status));
        if (first) this.dispatchForm.segment_id = first.id;
      }
    },

    // ---------- 派车 ----------
    eligibleVehicles(segmentId) {
      const seg = this.segById(segmentId);
      if (!seg) return [];
      return this.vehicles.filter(v => v.min_level <= seg.road_level && v.status !== "broken");
    },

    onDispatchSegmentChange() {
      const list = this.eligibleVehicles(this.dispatchForm.segment_id);
      const idle = list.find(v => v.status === "idle") || list[0];
      this.dispatchForm.vehicle_id = idle ? idle.id : null;
    },

    async submitDispatch() {
      const f = this.dispatchForm;
      if (!f.segment_id || !f.vehicle_id) {
        this.setFlash("error", "请选择路段与车辆"); return;
      }
      try {
        const d = await this.api("/api/dispatches", { method: "POST", json: f });
        this.setFlash("ok", `派车成功：派车单 #${d.id}，车辆 ${d.vehicle_plate}`);
        this.dispatchForm.note = "";
        await this.refreshAll();
      } catch (e) { this.setFlash("error", e.message); }
    },

    // ---------- 作业 ----------
    workForm(dispatchId) {
      if (!this.workForms[dispatchId]) {
        this.workForms[dispatchId] = { salt_kg: 300, pos_x: "", pos_y: "", photo: null, photoName: "" };
      }
      return this.workForms[dispatchId];
    },

    useGpsPosition(dispatchId) {
      const d = this.dispatches.find(x => x.id === dispatchId);
      const p = d ? this.posOf(d.vehicle_id) : null;
      const f = this.workForm(dispatchId);
      if (p) {
        f.pos_x = p.x.toFixed(3);
        f.pos_y = p.y.toFixed(3);
        this.setFlash("ok", `已取车辆模拟定位 (${f.pos_x}, ${f.pos_y})`);
      } else {
        this.setFlash("error", "暂无车辆位置");
      }
    },

    onPhotoPicked(ev, dispatchId) {
      const file = ev.target.files[0];
      this.workForm(dispatchId).photo = file || null;
      this.workForm(dispatchId).photoName = file ? file.name : "";
    },

    _buildPayload(dispatchId, { keepToken } = {}) {
      const f = this.workForms[dispatchId];
      const prev = this.lastSubmit[dispatchId];
      if (keepToken && prev) return JSON.parse(JSON.stringify(prev));
      const px = parseFloat(f.pos_x), py = parseFloat(f.pos_y);
      return {
        dispatch_id: dispatchId,
        salt_kg: parseFloat(f.salt_kg) || 0,
        pos_x: isNaN(px) ? 0.5 : px,
        pos_y: isNaN(py) ? 0.5 : py,
        client_token: "web-" + Date.now() + "-" + Math.random().toString(16).slice(2, 8),
      };
    },

    async uploadWork(dispatchId, { duplicate = false } = {}) {
      const f = this.workForm(dispatchId);
      // “模拟重复回传”时原样重放上一次的负载（含同一 client_token / 定位 / 用量）
      const payload = (duplicate && this.lastSubmit[dispatchId])
        ? JSON.parse(JSON.stringify(this.lastSubmit[dispatchId]))
        : this._buildPayload(dispatchId);
      try {
        let data;
        if (f.photo && !(duplicate && this.lastSubmit[dispatchId])) {
          const fd = new FormData();
          Object.entries(payload).forEach(([k, v]) => fd.append(k, v));
          fd.append("photo", f.photo);
          data = await this.api("/api/work-records/photo", { method: "POST", body: fd });
        } else {
          data = await this.api("/api/work-records", { method: "POST", json: payload });
        }
        this.lastSubmit[dispatchId] = payload;
        if (data.duplicate) {
          this.setFlash("ok", `⚠ 系统判定为重复回传（记录 #${data.id}），融雪剂未重复计量`);
        } else {
          this.setFlash("ok", `作业已回传（记录 #${data.id}），本次 ${data.salt_kg}kg${data.photo_url ? "，含现场照片" : ""}`);
          f.photo = null; f.photoName = "";
        }
        await this.refreshAll();
        if (this.selectedId) await this.selectSegment(this.selectedId, true);
      } catch (e) { this.setFlash("error", e.message); }
    },

    async completeDispatch(dispatchId) {
      try {
        await this.api("/api/dispatches/complete", {
          method: "POST", json: { dispatch_id: dispatchId },
        });
        this.setFlash("ok", "撒盐完成，路段已进入待复核状态");
        await this.refreshAll();
      } catch (e) { this.setFlash("error", e.message); }
    },

    bdForm(dispatchId) {
      if (!this.breakdownForms[dispatchId])
        this.breakdownForms[dispatchId] = { reason: "", follow_up: "" };
      return this.breakdownForms[dispatchId];
    },

    async reportBreakdown(dispatchId) {
      const f = this.bdForm(dispatchId);
      if (!f.reason || !f.follow_up) { this.setFlash("error", "请填写故障情况与后续安排"); return; }
      try {
        const b = await this.api("/api/breakdowns", { method: "POST", json: { dispatch_id: dispatchId, ...f } });
        this.setFlash("ok", `故障已登记（#${b.id}），派车单中断、车辆标记故障`);
        f.reason = ""; f.follow_up = "";
        this.showBreakdownFor[dispatchId] = false;
        await this.refreshAll();
      } catch (e) { this.setFlash("error", e.message); }
    },

    async resolveBreakdown(dispatchId, breakdownId) {
      const result = this.resolving[breakdownId] || "";
      if (!result) { this.setFlash("error", "请填写后续处理结果"); return; }
      try {
        await this.api(`/api/breakdowns/${breakdownId}/resolve`, {
          method: "POST", json: { follow_up_result: result },
        });
        this.setFlash("ok", "故障解除，车辆恢复作业");
        this.resolving[breakdownId] = "";
        await this.refreshAll();
      } catch (e) { this.setFlash("error", e.message); }
    },

    // ---------- 复核 ----------
    reviewForm(segmentId) {
      if (!this.reviewForms[segmentId])
        this.reviewForms[segmentId] = { snow_cleared: true, surface_safe: true, note: "" };
      return this.reviewForms[segmentId];
    },

    async submitReview(segmentId) {
      const f = this.reviewForm(segmentId);
      try {
        const r = await this.api("/api/reviews", { method: "POST", json: { segment_id: segmentId, ...f } });
        this.setFlash("ok", r.passed ? "复核通过，路段已开放通行 ✅" : "已驳回，路段退回补盐");
        f.note = "";
        await this.refreshAll();
      } catch (e) { this.setFlash("error", e.message); }
    },

    // 我是否在该路段作业过（前端提示，真正的强制在后端）
    workedByMe(segmentId) {
      const d = this.detail && this.detail.id === segmentId ? this.detail : null;
      if (!d) return false;
      return d.dispatches.some(dp => dp.records.some(r => r.operator_name === this.user?.name));
    },

    photoUrl(url) { return url ? `${url}?token=${encodeURIComponent(this.token)}` : ""; },

    tlClass(t) { return "tl-item t-" + t; },
    tlTransition(e) {
      if (e.from_status && e.to_status)
        return `${this.statusLabel(e.from_status)} → ${this.statusLabel(e.to_status)}`;
      return "";
    },
  },

  mounted() {
    this.restoreSession();
  },
}).mount("#app");
