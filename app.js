const stageColors = {
  Approved: "#0f6d55",
  "Phase III": "#0069c2",
  "Phase II": "#4f7bc8",
  "Phase I": "#6b5ac7",
  "Preclinical": "#9e6a00",
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
};

async function load() {
  const res = await fetch("data/acs-drugs.json");
  const data = await res.json();
  state.records = data.records;
  state.filtered = [...state.records];

  document.getElementById("snapshotDate").textContent = data.snapshotDate;
  document.getElementById("recordCount").textContent = String(state.records.length);

  seedFilter("stageFilter", unique(state.records.map((r) => r.stage)));
  seedFilter("settingFilter", unique(state.records.map((r) => r.setting)));

  bindFilters();
  applyFilters();
}

function unique(values) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
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
    r.sourceLinks.slice(0, 3).forEach((s, idx) => {
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
    columns: [
      "Drug",
      "Sponsor",
      "Stage",
      "Setting",
      "Key trial",
      "Next catalyst",
      "Signal",
    ],
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
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
}

function aggregate(records, key) {
  return records.reduce((acc, r) => {
    acc[r[key]] = (acc[r[key]] || 0) + 1;
    return acc;
  }, {});
}

function renderCatalystCount() {
  document.getElementById("nearCatalystCount").textContent = String(getNearCatalysts().length);
}

function getNearCatalysts() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const horizon = new Date(today);
  horizon.setDate(horizon.getDate() + 180);

  return state.filtered
    .filter((r) => {
      if (!r.nextCatalystDate) return false;
      const d = new Date(r.nextCatalystDate);
      return !Number.isNaN(d.getTime()) && d >= today && d <= horizon;
    })
    .sort((a, b) => new Date(a.nextCatalystDate) - new Date(b.nextCatalystDate));
}

function renderCatalystList() {
  const target = document.getElementById("nearCatalystList");
  target.innerHTML = "";
  const catalysts = getNearCatalysts();

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

load();
