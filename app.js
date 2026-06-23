const stageColors = {
  Approved: "#0f6d55",
  "Phase III": "#0069c2",
  "Phase II": "#4f7bc8",
  "Phase I": "#6b5ac7",
  Preclinical: "#9e6a00",
  "Paused/Stopped": "#a03232",
  Unknown: "#7a8592",
};

const signalClass = {
  positive: "signal-positive",
  mixed: "signal-mixed",
  negative: "signal-negative",
  monitor: "signal-monitor",
};

const state = {
  records: [],
  filtered: [],
  conferences: [],
  intel: null,
  changelog: null,
  feedItems: [],
};

async function load() {
  const [portfolioData, conferencesData, intelData, changelogData] = await Promise.all([
    fetchJson("data/acs-drugs.json"),
    fetchJson("data/conferences.json", { conferences: [] }),
    fetchJson("data/intel-latest.json", null),
    fetchJson("data/weekly-changelog-latest.json", null),
  ]);

  state.records = portfolioData.records || [];
  state.filtered = [...state.records];
  state.conferences = conferencesData.conferences || [];
  state.intel = intelData;
  state.changelog = changelogData;

  document.getElementById("snapshotDate").textContent = portfolioData.snapshotDate || "n/a";
  document.getElementById("recordCount").textContent = String(state.records.length);
  document.getElementById("weeklyChangeCount").textContent = String((state.changelog?.cardChanges || []).length);

  seedFilter("stageFilter", unique(state.records.map((r) => r.stage)));
  seedFilter("settingFilter", unique(state.records.map((r) => r.setting)));

  bindFilters();
  bindTabs();
  bindFeedControls();

  buildFeedItems();
  renderConferences();
  applyFilters();
}

async function fetchJson(path, fallback = { records: [] }) {
  try {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) {
      return fallback;
    }
    return await res.json();
  } catch {
    return fallback;
  }
}

function unique(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function seedFilter(id, values) {
  const el = document.getElementById(id);
  values.forEach((v) => {
    const option = document.createElement("option");
    option.value = v;
    option.textContent = v;
    el.appendChild(option);
  });
}

function changedDrugSet() {
  return new Set((state.changelog?.cardChanges || []).map((c) => (c.drug || "").toLowerCase()));
}

function appendLink(parent, link, label = "open") {
  if (!link) return;
  const a = document.createElement("a");
  a.href = link;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = label;
  parent.appendChild(a);
}

function valueText(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined || value === "") return "n/a";
  return String(value);
}

function bindFilters() {
  ["search", "stageFilter", "settingFilter", "signalFilter"].forEach((id) => {
    document.getElementById(id).addEventListener("input", applyFilters);
    document.getElementById(id).addEventListener("change", applyFilters);
  });
}

function bindTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view;
      buttons.forEach((b) => b.classList.toggle("is-active", b === btn));
      document.querySelectorAll(".view").forEach((section) => {
        section.classList.toggle("is-active", section.id === `view-${view}`);
      });
    });
  });
}

function bindFeedControls() {
  document.getElementById("feedType").addEventListener("change", renderFeed);
}

function applyFilters() {
  const q = document.getElementById("search").value.toLowerCase().trim();
  const stage = document.getElementById("stageFilter").value;
  const setting = document.getElementById("settingFilter").value;
  const signal = document.getElementById("signalFilter").value;

  state.filtered = state.records.filter((r) => {
    const inText =
      !q ||
      [
        r.drug,
        r.sponsor,
        r.class,
        r.target,
        r.keyTrial,
        r.statusSummary,
        ...(r.priorityTrials || []).flatMap((trial) => [trial.name, trial.nctId, trial.note]),
      ]
        .join(" ")
        .toLowerCase()
        .includes(q);
    const inStage = stage === "all" || r.stage === stage;
    const inSetting = setting === "all" || r.setting === setting;
    const inSignal = signal === "all" || r.signal === signal;
    return inText && inStage && inSetting && inSignal;
  });

  renderCards();
  renderGrid();
  renderCharts();
  renderCatalystCount();
  renderCatalystList();
  renderCatalystPlanner();
  renderFeed();
  renderWeeklyChanges();
}

