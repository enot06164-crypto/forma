/* FORMA — клиент */
(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const boot = JSON.parse($("#boot").textContent);
  const BASE = boot.base || "";

  const state = {
    file: null, target: null,
    sfile: null, mode: "static", mask: false,
    busy: false,
  };

  /* ---------------------------------------------------------- утилиты */
  const fmtBytes = (n) => {
    n = Number(n) || 0;
    if (n < 1024) return n + " Б";
    if (n < 1024 ** 2) return (n / 1024).toFixed(1).replace(".0", "") + " КБ";
    if (n < 1024 ** 3) return (n / 1024 ** 2).toFixed(1).replace(".0", "") + " МБ";
    return (n / 1024 ** 3).toFixed(2) + " ГБ";
  };

  const fmtDate = (ts) => {
    const d = new Date(ts * 1000);
    return d.toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let toastTimer;
  function toast(msg, err = false) {
    const t = $("#toast");
    t.textContent = msg;
    t.className = "toast show" + (err ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.className = "toast"), 3200);
  }

  async function api(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) {
      let msg = "ошибка " + r.status;
      try { const j = await r.json(); msg = j.detail || msg; } catch (e) {}
      throw new Error(msg);
    }
    return r.json();
  }

  /* ---------------------------------------------------------- навигация */
  $$(".rail-btn").forEach((b) => {
    b.addEventListener("click", () => {
      $$(".rail-btn").forEach((x) => x.classList.toggle("active", x === b));
      $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + b.dataset.view));
      if (b.dataset.view === "library") loadLibrary();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  /* ---------------------------------------------------------- загрузка */
  function wireDrop(dropEl, inputEl, onFile) {
    dropEl.addEventListener("click", () => inputEl.click());
    dropEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputEl.click(); }
    });
    inputEl.addEventListener("change", () => {
      if (inputEl.files && inputEl.files[0]) onFile(inputEl.files[0]);
      inputEl.value = "";
    });
    ["dragenter", "dragover"].forEach((ev) =>
      dropEl.addEventListener(ev, (e) => { e.preventDefault(); dropEl.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) =>
      dropEl.addEventListener(ev, (e) => { e.preventDefault(); dropEl.classList.remove("over"); }));
    dropEl.addEventListener("drop", (e) => {
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) onFile(f);
    });
  }

  async function uploadFile(file) {
    const fd = new FormData();
    fd.append("file", file);
    return api("/api/upload", { method: "POST", body: fd });
  }

  /* ---------------------------------------------------------- конвертер */
  const HINTS = {
    png: "alpha", jpg: "фото", webp: "alpha", avif: "сжатие", gif: "анимация",
    bmp: "без сжатия", tiff: "печать", ico: "favicon", pdf: "документ",
    mp4: "h.264", webm: "vp9", mkv: "контейнер", mov: "quicktime",
    mp3: "192 kbps", wav: "pcm", ogg: "vorbis", opus: "речь", flac: "lossless",
    m4a: "aac", aac: "adts", docx: "word", odt: "open doc", txt: "текст",
    csv: "таблица", html: "веб", rtf: "rich text", xlsx: "excel", ods: "таблица",
    odp: "слайды", pptx: "powerpoint",
  };

  function showFile(f) {
    state.file = f;
    state.target = null;
    $("#drop").hidden = true;
    $("#filecard").hidden = false;
    $("#targets").hidden = false;

    const thumb = $("#fc-thumb");
    if (f.kind === "image" && f.ext !== "svg") {
      thumb.innerHTML = `<img src="${f.preview}" alt="">`;
    } else {
      thumb.innerHTML = `<span>${esc(f.ext)}</span>`;
    }
    $("#fc-name").textContent = f.name;
    const bits = [fmtBytes(f.size), f.kind];
    if (f.meta && f.meta.width) bits.push(`${f.meta.width}×${f.meta.height}`);
    if (f.meta && f.meta.duration) bits.push(f.meta.duration.toFixed(1) + " с");
    if (f.meta && f.meta.vcodec) bits.push(f.meta.vcodec);
    if (f.meta && f.meta.acodec) bits.push(f.meta.acodec);
    $("#fc-meta").innerHTML = bits.map((b) => `<b>${esc(b)}</b>`).join("<span>·</span>");

    $("#targets-kind").textContent = f.targets.length + " форматов доступно";
    const chips = $("#chips");
    chips.innerHTML = "";
    f.targets.forEach((t) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.dataset.target = t;
      b.innerHTML = `${esc(t)}${HINTS[t] ? `<small>${HINTS[t]}</small>` : ""}`;
      b.addEventListener("click", () => selectTarget(t));
      chips.appendChild(b);
    });
    $("#go").disabled = true;
    $("#progress").hidden = true;
    $("#opts").hidden = true;
  }

  function selectTarget(t) {
    state.target = t;
    $$("#chips .chip").forEach((c) => c.classList.toggle("on", c.dataset.target === t));
    $("#go").disabled = false;

    const isImg = state.file && state.file.kind === "image";
    const isPdf = state.file && state.file.ext === "pdf";
    $("#opt-quality").hidden = !(isImg && ["jpg", "jpeg", "webp", "avif"].includes(t));
    $("#opt-dim").hidden = !(isImg && t !== "pdf" && t !== "ico");
    $("#opt-dpi").hidden = !(isPdf && ["png", "jpg"].includes(t));
    $("#opts").hidden = $("#opt-quality").hidden && $("#opt-dim").hidden && $("#opt-dpi").hidden;
  }

  wireDrop($("#drop"), $("#file"), async (file) => {
    try {
      const f = await uploadFile(file);
      showFile(f);
      toast("файл загружен · " + fmtBytes(f.size));
    } catch (e) { toast(e.message, true); }
  });

  $("#fc-reset").addEventListener("click", () => {
    state.file = null; state.target = null;
    $("#drop").hidden = false;
    $("#filecard").hidden = true;
    $("#targets").hidden = true;
    $("#progress").hidden = true;
  });

  $("#quality").addEventListener("input", (e) => ($("#q-val").textContent = e.target.value));

  $("#go").addEventListener("click", async () => {
    if (!state.file || !state.target || state.busy) return;
    state.busy = true;
    $("#go").disabled = true;
    const prog = $("#progress");
    prog.hidden = false;
    prog.classList.remove("error");
    $("#p-label").textContent = "конвертация";
    $("#p-pct").textContent = "0%";
    $("#p-bar").style.width = "0%";
    $("#p-note").textContent = "запуск…";

    const opts = {};
    if (!$("#opt-quality").hidden) opts.quality = Number($("#quality").value);
    if (!$("#opt-dim").hidden) opts.max_dim = Number($("#maxdim").value);
    if (!$("#opt-dpi").hidden) opts.dpi = Number($("#dpi").value);

    try {
      const { job } = await api("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: state.file.id, target: state.target, opts }),
      });
      const res = await poll(job, (j) => {
        $("#p-pct").textContent = Math.round(j.progress) + "%";
        $("#p-bar").style.width = j.progress + "%";
        if (j.note) $("#p-note").textContent = j.note;
      });
      if (res.status === "error") throw new Error(res.error || "ошибка конвертации");
      $("#p-pct").textContent = "100%";
      $("#p-bar").style.width = "100%";
      $("#p-note").textContent = "готово · " + fmtBytes(res.result.size);
      renderResult(res.result);
      refreshStats();
      toast("готово · " + res.result.ext.toUpperCase() + " · " + fmtBytes(res.result.size));
    } catch (e) {
      prog.classList.add("error");
      $("#p-label").textContent = "ошибка";
      $("#p-pct").textContent = "—";
      $("#p-note").textContent = e.message;
      toast(e.message, true);
    } finally {
      state.busy = false;
      $("#go").disabled = false;
    }
  });

  async function poll(jobId, onUpdate) {
    for (;;) {
      const j = await api("/api/job/" + jobId);
      onUpdate(j);
      if (j.status === "done" || j.status === "error") return j;
      await new Promise((r) => setTimeout(r, 420));
    }
  }

  /* ---------------------------------------------------------- стикеры */
  const SPECS = {
    static: [["512×512", 1], ["PNG / WEBP", 0], ["≤ 512 КБ", 0], ["прозрачность", 0]],
    animated: [["512×512", 1], ["VP9 + alpha", 1], ["≤ 64 КБ", 1], ["≤ 3 с", 0], ["30 fps", 0]],
    video: [["512×512", 1], ["VP9", 1], ["≤ 256 КБ", 1], ["≤ 3 с", 0], ["30 fps", 0]],
  };

  function renderSpecs() {
    $("#specs").innerHTML = SPECS[state.mode]
      .map(([t, hot]) => `<span class="spec${hot ? " hot" : ""}">${t}</span>`)
      .join("");
  }

  function showStickerFile(f) {
    state.sfile = f;
    $("#drop2").hidden = true;
    $("#filecard2").hidden = false;
    $("#sticker-form").hidden = false;
    const thumb = $("#fc2-thumb");
    if (f.kind === "image" && f.ext !== "svg") thumb.innerHTML = `<img src="${f.preview}" alt="">`;
    else thumb.innerHTML = `<span>${esc(f.ext)}</span>`;
    $("#fc2-name").textContent = f.name;
    const bits = [fmtBytes(f.size), f.kind];
    if (f.meta && f.meta.width) bits.push(`${f.meta.width}×${f.meta.height}`);
    if (f.meta && f.meta.duration) bits.push(f.meta.duration.toFixed(1) + " с");
    $("#fc2-meta").innerHTML = bits.map((b) => `<b>${esc(b)}</b>`).join("<span>·</span>");
    // видео по умолчанию собираем как анимированный стикер — сразу с редактором
    if (f.kind === "video" && state.mode === "static") {
      state.mode = "animated";
      $$("#mode button").forEach((x) => x.classList.toggle("on", x.dataset.mode === "animated"));
    }
    renderSpecs();
    setupEditor(f);
  }

  wireDrop($("#drop2"), $("#file2"), async (file) => {
    try {
      const f = await uploadFile(file);
      if (!["image", "video"].includes(f.kind)) throw new Error("нужна картинка, GIF или видео");
      showStickerFile(f);
      toast("готово к сборке · " + fmtBytes(f.size));
    } catch (e) { toast(e.message, true); }
  });

  $("#fc2-reset").addEventListener("click", () => {
    state.sfile = null;
    $("#drop2").hidden = false;
    $("#filecard2").hidden = true;
    $("#sticker-form").hidden = true;
    $("#progress2").hidden = true;
    $("#editor").hidden = true;
    ed.ready = false;
    const v = $("#ed-video");
    if (v) { v.pause(); v.removeAttribute("src"); v.load(); }
  });

  $$("#mode button").forEach((b) => {
    b.addEventListener("click", () => {
      state.mode = b.dataset.mode;
      $$("#mode button").forEach((x) => x.classList.toggle("on", x === b));
      renderSpecs();
      $("#editor").hidden = state.mode === "static" || !ed.ready;
    });
  });

  const maskSwitch = $("#mask-switch");
  function toggleMask() {
    state.mask = !state.mask;
    maskSwitch.classList.toggle("on", state.mask);
    maskSwitch.setAttribute("aria-checked", String(state.mask));
    $("#mask-visual").classList.toggle("on", state.mask);
  }
  maskSwitch.addEventListener("click", toggleMask);
  maskSwitch.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleMask(); }
  });

  /* ---------------------------------------------------------- редактор фрагмента */
  const MIN_LEN = 0.3;
  const MAX_LEN = 3.0;
  const ed = { dur: 0, start: 0, end: 0, url: null, ready: false, dragging: null };

  function edSeek(t) {
    const v = $("#ed-video");
    if (!v || !ed.ready) return;
    try { v.currentTime = Math.max(0, Math.min(ed.dur - 0.02, t)); } catch (e) {}
  }

  function edRender() {
    const p1 = ed.dur ? (ed.start / ed.dur) * 100 : 0;
    const p2 = ed.dur ? (ed.end / ed.dur) * 100 : 100;
    $("#ed-sel").style.left = p1 + "%";
    $("#ed-sel").style.width = Math.max(0, p2 - p1) + "%";
    $("#ed-h-start").style.left = p1 + "%";
    $("#ed-h-end").style.left = p2 + "%";
    $("#ed-start").textContent = ed.start.toFixed(2);
    $("#ed-end").textContent = ed.end.toFixed(2);
    $("#ed-len").textContent = (ed.end - ed.start).toFixed(2);
    $("#ed-range").textContent = `${ed.start.toFixed(2)} – ${ed.end.toFixed(2)} с`;
  }

  async function setupEditor(f) {
    const isVideo = f.kind === "video";
    const isGif = f.kind === "image" && f.ext === "gif";
    if (!isVideo && !isGif) {
      $("#editor").hidden = true;
      ed.ready = false;
      return;
    }
    try {
      const p = await api("/api/preview/" + f.id);
      ed.url = p.url;
      ed.dur = Number(p.duration) || 3;
      ed.start = 0;
      ed.end = Math.min(MAX_LEN, ed.dur);
      const v = $("#ed-video");
      v.src = p.url;
      v.load();
      ed.ready = true;
      $("#editor").hidden = state.mode === "static";
      edRender();
    } catch (e) {
      $("#editor").hidden = true;
      ed.ready = false;
      toast(e.message, true);
    }
  }

  const tl = $("#ed-timeline");
  tl.addEventListener("pointerdown", (e) => {
    if (!ed.ready) return;
    const r = tl.getBoundingClientRect();
    const t = Math.max(0, Math.min(ed.dur, ((e.clientX - r.left) / r.width) * ed.dur));
    const pxPerSec = r.width / Math.max(0.001, ed.dur);
    if (Math.abs(t - ed.start) * pxPerSec < 16) {
      ed.dragging = "start";
    } else if (Math.abs(t - ed.end) * pxPerSec < 16) {
      ed.dragging = "end";
    } else {
      const len = ed.end - ed.start;
      ed.start = Math.max(0, Math.min(t - len / 2, ed.dur - len));
      ed.end = ed.start + len;
      ed.dragging = "move";
      edSeek(ed.start);
    }
    try { tl.setPointerCapture(e.pointerId); } catch (err) {}
    edRender();
  });

  tl.addEventListener("pointermove", (e) => {
    if (!ed.dragging || !ed.ready) return;
    const r = tl.getBoundingClientRect();
    const t = Math.max(0, Math.min(ed.dur, ((e.clientX - r.left) / r.width) * ed.dur));
    if (ed.dragging === "start") {
      ed.start = Math.min(t, ed.end - MIN_LEN);
      if (ed.end - ed.start > MAX_LEN) ed.end = ed.start + MAX_LEN;
      edSeek(ed.start);
    } else if (ed.dragging === "end") {
      ed.end = Math.max(t, ed.start + MIN_LEN);
      if (ed.end - ed.start > MAX_LEN) ed.start = ed.end - MAX_LEN;
      edSeek(ed.end - 0.05);
    } else {
      const len = ed.end - ed.start;
      ed.start = Math.max(0, Math.min(t - len / 2, ed.dur - len));
      ed.end = ed.start + len;
      edSeek(ed.start);
    }
    edRender();
  });

  ["pointerup", "pointercancel"].forEach((ev) =>
    tl.addEventListener(ev, () => { ed.dragging = null; }));

  $("#ed-play").addEventListener("click", () => {
    const v = $("#ed-video");
    if (!ed.ready) return;
    v.currentTime = ed.start;
    v.play().catch(() => {});
    const stop = () => {
      if (v.currentTime >= ed.end - 0.02) {
        v.pause();
        v.removeEventListener("timeupdate", stop);
      }
    };
    v.addEventListener("timeupdate", stop);
  });

  $("#ed-video").addEventListener("timeupdate", () => {
    const v = $("#ed-video");
    const p = ed.dur ? (v.currentTime / ed.dur) * 100 : 0;
    $("#ed-playhead").style.left = p + "%";
  });

  $("#go2").addEventListener("click", async () => {
    if (!state.sfile || state.busy) return;
    state.busy = true;
    $("#go2").disabled = true;
    const prog = $("#progress2");
    prog.hidden = false;
    prog.classList.remove("error");
    $("#p2-label").textContent = "сборка стикера";
    $("#p2-pct").textContent = "0%";
    $("#p2-bar").style.width = "0%";
    $("#p2-note").textContent = "подготовка…";

    try {
      const { job } = await api("/api/sticker", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: state.sfile.id, mode: state.mode, mask: state.mask,
          start: state.mode === "static" ? 0 : ed.start,
          duration: state.mode === "static" ? 0 : Math.max(0.3, ed.end - ed.start),
        }),
      });
      const res = await poll(job, (j) => {
        $("#p2-pct").textContent = Math.round(j.progress) + "%";
        $("#p2-bar").style.width = j.progress + "%";
        if (j.note) $("#p2-note").textContent = j.note;
      });
      if (res.status === "error") throw new Error(res.error || "ошибка сборки");
      $("#p2-pct").textContent = "100%";
      $("#p2-bar").style.width = "100%";
      $("#p2-note").textContent = "готово · " + fmtBytes(res.result.size);
      renderResult(res.result, true);
      refreshStats();
      toast("стикер готов · " + fmtBytes(res.result.size));
    } catch (e) {
      prog.classList.add("error");
      $("#p2-label").textContent = "ошибка";
      $("#p2-pct").textContent = "—";
      $("#p2-note").textContent = e.message;
      toast(e.message, true);
    } finally {
      state.busy = false;
      $("#go2").disabled = false;
    }
  });

  /* ---------------------------------------------------------- результат */
  const IMG = ["png", "jpg", "jpeg", "webp", "avif", "gif", "bmp", "tiff", "ico", "svg"];
  const VID = ["mp4", "webm", "mkv", "mov", "m4v", "avi"];
  const AUD = ["mp3", "wav", "ogg", "oga", "opus", "flac", "aac", "m4a"];
  const TXT = ["txt", "csv", "md", "html", "htm"];

  function renderResult(f, isSticker = false) {
    $("#dock-empty").hidden = true;
    const body = $("#dock-body");
    body.hidden = false;
    $("#dock-tag").textContent = isSticker ? "стикер" : "готово";

    const alpha = ["png", "webp", "avif", "gif", "webm"].includes(f.ext);
    let preview = "";
    if (IMG.includes(f.ext)) {
      preview = `<img src="${f.preview}" alt="${esc(f.name)}">`;
    } else if (VID.includes(f.ext)) {
      preview = `<video src="${f.preview}" controls autoplay muted loop playsinline></video>`;
    } else if (AUD.includes(f.ext)) {
      preview = `<audio src="${f.preview}" controls></audio>`;
    } else if (f.ext === "pdf") {
      preview = `<iframe src="${f.preview}" title="PDF"></iframe>`;
    } else if (TXT.includes(f.ext)) {
      preview = `<div class="txt" id="txt-prev">загрузка…</div>`;
    } else {
      preview = `<div class="ph">${esc(f.ext)} · предпросмотр недоступен</div>`;
    }

    const rows = [];
    rows.push(["формат", f.ext.toUpperCase()]);
    rows.push(["размер", fmtBytes(f.size)]);
    if (f.meta && f.meta.width) rows.push(["разрешение", `${f.meta.width}×${f.meta.height}`]);
    if (f.meta && f.meta.duration) rows.push(["длительность", f.meta.duration.toFixed(2) + " с"]);
    if (f.meta && f.meta.start !== undefined && f.meta.start !== null) {
      rows.push(["фрагмент", `${Number(f.meta.start).toFixed(2)} – ${(Number(f.meta.start) + Number(f.meta.duration || 0)).toFixed(2)} с`]);
    }
    if (f.meta && f.meta.fps) rows.push(["кадры", f.meta.fps + " fps"]);
    if (f.meta && f.meta.vcodec) rows.push(["кодек", f.meta.vcodec]);
    if (f.meta && f.meta.acodec) rows.push(["аудио", f.meta.acodec]);
    if (f.meta && f.meta.mask !== undefined) rows.push(["маска", f.meta.mask ? "круглая" : "нет"]);
    if (f.meta && f.meta.limit) rows.push(["лимит TG", fmtBytes(f.meta.limit) + (f.meta.fits ? " · ок" : " · превышен")]);

    body.innerHTML = `
      <div class="preview-box${alpha ? " checker" : ""}">${preview}</div>
      <div class="meta-rows">${rows.map(([k, v]) => `<div class="meta-row"><span>${k}</span><b>${esc(v)}</b></div>`).join("")}</div>
      <div class="dock-actions">
        <a class="btn primary wide" href="${f.url}" download>Скачать ${esc(f.ext.toUpperCase())}</a>
        <div class="row">
          <button class="btn ghost" data-qr="${f.id}" type="button">QR-код</button>
          <a class="btn ghost" href="${f.page}" target="_blank" rel="noopener">Страница</a>
        </div>
        <button class="btn danger" data-del="${f.id}" type="button">Удалить файл</button>
      </div>`;

    if (TXT.includes(f.ext)) {
      api("/api/text/" + f.id).then((r) => {
        const el = $("#txt-prev");
        if (el) el.textContent = r.text || "(пусто)";
      }).catch(() => {});
    }

    body.querySelectorAll("[data-qr]").forEach((b) =>
      b.addEventListener("click", () => openQR(b.dataset.qr)));
    body.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", () => delFile(b.dataset.del)));

    if (window.innerWidth <= 1240) body.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function delFile(id) {
    try {
      await api("/api/file/" + id, { method: "DELETE" });
      $("#dock-body").hidden = true;
      $("#dock-empty").hidden = false;
      $("#dock-tag").textContent = "ожидание";
      toast("файл удалён");
      refreshStats();
      if ($("#view-library").classList.contains("active")) loadLibrary();
    } catch (e) { toast(e.message, true); }
  }

  /* ---------------------------------------------------------- QR */
  function openQR(id) {
    $("#qr-img").src = "/qr/" + id + ".png";
    $("#qr-link").value = BASE + "/d/" + id;
    $("#modal").classList.add("open");
  }
  $("#qr-close").addEventListener("click", () => $("#modal").classList.remove("open"));
  $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").classList.remove("open"); });
  $("#qr-copy").addEventListener("click", async () => {
    const inp = $("#qr-link");
    try {
      await navigator.clipboard.writeText(inp.value);
      toast("ссылка скопирована");
    } catch (e) {
      inp.select();
      document.execCommand("copy");
      toast("ссылка скопирована");
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("#modal").classList.remove("open");
  });

  /* ---------------------------------------------------------- хранилище */
  async function loadLibrary() {
    const box = $("#lib");
    box.innerHTML = `<div class="empty">загрузка…</div>`;
    try {
      const { files } = await api("/api/library");
      if (!files.length) {
        box.innerHTML = `<div class="empty">Пока пусто. Сконвертируй что-нибудь — файлы появятся здесь.</div>`;
        return;
      }
      box.innerHTML = files.map((f) => {
        const thumb = f.poster
          ? `<img src="${f.poster}" alt="">`
          : (f.kind === "image" && f.ext !== "svg" ? `<img src="${f.preview}" alt="">` : esc(f.ext));
        const role = f.role === "output" ? "результат" : "исходник";
        return `<div class="lib-row">
          <div class="lib-thumb">${thumb}</div>
          <div>
            <div class="lib-name">${esc(f.name)}</div>
            <div class="lib-meta">${esc(f.ext.toUpperCase())} · ${fmtBytes(f.size)} · ${role} · ${fmtDate(f.created)}</div>
          </div>
          <div class="lib-actions">
            <a class="icon-btn" href="${f.url}" download title="Скачать">
              <svg viewBox="0 0 24 24"><path d="M12 4v11m0 0l-4-4m4 4l4-4"/><path d="M5 19h14"/></svg>
            </a>
            <button class="icon-btn" data-qr="${f.id}" title="QR">
              <svg viewBox="0 0 24 24"><rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><path d="M14 14h2v2h-2zM18 18h2v2h-2z"/></svg>
            </button>
            <button class="icon-btn" data-del="${f.id}" title="Удалить">
              <svg viewBox="0 0 24 24"><path d="M5 7h14M9 7V5h6v2M7 7l1 12h8l1-12"/></svg>
            </button>
          </div>
        </div>`;
      }).join("");
      box.querySelectorAll("[data-qr]").forEach((b) => b.addEventListener("click", () => openQR(b.dataset.qr)));
      box.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => delFile(b.dataset.del)));
    } catch (e) {
      box.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    }
  }

  /* ---------------------------------------------------------- статистика */
  function animateNum(el, target, isBytes) {
    const dur = 900;
    const t0 = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      const v = target * e;
      if (isBytes) {
        el.innerHTML = v >= 1024 ** 3
          ? (v / 1024 ** 3).toFixed(2) + "<u>ГБ</u>"
          : (v / 1024 ** 2).toFixed(1) + "<u>МБ</u>";
      } else {
        el.innerHTML = Math.round(v).toLocaleString("ru-RU");
      }
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function paintStats(s) {
    const nums = $$(".stat .num");
    animateNum(nums[0], s.bytes, true);
    animateNum(nums[1], s.outputs, false);
    animateNum(nums[2], s.sources, false);
    animateNum(nums[3], s.by_ext.length, false);

    const total = s.by_kind.reduce((a, k) => a + k.b, 0) || 1;
    const colors = ["var(--lime)", "#7ee2a8", "#5a8cff", "#ffb020"];
    const names = { image: "изображения", audio: "аудио", video: "видео", document: "документы" };
    $("#stats-bar").innerHTML = s.by_kind.map((k, i) =>
      `<i style="width:${(k.b / total) * 100}%;background:${colors[i % 4]}"></i>`).join("");
    $("#legend").innerHTML = s.by_kind.map((k, i) =>
      `<span><i style="background:${colors[i % 4]}"></i>${names[k.kind] || k.kind} · ${fmtBytes(k.b)}</span>`).join("")
      || `<span>пока нет данных</span>`;
  }

  async function refreshStats() {
    try { paintStats(await api("/api/stats")); } catch (e) {}
  }

  /* ---------------------------------------------------------- вставка из буфера */
  document.addEventListener("paste", (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (const it of items) {
      if (it.type.startsWith("image/")) {
        const f = it.getAsFile();
        if (f) {
          const named = new File([f], "clipboard." + (f.type.split("/")[1] || "png"), { type: f.type });
          if ($("#view-stickers").classList.contains("active")) {
            uploadFile(named).then(showStickerFile).catch((err) => toast(err.message, true));
          } else {
            uploadFile(named).then(showFile).catch((err) => toast(err.message, true));
          }
          toast("вставлено из буфера");
        }
        break;
      }
    }
  });

  /* ---------------------------------------------------------- старт */
  paintStats(boot.stats);
  renderSpecs();
})();
