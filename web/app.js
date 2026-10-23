"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  user: null,
  workspaces: [],
  workspace: null,
  videos: [],
  experiments: [],
  operations: [],
  route: 0,
  poll: null,
};
const labels = {
  draft: "Draft",
  ready: "Ready to publish",
  awaiting: "Awaiting results",
  completed: "Completed",
};
const outcomes = {
  observed_improvement: "Observed improvement",
  criterion_not_met: "Criterion not met",
  insufficient_data: "Not enough comparable data",
};
const e = (tag, cls = "", value = "") => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (value !== null && value !== undefined) n.textContent = String(value);
  return n;
};
const append = (node, ...children) => {
  for (const child of children) if (child) node.append(child);
  return node;
};
const percent = (n) =>
  n === null || n === undefined ? "—" : `${(Number(n) * 100).toFixed(1)}%`;
const formatTime = (seconds) =>
  `${Math.floor(Number(seconds || 0) / 60)}:${(Number(seconds || 0) % 60).toFixed(2).padStart(5, "0")}`;
const date = (value) => (value ? new Date(value).toLocaleString() : "");
const json = (value) => JSON.stringify(value, null, 2);
const wsPath = (tail) =>
  `/workspaces/${encodeURIComponent(state.workspace.id)}${tail}`;
const videoPath = (id, tail = "") =>
  wsPath(`/videos/${encodeURIComponent(id)}${tail}`);