function renderCards() {
  const root = document.getElementById("cards");
  root.innerHTML = "";
  const template = document.getElementById("cardTemplate");
  const changed = changedDrugSet();

  state.filtered.forEach((r) => {
    const node = template.content.cloneNode(true);
    node.querySelector(".drug-name").textContent = r.drug;
    node.querySelector(".drug-sponsor").textContent = r.sponsor;
    node.querySelector(".drug-class").textContent = `${r.class} | Target: ${r.target}`;
    node.querySelector(".status").textContent = r.statusSummary;

    const stage = node.querySelector(".stage");
    stage.textContent = r.stage;
    stage.style.borderColor = stageColors[r.stage] || stageColors.Unknown;
    stage.style.color = stageColors[r.stage] || stageColors.Unknown;

    const weeklyBadge = node.querySelector(".weekly-badge");
    weeklyBadge.hidden = !changed.has((r.drug || "").toLowerCase());

    const chips = node.querySelector(".chip-row");
    [r.setting, `Signal: ${r.signal}`, r.competitorWatch].forEach((label) => {
      const chip = document.createElement("span");
      chip.className = `chip ${r.signal ? signalClass[r.signal] : ""}`;
      chip.textContent = label;
      chips.appendChild(chip);
    });

    const catalystText = r.nextCatalystDate
      ? `Next catalyst: ${r.nextCatalystDate} (${r.nextCatalystEvent})`
      : `Next catalyst: ${r.nextCatalystEvent}`;
    node.querySelector(".catalyst").textContent = catalystText;

    const priorityRoot = node.querySelector(".priority-trials");
    if (r.priorityTrials && r.priorityTrials.length) {
      const title = document.createElement("h4");
      title.textContent = "Priority trials";
      priorityRoot.appendChild(title);
      r.priorityTrials.forEach((trial) => {
        const row = document.createElement("a");
        row.className = "trial-row";
        row.href = trial.link || "#";
        row.target = "_blank";
        row.rel = "noopener noreferrer";
        row.innerHTML = `
          <strong>${trial.name || "Trial"} <span>${trial.phase || ""}</span></strong>
          <small>${trial.date || "n/a"} | ${trial.event || trial.status || "Catalyst"}</small>
          <small>${trial.nctId || ""}${trial.note ? ` | ${trial.note}` : ""}</small>
        `;
        priorityRoot.appendChild(row);
      });
    }

    const sourceRoot = node.querySelector(".sources");
    (r.sourceLinks || []).slice(0, 3).forEach((s, idx) => {
      const a = document.createElement("a");
      a.href = s;
      a.textContent = `Source ${idx + 1}`;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      sourceRoot.appendChild(a);
    });

    root.appendChild(node);
  });
}

let grid;
function renderGrid() {
  const target = document.getElementById("grid");
  if (grid) {
    grid.destroy();
    target.innerHTML = "";
  }

  grid = new gridjs.Grid({
    search: false,
    pagination: { limit: 8 },
    sort: true,
    columns: ["Drug", "Sponsor", "Stage", "Setting", "Key trial", "Next catalyst", "Signal"],
    data: state.filtered.map((r) => [
      r.drug,
      r.sponsor,
      r.stage,
      r.setting,
      r.keyTrial,
      r.nextCatalystDate || r.nextCatalystEvent,
      r.signal,
    ]),
  });

  grid.render(target);
}

