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
  feedItems: [],
};

async function load() {
  const [portfolioData, conferencesData, intelData] = await Promise.all([
    fetchJson("data/acs-drugs.json"),
    fetchJson("data/conferences.json", { conferences: [] }),
    fetchJson("reports/latest.json", null),
  ]);

  state.records = portfolioData.records || [];
  state.filtered = [...state.records];
  state.conferences = conferencesData.conferences || [];
  state.intel = intelData;

  document.getElementById("snapshotDate").textContent = portfolioData.snapshotDate || "n/a";
  document.getElementById("recordCount").textContent = String(state.records.length);

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
      [r.drug, r.sponsor, r.class, r.target, r.keyTrial, r.statusSummary]
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
}

function renderCards() {
  const root = document.getElementById("cards");
  root.innerHTML = "";
  const template = document.getElementById("cardTemplate");

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

  return state.filtered
    .filter((r) => {
      if (!r.nextCatalystDate) return false;
      const d = new Date(r.nextCatalystDate);
      return !Number.isNaN(d.getTime()) && d >= today && d <= horizon;
    })
    .sort((a, b) => new Date(a.nextCatalystDate) - new Date(b.nextCatalystDate));
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
    li.textContent = `${r.nextCatalystDate} | ${r.drug} (${r.stage}) | ${r.nextCatalystEvent}`;
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
    li.innerHTML = `<strong>${r.nextCatalystDate}</strong><span>${r.drug} | ${r.stage}</span><small>${r.nextCatalystEvent}</small>`;
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

load();