function showNotice(message, failure = false) {
  $("notice").textContent = message;
  $("notice").className = `notice${failure ? " failure" : ""}`;
}
function errorMessage(err) {
  return err instanceof Error ? err.message : String(err);
}
function button(label, handler, cls = "secondary") {
  const n = e("button", cls, label);
  n.type = "button";
  n.addEventListener("click", async () => {
    n.disabled = true;
    try {
      await handler();
    } catch (err) {
      showNotice(errorMessage(err), true);
    } finally {
      n.disabled = false;
    }
  });
  return n;
}
function list(items) {
  const n = e("ul", "compact-list");
  for (const item of items || []) n.append(e("li", "", item));
  return n;
}
function field(label, type, name, value = "", options = {}) {
  const input = e(type === "textarea" ? "textarea" : "input");
  if (type !== "textarea") input.type = type;
  input.name = name;
  input.value = value ?? "";
  Object.assign(input, options);
  return append(e("label", "", label), input);
}
function formValue(form, name) {
  return new FormData(form).get(name);
}
function empty(title, description) {
  return append(e("div", "empty"), e("h3", "", title), e("p", "", description));
}
function pageHead(kicker, title, description, action) {
  const head = e("div", "page-head");
  head.append(
    append(
      e("div"),
      e("div", "eyebrow", kicker),
      e("h1", "", title),
      e("p", "", description),
    ),
  );
  if (action) head.append(action);
  return head;
}
function section(title, meta) {
  return append(
    e("div", "section-heading"),
    e("h2", "", title),
    meta ? e("span", "muted", meta) : null,
  );
}
function badge(text, cls = "") {
  return e("span", `tag ${cls}`, text);
}
function statusBadge(status) {
  return badge(
    labels[status] || status,
    status === "completed" ? "good" : status === "awaiting" ? "warm" : "",
  );
}
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  let body = options.body;
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    body,
    credentials: "same-origin",
  });
  const data = await response
    .json()
    .catch(() => ({ detail: `Request failed (${response.status})` }));
  if (!response.ok) {
    const detail =
      data.detail || data.error || `Request failed (${response.status})`;
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  return data;
}
async function refreshData() {
  const workspaceId = state.workspace.id;
  const route = state.route;
  const [videos, experiments] = await Promise.all([
    api(wsPath("/videos")),
    api(wsPath("/experiments")),
  ]);
  if (state.workspace?.id !== workspaceId || state.route !== route) return;
  state.videos = videos;
  state.experiments = experiments;
}
function currentVideo(id) {
  return state.videos.find((v) => v.id === id);
}
function media(id) {
  return `/api${videoPath(id, "/media")}`;
}
function player(id, start = 0) {
  const n = e("video", "video-player");
  n.controls = true;
  n.preload = "metadata";
  n.playsInline = true;
  n.src = media(id);
  if (start > 0)
    n.addEventListener(
      "loadedmetadata",
      () => {
        n.currentTime = Math.min(start, n.duration || start);
      },
      { once: true },
    );
  return n;
}
function routeTo(view, id = "", time = "") {
  location.hash = `${view}${id ? "/" + encodeURIComponent(id) : ""}${time !== "" ? "/" + Number(time) : ""}`;
}
function sourceLink(source) {
  return button(
    `${source.title || "Source video"} · ${formatTime(source.start)}–${formatTime(source.end)}`,
    () => routeTo("analysis", source.video_id, source.start),
    "source-link",
  );
}
function renderMetrics(metrics) {
  if (!metrics?.length)
    return e(
      "p",
      "hint",
      "No publication results imported. Missing values stay unknown.",
    );
  const wrap = e("div", "table-wrap"),
    table = e("table"),
    head = e("thead"),
    tr = e("tr");
  for (const t of [
    "Publication",
    "Context",
    "Measurement period",
    "Starts",
    "3s retention",
  ])
    tr.append(e("th", "", t));
  head.append(tr);
  table.append(head);
  const body = e("tbody");
  for (const m of metrics) {
    const row = e("tr");
    row.append(
      append(
        e("td"),
        e("span", "", m.publication_id),
        e("span", "video-meta", m.source),
      ),
      e("td", "", `${m.platform} · ${m.traffic}`),
      e("td", "small", `${m.period_start} → ${m.period_end}`),
      e("td", "number", m.views ?? "—"),
      e("td", "number", percent(m.retention_3s)),
    );
    body.append(row);
  }
  table.append(body);
  wrap.append(table);
  return wrap;
}
async function enterApp() {
  state.user = await api("/me");
  state.workspaces = await api("/workspaces");
  $("auth").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("account").textContent = state.user.email;
  const select = $("workspaceSelect");
  select.replaceChildren();
  for (const w of state.workspaces) {
    const option = e("option", "", w.name);
    option.value = w.id;
    select.append(option);
  }
  const previous = state.workspace?.id;
  state.workspace =
    state.workspaces.find((w) => w.id === previous) ||
    state.workspaces[0] ||
    null;
  if (state.workspace) select.value = state.workspace.id;
  await render();
  if (!state.poll) state.poll = setInterval(pollOperations, 2500);
}
async function authenticate(register = false, demo = false) {
  $("authError").classList.add("hidden");
  try {
    await api(register ? "/register" : "/login", {
      method: "POST",
      body: {
        email: demo ? "demo@example.test" : $("email").value,
        password: demo ? "creative-demo" : $("password").value,
      },
    });
    await enterApp();
  } catch (err) {
    $("authError").textContent = errorMessage(err);
    $("authError").classList.remove("hidden");
  }
}
$("authForm").addEventListener("submit", (event) => {
  event.preventDefault();
  authenticate();
});
$("register").addEventListener("click", () => {
  if ($("authForm").reportValidity()) authenticate(true);
});
$("demoLogin").addEventListener("click", () => authenticate(false, true));
$("logout").addEventListener("click", async () => {
  try {
    await api("/logout", { method: "POST", body: {} });
    state.user = null;
    state.workspace = null;
    clearInterval(state.poll);
    state.poll = null;
    $("app").classList.add("hidden");
    $("auth").classList.remove("hidden");
  } catch (err) {
    showNotice(errorMessage(err), true);
  }
});
$("workspaceSelect").addEventListener("change", async (event) => {
  state.workspace = state.workspaces.find((w) => w.id === event.target.value);
  state.operations = [];
  location.hash = "library";
  await render();
});
$("newWorkspace").addEventListener("click", () => {
  $("workspaceError").classList.add("hidden");
  $("workspaceDialog").showModal();
});
$("closeWorkspace").addEventListener("click", () =>
  $("workspaceDialog").close(),
);
$("workspaceForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = Object.fromEntries(new FormData(event.target));
    state.workspace = await api("/workspaces", { method: "POST", body: data });
    $("workspaceDialog").close();
    event.target.reset();
    location.hash = "library";
    await enterApp();
  } catch (err) {
    $("workspaceError").textContent = errorMessage(err);
    $("workspaceError").classList.remove("hidden");
  }
});
$("activityToggle").addEventListener("click", () => {
  $("activity").classList.toggle("hidden");
  renderActivity();
});
window.addEventListener("hashchange", () => render());
async function render() {
  if (!state.user) return;
  const ticket = ++state.route;
  const content = $("content");
  if (!state.workspace) {
    content.replaceChildren(
      pageHead(
        "START HERE",
        "One brand. One place.",
        "Create a workspace to keep its videos, publication results and experiments together.",
      ),
      button(
        "Create your first workspace",
        () => $("workspaceDialog").showModal(),
        "primary",
      ),
    );
    return;
  }
  $("workspaceName").textContent = state.workspace.name;
  $("workspaceType").textContent = state.workspace.synthetic
    ? "Synthetic demo"
    : "Private workspace";
  $("workspaceType").className =
    `tag${state.workspace.synthetic ? " synthetic" : ""}`;
  let [view, id, time] = location.hash.slice(1).split("/");
  view = view || "library";
  id = id ? decodeURIComponent(id) : "";
  document
    .querySelectorAll("nav a")
    .forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  content.replaceChildren(e("div", "loading", "Loading workspace…"));
  try {
    await refreshData();
    if (ticket !== state.route) return;
    const body = await (
      {
        library: renderLibrary,
        analysis: () => renderAnalysis(id, Number(time || 0)),
        experiments: () => renderExperiments(id),
        knowledge: renderKnowledge,
      }[view] || renderLibrary
    )();
    if (ticket !== state.route) return;
    content.replaceChildren(body);
    if (state.lastRoute !== location.hash) {
      state.lastRoute = location.hash;
      window.scrollTo({ top: 0, behavior: "instant" });
    }
    await pollOperations();
  } catch (err) {
    if (ticket === state.route)
      content.replaceChildren(
        empty("This view could not load", errorMessage(err)),
        button("Try again", render),
      );
  }
}
function uploadForms() {
  const wrap = e("div", "import-strip"),
    videoBox = e("details"),
    csvBox = e("details");
  videoBox.append(e("summary", "", "Upload a video"));
  const videoForm = e("form", "form-grid");
  videoForm.append(
    field("Title", "text", "title", "", { required: true, maxLength: 160 }),
    field("MP4 video · up to 50 MB", "file", "file", "", {
      required: true,
      accept: "video/mp4,.mp4",
    }),
    e(
      "p",
      "hint",
      "Upload material you have permission to use. Video processing runs locally.",
    ),
  );
  const submit = e("button", "primary", "Upload video");
  submit.type = "submit";
  videoForm.append(submit);
  const sampleVideo = e(
    "a",
    "plain-link",
    "Download a synthetic MP4 for testing ↗",
  );
  sampleVideo.href = "/api/demo/sample-video";
  sampleVideo.download = "synthetic-sample.mp4";
  videoForm.append(sampleVideo);
  videoForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const file = formValue(videoForm, "file");
      if (file.size > 50 * 1024 * 1024)
        throw new Error("Video exceeds the 50 MB limit.");
      const result = await api(wsPath("/videos"), {
        method: "POST",
        body: new FormData(videoForm),
      });
      showNotice("Video uploaded. Open its analysis to inspect the timeline.");
      await render();
    } catch (err) {
      showNotice(errorMessage(err), true);
    } finally {
      submit.disabled = false;
    }
  });
  videoBox.append(videoForm);
  csvBox.append(e("summary", "", "Import publication results"));
  const csvForm = e("form", "form-grid");
  csvForm.append(
    field("Statistics CSV", "file", "file", "", {
      required: true,
      accept: ".csv,text/csv",
    }),
  );
  const template = e("a", "plain-link", "Download workspace CSV template ↗");
  template.href = `/api${wsPath("/csv-template")}`;
  template.download = "publication-results.csv";
  csvForm.append(
    template,
    e(
      "p",
      "hint",
      "Retention is a fraction from 0 to 1. Views means video starts. Keep missing values blank. Paid and organic results remain separate.",
    ),
  );
  const importButton = e("button", "primary", "Validate & import");
  importButton.type = "submit";
  csvForm.append(importButton);
  csvForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    importButton.disabled = true;
    try {
      const r = await api(wsPath("/import"), {
        method: "POST",
        body: new FormData(csvForm),
      });
      showNotice(
        `Import complete: ${r.inserted ?? 0} new records; ${r.duplicate ?? 0} unchanged duplicates skipped.`,
      );
      await render();
    } catch (err) {
      showNotice(`CSV import rejected. ${errorMessage(err)}`, true);
    } finally {
      importButton.disabled = false;
    }
  });
  csvBox.append(csvForm);
  wrap.append(videoBox, csvBox);
  return wrap;
}
async function renderLibrary() {
  const root = e("div");
  root.append(
    pageHead(
      "01 / LIBRARY",
      "The work behind the numbers.",
      "Keep each video connected to its publication context. Start with an observation, then change one thing.",
    ),
    uploadForms(),
  );
  const layout = e("div", "library-layout"),
    left = e("section"),
    right = e("aside", "panel");
  left.append(section("Video library", `${state.videos.length} videos`));
  if (!state.videos.length)
    left.append(
      empty(
        "Start with your first clip",
        "Upload an MP4, then import its publication results using the workspace template.",
      ),
    );
  else {
    const wrap = e("div", "table-wrap"),
      table = e("table"),
      head = e("thead"),
      hr = e("tr");
    for (const t of ["Video", "Length", "Results", "Analysis", ""])
      hr.append(e("th", "", t));
    head.append(hr);
    table.append(head);
    const body = e("tbody");
    for (const v of state.videos) {
      const row = e("tr"),
        title = e("td");
      title.append(
        e("span", "video-name", v.title),
        e(
          "span",
          "video-meta",
          `${v.width} × ${v.height} · ${v.synthetic ? "Synthetic media" : "Uploaded media"}`,
        ),
      );
      row.append(
        title,
        e("td", "number", `${Number(v.duration).toFixed(1)}s`),
        e(
          "td",
          "",
          `${v.metrics?.length || 0} record${v.metrics?.length === 1 ? "" : "s"}`,
        ),
        e(
          "td",
          "small",
          v.analysis
            ? v.analysis.mode === "synthetic_fixture"
              ? "Fixture annotation"
              : v.analysis.mode === "openai"
                ? "Model analysis"
                : v.analysis.mode === "gemini_import"
                  ? "Saved Gemini analysis"
                : "Local measurements"
            : "Not analyzed",
        ),
        append(
          e("td"),
          button("Inspect ↗", () => routeTo("analysis", v.id), "row-action"),
        ),
      );
      body.append(row);
    }
    table.append(body);
    wrap.append(table);
    left.append(
      wrap,
      e(
        "p",
        "measure-note",
        "3s retention = video starts still viewing at 3 seconds ÷ all video starts. A blank statistic is unknown, never zero. Publication contexts are compared only when compatible.",
      ),
    );
  }
  right.append(
    section("Next experiments"),
    e(
      "p",
      "hint",
      "Rule-based suggestions from saved evidence. Numerical comparisons are calculated locally.",
    ),
    button(
      "Explain with model",
      async () => {
        const op = await api(wsPath("/recommendations/generate"), {
          method: "POST",
          body: {},
        });
        trackOperation(op);
        showNotice(
          "Model explanation requested. See Activity for its actual outcome.",
        );
        await pollOperations();
      },
      "quiet",
    ),
  );
  const recs = await api(wsPath("/recommendations"));
  const recWrap = e("div", "recommendations-list");
  if (!recs.length)
    recWrap.append(
      empty(
        "An open question is enough",
        "Analyze a video to get a bounded exploratory hypothesis. More comparable results will make the observation stronger.",
      ),
    );
  for (const r of recs) {
    const card = e("article", "recommendation");
    card.append(
      badge(r.kind === "observational" ? "Observation" : "Exploratory", "warm"),
      e("h3", "", r.title),
      e("p", "", r.observation),
    );
    const sources = e("div", "source-links");
    for (const source of r.sources || []) sources.append(sourceLink(source));
    card.append(sources);
    if (r.limitations?.length)
      card.append(e("p", "limit", r.limitations.join(" ")));
    card.append(
      button(
        "Prepare experiment →",
        () => createFromRecommendation(r),
        "primary",
      ),
    );
    recWrap.append(card);
  }
  right.append(recWrap);
  layout.append(left, right);
  root.append(layout);
  return root;
}
async function createFromRecommendation(r) {
  const baseline =
    r.baseline_id ||
    r.sources?.find(
      (s) => currentVideo(s.video_id)?.analysis?.hook_category === "packaging",
    )?.video_id ||
    r.sources?.[0]?.video_id ||
    state.videos[0]?.id;
  if (!baseline) throw new Error("Upload a baseline video first.");
  const result = await api(wsPath("/experiments"), {
    method: "POST",
    body: {
      recommendation_id: r.id,
      title: r.title,
      hypothesis: r.hypothesis,
      baseline_id: baseline,
      change: r.change,
      preserve: r.preserve || [],
      metric: r.metric || "retention_3s",
      threshold_pp: r.threshold_pp ?? 5,
      min_views: r.min_views ?? 100,
      window_days: r.window_days ?? 7,
      limitations: r.limitations || [],
    },
  });
  showNotice(
    "Draft saved. Review the hypothesis and criteria before preparing a variant.",
  );
  routeTo("experiments", result.id);
}
async function renderAnalysis(id, start) {
  const root = e("div");
  const video = currentVideo(id) || state.videos[0];
  const select = e("select", "video-select");
  select.setAttribute("aria-label", "Choose video");
  for (const v of state.videos) {
    const option = e("option", "", v.title);
    option.value = v.id;
    option.selected = v.id === video?.id;
    select.append(option);
  }
  select.addEventListener("change", () => routeTo("analysis", select.value));
  root.append(
    pageHead(
      "02 / VIDEO ANALYSIS",
      video?.title || "Inspect the creative.",
      "Every interpretation belongs to a timestamp. Measured properties and model judgments stay separate.",
      select,
    ),
  );
  if (!video) {
    root.append(
      empty("No video to inspect", "Upload a clip from the library first."),
    );
    return root;
  }
  const layout = e("div", "analysis-layout"),
    left = e("section"),
    right = e("section", "panel"),
    vp = player(video.id, start);
  vp.setAttribute("aria-label", "Analysis video");
  left.append(vp);
  const facts = e("div", "facts");
  for (const [name, value] of [
    ["Duration", `${Number(video.duration).toFixed(2)}s`],
    ["Resolution", `${video.width}×${video.height}`],
    ["Frame rate", `${Number(video.fps).toFixed(2)} fps`],
    ["Audio track", video.has_audio ? "Present" : "Absent"],
  ])
    facts.append(
      append(e("div", "fact"), e("small", "", name), e("strong", "", value)),
    );
  left.append(facts);
  const analysis = video.analysis;
  left.append(
    e(
      "p",
      "status-line",
      analysis
        ? `Analysis source: ${analysis.mode === "synthetic_fixture" ? "authored synthetic fixture" : analysis.mode === "gemini_import" ? `saved response · ${analysis.model}` : analysis.mode === "openai" ? analysis.model || "OpenAI" : "local video measurements"}`
        : "No analysis saved yet.",
    ),
  );
  if (video.provenance) {
    const p = video.provenance;
    left.append(e("p", "measure-note", `${p.title} · ${p.author} · ${p.license}. ${p.modifications || ""}`));
  }
  left.append(
    append(
      e("div", "analysis-actions"),
      button(
        "Measure locally",
        () => startAnalysis(video, "local"),
        "secondary",
      ),
      button(
        "Analyze with OpenAI",
        () => startAnalysis(video, "openai"),
        "secondary",
      ),
    ),
  );
  left.append(
    e(
      "p",
      "measure-note",
      "Local analysis measures video properties and samples the timeline; it does not infer a hook or transcribe speech. OpenAI requires server-side authorization and a configured budget.",
    ),
  );
  if (analysis?.limitations?.length) left.append(list(analysis.limitations));
  right.append(
    section(
      "Timeline evidence",
      analysis?.segments?.length ? `${analysis.segments.length} entries` : "",
    ),
  );
  if (!analysis)
    right.append(
      empty(
        "Ready for a closer look",
        "Run local processing to inspect measured properties. Model interpretation is a separate operation.",
      ),
    );
  else {
    for (const s of analysis.segments || []) {
      const segment = e("article", "segment");
      const time = button(
        `${formatTime(s.start)}–${formatTime(s.end)}`,
        () => {
          vp.currentTime = s.start;
          vp.focus();
        },
        "time-link",
      );
      segment.append(
        append(e("div", "segment-head"), time, badge(s.kind)),
        e("p", "", s.text),
        e(
          "span",
          "origin",
          s.origin === "fixture"
            ? "Synthetic fixture annotation"
            : s.origin === "model"
              ? "Model interpretation"
              : "Measured from video",
        ),
      );
      right.append(segment);
    }
    right.append(
      e(
        "p",
        "measure-note",
        analysis.speech_status === "synthetic_fixture"
          ? "Speech entries, if present, are synthetic fixture annotations."
          : "Speech has not been transcribed. Visual frames do not establish what was said.",
      ),
    );
  }
  layout.append(left, right);
  root.append(layout);
  const metricSection = e("section", "panel");
  metricSection.append(
    section("Publication results"),
    renderMetrics(video.metrics),
  );
  root.append(e("hr", "subtle-line"), metricSection);
  return root;
}
async function startAnalysis(video, mode) {
  const operation = await api(videoPath(video.id, "/analyze"), {
    method: "POST",
    body: { mode },
  });
  trackOperation(operation);
  showNotice(
    `Analysis ${operation.status || "queued"}. Progress and failures are recorded in Activity.`,
  );
  await pollOperations();
}
async function renderExperiments(id) {
  const root = e("div");
  if (id === "new") return renderCreateExperiment();
  if (!id) {
    root.append(
      pageHead(
        "03 / EXPERIMENTS",
        "Change one thing. Keep the evidence.",
        "Define the expected outcome before results arrive. A failed or inconclusive experiment is still knowledge.",
        button(
          "New experiment +",
          () => routeTo("experiments", "new"),
          "primary",
        ),
      ),
    );
    if (!state.experiments.length)
      root.append(
        empty(
          "Your first experiment starts here",
          "Choose a recommendation from the library or write your own hypothesis.",
        ),
      );
    const wrap = e("div", "experiment-list");
    for (const x of state.experiments) {
      const item = button(
        "",
        () => routeTo("experiments", x.id),
        "experiment-item",
      );
      item.append(
        append(e("div"), e("h3", "", x.title), e("p", "", x.hypothesis)),
        statusBadge(x.status),
      );
      wrap.append(item);
    }
    root.append(wrap);
    return root;
  }
  const x = await api(wsPath(`/experiments/${encodeURIComponent(id)}`));
  root.append(
    append(
      e("div", "experiment-topline"),
      button(
        "← All experiments",
        () => routeTo("experiments"),
        "quiet back-button",
      ),
      e("span", "muted small", `Revision ${x.revision || 1}`),
    ),
    pageHead(
      "03 / EXPERIMENT",
      x.title,
      "One hypothesis, a controlled edit and an explicit decision rule.",
      statusBadge(x.status),
    ),
  );
  const steps = e("div", "steps"),
    statuses = Object.keys(labels),
    current = statuses.indexOf(x.status);
  statuses.forEach((s, i) =>
    steps.append(
      e(
        "div",
        `step ${i === current ? "current" : i < current ? "past" : ""}`,
        `${String(i + 1).padStart(2, "0")} · ${labels[s]}`,
      ),
    ),
  );
  root.append(
    steps,
    append(
      e("div", "experiment-question"),
      e("div", "eyebrow", "WHAT WE ARE TESTING"),
      e("p", "", x.hypothesis),
    ),
  );
  if (x.result) root.append(resultBlock(x.result));
  const pair = e("div", "comparison");
  pair.append(
    append(e("section"), e("h3", "", "Baseline"), player(x.baseline_id)),
  );
  const variant = e("section");
  variant.append(
    append(
      e("h3"),
      e("span", "", "Changed version"),
      x.variant_id ? badge("Edited media", "good") : badge("Not created"),
    ),
  );
  variant.append(
    x.variant_id
      ? player(x.variant_id)
      : e(
          "div",
          "variant-placeholder",
          "Upload an alternative fragment below. A generation brief is not a generated video.",
        ),
  );
  pair.append(variant);
  root.append(pair);
  const columns = e("div", "experiment-columns"),
    left = e("div"),
    right = e("div");
  const plan = e("section", "panel");
  plan.append(section("The change & the controls"));
  const kv = e("dl", "key-value");
  for (const [k, v] of [
    ["Change", x.change],
    [
      "Keep fixed",
      Array.isArray(x.preserve) ? x.preserve.join("; ") : x.preserve,
    ],
    ["Metric", "3-second retention"],
    ["Decision rule", `At least +${x.threshold_pp} percentage points`],
    ["Minimum data", `${x.min_views} starts per publication`],
    ["Observe for", `${x.window_days} days`],
  ])
    kv.append(append(e("div"), e("dt", "", k), e("dd", "", v)));
  plan.append(kv);
  if (x.limitations?.length) plan.append(list(x.limitations));
  if (x.source_snapshot) {
    const d = e("details");
    d.append(
      e("summary", "", "Original observation and source snapshot"),
      e("pre", "", json(x.source_snapshot)),
    );
    plan.append(d);
    const snapshotSources = Array.isArray(x.source_snapshot)
      ? x.source_snapshot
      : x.source_snapshot.sources || [];
    for (const source of snapshotSources)
      if (source.video_id) plan.append(sourceLink(source));
  }
  plan.append(criteriaEditor(x));
  left.append(plan);
  const edit = e("section", "panel");
  edit.append(section("Prepare the changed version"));
  const gen = e("details");
  gen.append(
    e("summary", "", "Generation brief · instruction only"),
    e(
      "pre",
      "",
      typeof x.generation_brief === "string"
        ? x.generation_brief
        : json(x.generation_brief || {}),
    ),
  );
  edit.append(
    e(
      "p",
      "hint",
      "Generate or record an alternative clip, then upload it here. This app replaces only the chosen visual interval and retains the original soundtrack. No generation provider has been called.",
    ),
    gen,
  );
  if (x.status === "draft") edit.append(editForm(x));
  else
    edit.append(
      e(
        "p",
        "status-line",
        "The variant is locked after the draft stage. The saved edit remains attached to this experiment.",
      ),
    );
  if (x.edit_report) {
    const detail = e("details");
    detail.append(
      e("summary", "", "What changed · processing report"),
      e("pre", "", json(x.edit_report)),
    );
    edit.append(detail);
  }
  left.append(edit);
  const next = e("section", "panel");
  next.append(section("Next step"));
  const template = e(
    "a",
    "plain-link",
    "Download results CSV for this experiment ↗",
  );
  template.href = `/api${wsPath(`/experiments/${x.id}/csv-template`)}`;
  template.download = "experiment-results.csv";
  next.append(
    template,
    e(
      "p",
      "measure-note",
      state.workspace.synthetic
        ? "This template includes synthetic example results. Import it from the Library to exercise the workflow."
        : "Fill the blank template with actual publication results, then import it from the Library.",
    ),
  );
  if (x.status === "draft") {
    next.append(
      e(
        "p",
        "muted small",
        x.variant_id
          ? "Review the edited video and the decision rule, then mark the experiment ready."
          : "Prepare a changed version before marking the experiment ready.",
      ),
      button("Mark ready to publish", () => transition(x, "ready"), "primary"),
    );
  } else if (x.status === "ready") {
    next.append(
      e(
        "p",
        "muted small",
        "Publish both versions outside this application. Starting the observation period freezes the criteria used for the result.",
      ),
      button("Start observation", () => transition(x, "awaiting"), "primary"),
    );
  } else if (x.status === "awaiting") {
    next.append(
      e(
        "p",
        "muted small",
        "Import publication results from the Library. Evaluate once both observation windows have ended. Missing or incompatible data produces an inconclusive result.",
      ),
      button("Import results", () => routeTo("library"), "secondary"),
      button(
        "Evaluate available results",
        async () => {
          await api(wsPath(`/experiments/${x.id}/evaluate`), {
            method: "POST",
            body: {},
          });
          showNotice(
            "Result saved with its evaluation criteria and limitations.",
          );
          await render();
        },
        "primary",
      ),
    );
  } else
    next.append(
      e(
        "p",
        "muted small",
        "This result is saved in Brand knowledge, including its limitations and unsuccessful outcomes.",
      ),
      button("Open brand knowledge", () => routeTo("knowledge"), "secondary"),
    );
  right.append(next);
  const records = e("section", "panel");
  records.append(section("Result records"));
  for (const [name, vid] of [
    ["Baseline", x.baseline_id],
    ["Changed version", x.variant_id],
  ]) {
    records.append(e("h3", "", name));
    const v = currentVideo(vid);
    records.append(
      e(
        "p",
        "status-line",
        v?.metrics?.length
          ? `${v.metrics.length} publication record(s). Open the video for measurement context.`
          : "No results imported.",
      ),
    );
    if (v)
      records.append(
        button(
          "View records ↗",
          () => routeTo("analysis", v.id),
          "row-action",
        ),
      );
  }
  right.append(records);
  const history = e("section", "panel");
  history.append(section("Decision history"));
  if (!x.history?.length)
    history.append(
      e(
        "p",
        "hint",
        "The initial hypothesis is saved. Further edits and state changes appear here.",
      ),
    );
  for (const item of [...(x.history || [])].reverse()) {
    const h = e("div", "history-item");
    h.append(
      e(
        "strong",
        "",
        item.action || item.kind || `Revision ${item.revision || ""}`,
      ),
      e("p", "", date(item.created_at || item.at)),
    );
    const d = e("details");
    d.append(
      e("summary", "", "Inspect recorded change"),
      e("pre", "", json(item)),
    );
    h.append(d);
    history.append(h);
  }
  right.append(history);
  columns.append(left, right);
  root.append(columns);
  return root;
}
function criteriaEditor(x) {
  const details = e("details", "edit-form");
  details.append(e("summary", "", "Edit hypothesis & criteria"));
  const form = e("form", "form-grid");
  form.append(
    field("Hypothesis", "textarea", "hypothesis", x.hypothesis, {
      required: true,
      rows: 3,
      maxLength: 2000,
    }),
    field("What changes", "textarea", "change", x.change, {
      required: true,
      rows: 2,
      maxLength: 2000,
    }),
    field(
      "What stays fixed · one item per line",
      "textarea",
      "preserve",
      Array.isArray(x.preserve) ? x.preserve.join("\n") : x.preserve,
      { rows: 3 },
    ),
    append(
      e("div", "inline-fields"),
      field(
        "Required lift · percentage points",
        "number",
        "threshold_pp",
        x.threshold_pp,
        { required: true, min: 0, max: 100, step: 0.1 },
      ),
      field("Minimum starts", "number", "min_views", x.min_views, {
        required: true,
        min: 1,
        step: 1,
      }),
      field("Observation days", "number", "window_days", x.window_days, {
        required: true,
        min: 1,
        max: 365,
        step: 1,
      }),
    ),
  );
  if (x.status === "awaiting" || x.status === "completed")
    form.append(
      e(
        "p",
        "hint",
        "This change will be recorded as a later revision. The current result is evaluated against the criteria frozen when observation started.",
      ),
    );
  const save = e("button", "secondary", "Save revision");
  save.type = "submit";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    save.disabled = true;
    try {
      await api(wsPath(`/experiments/${x.id}`), {
        method: "PATCH",
        body: {
          hypothesis: formValue(form, "hypothesis"),
          change: formValue(form, "change"),
          preserve: String(formValue(form, "preserve"))
            .split("\n")
            .filter(Boolean),
          threshold_pp: Number(formValue(form, "threshold_pp")),
          min_views: Number(formValue(form, "min_views")),
          window_days: Number(formValue(form, "window_days")),
        },
      });
      showNotice("Revision saved. Earlier criteria remain in the history.");
      await render();
    } catch (err) {
      showNotice(errorMessage(err), true);
    } finally {
      save.disabled = false;
    }
  });
  details.append(form);
  return details;
}
function editForm(x) {
  const form = e("form", "form-grid");
  form.style.marginTop = "20px";
  if (state.workspace.synthetic) {
    const sample = e(
      "a",
      "plain-link",
      "Download synthetic alternative fragment ↗",
    );
    sample.href = "/api/demo/replacement";
    sample.download = "synthetic-alternative.mp4";
    form.append(sample);
  }
  const file = field(
    "Alternative fragment · MP4, up to 50 MB",
    "file",
    "file",
    "",
    { required: true, accept: ".mp4,video/mp4" },
  );
  form.append(
    file,
    append(
      e("div", "inline-fields two"),
      field("Replace from · seconds", "number", "start", 0, {
        required: true,
        min: 0,
        step: 1 / 24,
      }),
      field("Replace until · seconds", "number", "end", 2, {
        required: true,
        min: 1 / 24,
        step: 1 / 24,
      }),
    ),
    e(
      "p",
      "hint",
      "Times must align to the 24 fps edit grid. The replacement must be long enough. Only its first selected-duration seconds are used; its audio is ignored.",
    ),
  );
  const b = e("button", "primary", "Create edited version");
  b.type = "submit";
  form.append(b);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    b.disabled = true;
    try {
      const file = formValue(form, "file");
      if (file.size > 50 * 1024 * 1024)
        throw new Error("Alternative fragment exceeds 50 MB.");
      const r = await api(wsPath(`/experiments/${x.id}/edit`), {
        method: "POST",
        body: new FormData(form),
      });
      trackOperation(r);
      showNotice(
        `Edit ${r.status || "queued"}. The completed version and processing report will appear here.`,
      );
      await pollOperations();
    } catch (err) {
      showNotice(errorMessage(err), true);
    } finally {
      b.disabled = false;
    }
  });
  return form;
}
async function transition(x, status) {
  await api(wsPath(`/experiments/${x.id}`), {
    method: "PATCH",
    body: { status },
  });
  showNotice(`Experiment is now ${labels[status].toLowerCase()}.`);
  await render();
}
function renderCreateExperiment() {
  const root = e("div");
  root.append(
    pageHead(
      "03 / NEW EXPERIMENT",
      "Make the question testable.",
      "Write the prediction and the decision rule before seeing the new results.",
      button("← Experiments", () => routeTo("experiments"), "quiet"),
    ),
  );
  if (!state.videos.length) {
    root.append(
      empty(
        "A baseline is needed",
        "Upload a video in the Library before creating an experiment.",
      ),
    );
    return root;
  }
  const form = e("form", "panel form-grid wide-form");
  form.append(
    field("Experiment name", "text", "title", "", {
      required: true,
      maxLength: 160,
    }),
    field("Hypothesis", "textarea", "hypothesis", "", {
      required: true,
      rows: 3,
      maxLength: 2000,
    }),
  );
  const select = e("select");
  select.name = "baseline_id";
  for (const v of state.videos) {
    const option = e("option", "", v.title);
    option.value = v.id;
    select.append(option);
  }
  form.append(
    append(e("label", "", "Baseline video"), select),
    field(
      "The change",
      "textarea",
      "change",
      "Replace the first 2 seconds with an alternative hook.",
      { required: true, rows: 2 },
    ),
    field(
      "Keep fixed · one item per line",
      "textarea",
      "preserve",
      "Main section\nOffer and call to action\nTotal duration\nOriginal soundtrack",
      { rows: 4 },
    ),
    append(
      e("div", "inline-fields"),
      field("Required lift · percentage points", "number", "threshold_pp", 5, {
        required: true,
        min: 0,
        max: 100,
        step: 0.1,
      }),
      field("Minimum video starts", "number", "min_views", 100, {
        required: true,
        min: 1,
        step: 1,
      }),
      field("Observation window · days", "number", "window_days", 7, {
        required: true,
        min: 1,
        max: 365,
        step: 1,
      }),
    ),
    e(
      "p",
      "hint",
      "Primary metric: share of video starts retained at 3 seconds. Publication comparisons are observational; the result does not establish a causal effect.",
    ),
  );
  const save = e("button", "primary", "Create draft");
  save.type = "submit";
  form.append(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    save.disabled = true;
    try {
      const values = Object.fromEntries(new FormData(form));
      for (const key of ["threshold_pp", "min_views", "window_days"])
        values[key] = Number(values[key]);
      values.preserve = values.preserve.split("\n").filter(Boolean);
      values.metric = "retention_3s";
      values.limitations = [
        "Publication comparison is observational; audience and distribution can differ.",
      ];
      const x = await api(wsPath("/experiments"), {
        method: "POST",
        body: values,
      });
      routeTo("experiments", x.id);
    } catch (err) {
      showNotice(errorMessage(err), true);
    } finally {
      save.disabled = false;
    }
  });
  root.append(form);
  return root;
}
function resultBlock(r) {
  const root = e(
    "section",
    `result-block ${r.outcome === "insufficient_data" ? "uncertain" : ""}`,
  );
  root.append(
    badge("OBSERVATIONAL RESULT"),
    e("h2", "", outcomes[r.outcome] || r.outcome),
    e("p", "", r.summary),
  );
  if (r.delta_pp !== null && r.delta_pp !== undefined) {
    const values = e("div", "result-numbers");
    const base =
      typeof r.baseline === "number" ? r.baseline : r.baseline?.retention_3s;
    const variant =
      typeof r.variant === "number" ? r.variant : r.variant?.retention_3s;
    for (const [name, value] of [
      ["Baseline", percent(base)],
      ["Changed version", percent(variant)],
      [
        "Difference",
        `${r.delta_pp >= 0 ? "+" : ""}${Number(r.delta_pp).toFixed(1)} pp`,
      ],
    ])
      values.append(
        append(e("div"), e("span", "", name), e("strong", "", value)),
      );
    root.append(values);
  }
  if (r.limitations?.length) root.append(list(r.limitations));
  const d = e("details");
  d.append(
    e("summary", "", "Inspect calculation and frozen criteria"),
    e("pre", "", json(r)),
  );
  root.append(d);
  return root;
}
async function renderKnowledge() {
  const root = e("div");
  root.append(
    pageHead(
      "04 / BRAND KNOWLEDGE",
      "Keep what the experiment taught you.",
      "Useful observations include failures and uncertainty. Every conclusion keeps its original question and sources.",
    ),
  );
  const records = await api(wsPath("/knowledge"));
  if (!records.length) {
    root.append(
      empty(
        "No conclusions yet",
        "Complete an experiment to save its result here. “Not enough data” is a valid outcome, too.",
      ),
    );
    return root;
  }
  const wrap = e("div", "knowledge-list");
  for (const x of records) {
    const r = x.result || x;
    const item = e("article", "knowledge-item");
    item.append(
      badge(
        outcomes[r.outcome] || r.outcome || "Saved result",
        r.outcome === "observed_improvement" ? "good" : "warm",
      ),
      e("h2", "", x.title || x.hypothesis || "Experiment result"),
      e("p", "", r.summary),
    );
    if (x.hypothesis)
      item.append(e("p", "limit", `Hypothesis: ${x.hypothesis}`));
    if (r.limitations?.length) item.append(list(r.limitations));
    const actions = e("div", "actions");
    if (x.id)
      actions.append(
        button(
          "Open experiment →",
          () => routeTo("experiments", x.id),
          "row-action",
        ),
      );
    if (x.baseline_id)
      actions.append(
        button(
          "View baseline evidence",
          () => routeTo("analysis", x.baseline_id),
          "row-action",
        ),
      );
    item.append(
      actions,
      e(
        "p",
        "measure-note",
        `Saved ${date(x.updated_at || x.created_at)}${state.workspace.synthetic ? " · Synthetic demonstration results" : ""}`,
      ),
    );
    wrap.append(item);
  }
  root.append(wrap);
  return root;
}
function trackOperation(op) {
  if (op?.id)
    state.operations = [...state.operations.filter((x) => x.id !== op.id), op];
}
async function pollOperations() {
  if (!state.user || !state.workspace) return;
  const wid = state.workspace.id;
  try {
    const next = await api(wsPath("/operations"));
    if (state.workspace?.id !== wid) return;
    const before = new Map(state.operations.map((o) => [o.id, o.status]));
    state.operations = next;
    $("activityCount").textContent = next.filter((o) =>
      ["pending", "queued", "running"].includes(o.status),
    ).length;
    renderActivity();
    const changed = next.find(
      (o) =>
        ["completed", "succeeded", "failed", "interrupted"].includes(
          o.status,
        ) && ["pending", "queued", "running"].includes(before.get(o.id)),
    );
    if (changed) {
      showNotice(
        ["failed", "interrupted"].includes(changed.status)
          ? `${changed.kind} ${changed.status}: ${typeof changed.error === "string" ? changed.error : json(changed.error)}`
          : `${changed.kind} completed. Its outputs have been saved.`,
        ["failed", "interrupted"].includes(changed.status),
      );
      await render();
    }
  } catch (err) {
    /* Transient polling failures do not destroy unsaved forms. */
  }
}
function renderActivity() {
  const wrap = $("activity");
  wrap.replaceChildren(
    append(
      e("div", "section-heading"),
      e("h2", "", "Operation history"),
      button("Close", () => wrap.classList.add("hidden"), "quiet"),
    ),
  );
  if (!state.operations.length)
    wrap.append(
      e(
        "p",
        "muted small",
        "Analysis and editing operations will appear here.",
      ),
    );
  for (const op of [...state.operations].reverse()) {
    const row = e("article", "operation");
    row.append(
      append(
        e("h3"),
        e("span", "", op.kind),
        badge(
          op.status,
          op.status === "failed"
            ? "bad"
            : op.status === "completed"
              ? "good"
              : "",
        ),
      ),
      e("p", "", date(op.created_at)),
      e(
        "p",
        "",
        `${op.model || "Local processing"} · ${op.duration_ms == null ? "Duration pending" : `${(op.duration_ms / 1000).toFixed(2)}s`} · ${op.cost_usd == null ? "Cost not reported" : `$${Number(op.cost_usd).toFixed(5)}`}`,
      ),
    );
    if (op.error)
      row.append(
        e(
          "p",
          "error",
          typeof op.error === "string" ? op.error : json(op.error),
        ),
      );
    const d = e("details");
    d.append(
      e("summary", "", "Inputs, output & prompt version"),
      e(
        "pre",
        "",
        json({
          prompt_version: op.prompt_version,
          input: op.input,
          result: op.result,
        }),
      ),
    );
    row.append(d);
    wrap.append(row);
  }
}
enterApp().catch(() => {
  $("auth").classList.remove("hidden");
  $("app").classList.add("hidden");
});