let stageChart;
let modalityChart;
function renderCharts() {
  const stageCounts = aggregate(state.filtered, "stage");
  const modalityCounts = aggregate(state.filtered, "modality");

  if (stageChart) stageChart.destroy();
  if (modalityChart) modalityChart.destroy();

  stageChart = new Chart(document.getElementById("stageChart"), {
    type: "doughnut",
    data: {
      labels: Object.keys(stageCounts),
      datasets: [
        {
          data: Object.values(stageCounts),
          backgroundColor: Object.keys(stageCounts).map((k) => stageColors[k] || stageColors.Unknown),
        },
      ],
    },
    options: { plugins: { legend: { position: "bottom" } } },
  });

  modalityChart = new Chart(document.getElementById("modalityChart"), {
    type: "bar",
    data: {
      labels: Object.keys(modalityCounts),
      datasets: [
        {
          label: "Programs",
          data: Object.values(modalityCounts),
          backgroundColor: "#0069c2",
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
    },
  });
}

function aggregate(records, key) {
  return records.reduce((acc, r) => {
    const k = r[key] || "Unknown";
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
}

function getNearCatalysts(days = 180) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const horizon = new Date(today);
  horizon.setDate(horizon.getDate() + days);

  const items = [];
  state.filtered.forEach((record) => {
    (record.priorityTrials || []).forEach((trial) => {
      items.push({
        drug: record.drug,
        stage: trial.phase || record.stage,
        date: trial.date,
        event: `${trial.name || "Trial"}: ${trial.event || trial.status || "Catalyst"}${trial.nctId ? ` (${trial.nctId})` : ""}`,
        link: trial.link || "",
      });
    });
    if (record.nextCatalystDate) {
      items.push({
        drug: record.drug,
        stage: record.stage,
        date: record.nextCatalystDate,
        event: record.nextCatalystEvent,
        link: (record.sourceLinks || [])[0] || "",
      });
    }
  });

  const seen = new Set();
  return items
    .filter((item) => {
      if (!item.date) return false;
      const d = new Date(item.date);
      if (Number.isNaN(d.getTime()) || d < today || d > horizon) return false;
      const key = `${item.drug}|${item.date}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => new Date(a.date) - new Date(b.date));
}

function renderCatalystCount() {
  document.getElementById("nearCatalystCount").textContent = String(getNearCatalysts(180).length);
}

function renderCatalystList() {
  const target = document.getElementById("nearCatalystList");
  target.innerHTML = "";
  const catalysts = getNearCatalysts(180);

  if (!catalysts.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No catalysts in the next 180 days for current filters.";
    target.appendChild(li);
    return;
  }

  catalysts.slice(0, 8).forEach((r) => {
    const li = document.createElement("li");
    li.textContent = `${r.date} | ${r.drug} (${r.stage}) | ${r.event}`;
    target.appendChild(li);
  });
}

function renderCatalystPlanner() {
  const target = document.getElementById("catalystPlannerList");
  target.innerHTML = "";
  const catalysts = getNearCatalysts(365);

  if (!catalysts.length) {
    target.innerHTML = '<li class="empty">No catalysts in the next 12 months for current filters.</li>';
    return;
  }

  catalysts.forEach((r) => {
    const li = document.createElement("li");
    const linkHtml = r.link ? `<a href="${r.link}" target="_blank" rel="noopener noreferrer">open</a>` : "";
    li.innerHTML = `<strong>${r.date}</strong><span>${r.drug} | ${r.stage}</span><small>${r.event}</small>${linkHtml}`;
    target.appendChild(li);
  });
}

function renderConferences() {
  const root = document.getElementById("conferenceGrid");
  root.innerHTML = "";
  if (!state.conferences.length) {
    root.innerHTML = '<p class="empty">No conference data available.</p>';
    return;
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  state.conferences
    .slice()
    .sort((a, b) => new Date(a.startDate) - new Date(b.startDate))
    .forEach((c) => {
      const start = new Date(c.startDate);
      const days = Math.ceil((start - today) / (1000 * 60 * 60 * 24));
      const card = document.createElement("article");
      card.className = "conference-card";
      card.innerHTML = `
        <h3>${c.name}</h3>
        <p>${c.location || "Location not set"}</p>
        <p>${c.startDate} to ${c.endDate}</p>
        <p class="countdown">${days >= 0 ? `D-${days}` : "In the past"}</p>
        <p>Focus: ${c.focus || "Not set"}</p>
        <p>Watch: ${(c.watchDrugs || []).join(", ") || "Not set"}</p>
        <div class="conference-links"></div>
      `;

      const links = card.querySelector(".conference-links");
      (c.links || []).forEach((link, idx) => {
        const a = document.createElement("a");
        a.href = link;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = `Source ${idx + 1}`;
        links.appendChild(a);
      });

      root.appendChild(card);
    });
}

function buildFeedItems() {
  const intel = state.intel;
  if (!intel || !intel.drugs) {
    state.feedItems = [];
    return;
  }

  const items = [];
  intel.drugs.forEach((drugEntry) => {
    const drug = drugEntry.name;

    (drugEntry.clinicalTrials || []).forEach((trial) => {
      items.push({
        drug,
        type: "trial",
        date: trial.lastUpdate || trial.primaryCompletionDate || trial.completionDate || null,
        title: `${trial.nctId || "NCT"} | ${trial.overallStatus || "Unknown"}`,
        detail: trial.title || "Clinical trial update",
        link: trial.url || "",
      });
    });

    (drugEntry.companyPress || []).forEach((press) => {
      items.push({
        drug,
        type: "press",
        date: press.publishedAt || null,
        title: press.title || "Company press update",
        detail: press.source || "Company press room",
        link: press.link || "",
      });
    });

    (drugEntry.googleNews || []).forEach((news) => {
      items.push({
        drug,
        type: "news",
        date: news.publishedAt || null,
        title: news.title || "News update",
        detail: news.source || "Google News",
        link: news.link || "",
      });
    });
  });

  items.sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  state.feedItems = items;
}

function renderFeed() {
  const root = document.getElementById("feedList");
  root.innerHTML = "";

  if (!state.feedItems.length) {
    root.innerHTML = '<li class="empty">No feed data available yet. Run the intel updater.</li>';
    return;
  }

  const type = document.getElementById("feedType").value;
  const visibleDrugSet = new Set(state.filtered.map((r) => r.drug.toLowerCase()));

  const filtered = state.feedItems.filter((item) => {
    if (type !== "all" && item.type !== type) return false;
    if (!visibleDrugSet.size) return true;
    return visibleDrugSet.has(item.drug.toLowerCase());
  });

  if (!filtered.length) {
    root.innerHTML = '<li class="empty">No feed items match current filters.</li>';
    return;
  }

  filtered.slice(0, 120).forEach((item) => {
    const li = document.createElement("li");
    li.className = `feed-item feed-${item.type}`;
    const date = item.date ? item.date.slice(0, 10) : "n/a";
    const linkHtml = item.link ? `<a href="${item.link}" target="_blank" rel="noopener noreferrer">open</a>` : "";
    li.innerHTML = `<strong>${item.drug}</strong><span>${item.type.toUpperCase()} | ${date}</span><small>${item.title}</small><small>${item.detail}</small>${linkHtml}`;
    root.appendChild(li);
  });
}

function renderWeeklyChanges() {
  const changelog = state.changelog;
  const summary = changelog?.summary || {};
  document.getElementById("changeRunDate").textContent = changelog?.runDate || "n/a";
  document.getElementById("changeTrialCount").textContent = String(summary.trialUpdates || 0);
  document.getElementById("changePressCount").textContent = String(summary.pressUpdates || 0);
  document.getElementById("changeErrorCount").textContent = String(summary.errorGroups || 0);

  renderCardChanges(changelog?.cardChanges || []);
  renderWeeklyItems("trialChangeList", changelog?.trialUpdates || [], "trial");
  renderWeeklyItems("pressChangeList", changelog?.pressUpdates || [], "press");
  renderSourceErrors(changelog?.sourceErrors || []);
}

function renderCardChanges(changes) {
  const root = document.getElementById("cardChangeList");
  root.innerHTML = "";
  if (!changes.length) {
    root.innerHTML = '<li class="empty">No drug card changes were applied in the latest run.</li>';
    return;
  }

  changes.forEach((change) => {
    const li = document.createElement("li");
    li.className = "change-card";
    const title = document.createElement("strong");
    title.textContent = change.drug || "Unknown asset";
    li.appendChild(title);

    const fields = document.createElement("div");
    fields.className = "field-diff-list";
    (change.fields || []).forEach((field) => {
      const row = document.createElement("div");
      row.className = "field-diff";
      const name = document.createElement("span");
      name.textContent = field.field || "field";
      const before = document.createElement("small");
      before.textContent = `Before: ${valueText(field.before)}`;
      const after = document.createElement("small");
      after.textContent = `After: ${valueText(field.after)}`;
      row.append(name, before, after);
      fields.appendChild(row);
    });
    li.appendChild(fields);
    root.appendChild(li);
  });
}

function renderWeeklyItems(id, items, fallbackType) {
  const root = document.getElementById(id);
  root.innerHTML = "";
  if (!items.length) {
    root.innerHTML = '<li class="empty">No updates found in the latest run.</li>';
    return;
  }

  items.slice(0, 80).forEach((item) => {
    const li = document.createElement("li");
    li.className = `feed-item feed-${item.type || fallbackType}`;
    const title = document.createElement("strong");
    title.textContent = item.drug || "Unknown asset";
    const meta = document.createElement("span");
    const date = item.date ? item.date.slice(0, 10) : "n/a";
    const status = item.status ? ` | ${item.status}` : "";
    meta.textContent = `${(item.type || fallbackType).toUpperCase()} | ${date}${status}`;
    const headline = document.createElement("small");
    headline.textContent = item.title || "Untitled update";
    const source = document.createElement("small");
    source.textContent = item.nctId ? `${item.source || "Source"} | ${item.nctId}` : item.source || "Source";
    li.append(title, meta, headline, source);
    appendLink(li, item.link);
    root.appendChild(li);
  });
}

function renderSourceErrors(errors) {
  const root = document.getElementById("sourceErrorList");
  root.innerHTML = "";
  if (!errors.length) {
    root.innerHTML = '<li class="empty">No source errors recorded in the latest run.</li>';
    return;
  }

  errors.forEach((error) => {
    const li = document.createElement("li");
    li.className = "source-error";
    const title = document.createElement("strong");
    title.textContent = `${error.count || 0} asset(s) affected`;
    const message = document.createElement("span");
    message.textContent = error.message || "Unknown source error";
    const example = document.createElement("small");
    example.textContent = `Example asset: ${error.exampleDrug || "n/a"}`;
    li.append(title, message, example);
    root.appendChild(li);
  });
}

load();
