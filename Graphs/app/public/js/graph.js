/* global cytoscape, DigiMskCy */

const state = {
  cy: null,
  metadata: null,
  focusNodeId: null,
  nodeIndex: new Map(),
  edgeIndex: new Map(),
};

const CHUNK_PRIORITY_FIELDS = [
  "chunk_string",
  "evidence",
  "evidence_level",
  "edges",
  "path_type",
  "path",
  "is_specific",
  "is_guideline",
  "loc",
  "source_rank",
];

async function ensureAuth() {
  const res = await fetch("/api/auth/status");
  const data = await res.json();
  if (!data.authenticated) {
    window.location.href = "/login.html";
    throw new Error("Not authenticated");
  }
}

function selectedValues(containerId) {
  return [...document.querySelectorAll(`#${containerId} input:checked`)].map(
    (el) => el.value
  );
}

function setAllCheckboxes(containerId, checked) {
  document.querySelectorAll(`#${containerId} input`).forEach((el) => {
    el.checked = checked;
  });
}

function buildFilterMarkup(containerId, items, valueKey, labelFn) {
  const container = document.getElementById(containerId);
  container.innerHTML = items
    .map(
      (item) => `
      <label>
        <input type="checkbox" value="${item[valueKey]}" checked />
        <span>${labelFn(item)}</span>
      </label>
    `
    )
    .join("");
}

function populateNodeSearch(nodes) {
  const datalist = document.getElementById("node-options");
  datalist.innerHTML = nodes
    .map((node) => `<option value="${escapeHtml(node.name)}"></option>`)
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function indexGraphData(graph) {
  state.nodeIndex = new Map(graph.nodes.map((node) => [node.id, node]));
  state.edgeIndex = new Map(graph.edges.map((edge) => [edge.id, edge]));
}

function runLayout(cy) {
  return new Promise((resolve) => {
    const layout = cy.layout({
      name: "cose",
      animate: true,
      animationDuration: 400,
      fit: true,
      padding: 40,
      nodeDimensionsIncludeLabels: true,
      idealEdgeLength: 90,
      nodeRepulsion: 4000,
      gravity: 0.35,
      numIter: 500,
    });
    layout.on("layoutstop", resolve);
    layout.run();
  });
}

async function initCytoscape(elements) {
  if (typeof DigiMskCy === "undefined") {
    throw new Error("DigiMskCy presentation module is not loaded.");
  }
  if (state.cy) {
    state.cy.destroy();
    state.cy = null;
  }

  state.cy = cytoscape({
    container: document.getElementById("cy"),
    elements,
    style: DigiMskCy.cytoscapeStyle({
      edgeWidth: 1.5,
      conditionFontSize: 9,
      baseFontSize: 10,
    }),
    minZoom: 0.08,
    maxZoom: 4,
    wheelSensitivity: 0.18,
    layout: { name: "grid", cols: 12, fit: true, padding: 40 },
  });

  state.cy.on("tap", "node", (event) => {
    event.target.select();
    showNodeDetails(event.target);
  });
  state.cy.on("tap", "edge", (event) => {
    event.target.select();
    showEdgeDetails(event.target);
  });
  state.cy.on("tap", (event) => {
    if (event.target === state.cy) clearSelection();
  });

  await runLayout(state.cy);
}

function showNodeDetails(ele) {
  const node = state.nodeIndex.get(ele.id());
  if (!node) return;

  document.getElementById("legend-empty").hidden = true;
  document.getElementById("legend-content").hidden = false;
  document.getElementById("legend-detail-type").textContent = node.label;
  document.getElementById("legend-detail-title").textContent = node.name;

  const bodyEl = document.getElementById("legend-detail-body");
  const propsEl = document.getElementById("legend-detail-props");

  if (node.label === "Chunk" && node.properties.chunk_string) {
    bodyEl.textContent = node.properties.chunk_string;
    bodyEl.hidden = false;
  } else {
    bodyEl.textContent = describeNodeRole(node.label);
    bodyEl.hidden = false;
  }

  propsEl.innerHTML = buildPropertyList(node);
}

function describeNodeRole(label) {
  if (label === "Factor") {
    return "Clinical symptom, trait, or mediating concept linked to red-flag conditions.";
  }
  if (label === "Condition") {
    return "Red-flag diagnosis that may require urgent triage.";
  }
  return "";
}

function buildPropertyList(node) {
  const props = node.properties || {};
  const keys =
    node.label === "Chunk"
      ? [
          ...CHUNK_PRIORITY_FIELDS.filter((k) => k in props),
          ...Object.keys(props).filter((k) => !CHUNK_PRIORITY_FIELDS.includes(k)),
        ]
      : Object.keys(props);

  const seen = new Set();
  const items = [];
  for (const key of keys) {
    if (seen.has(key)) continue;
    seen.add(key);
    if (key === "chunk_string") continue;
    const value = props[key];
    if (value === "" || value === null || value === undefined) continue;
    items.push(
      `<dt>${escapeHtml(formatKey(key))}</dt><dd>${escapeHtml(String(value))}</dd>`
    );
  }
  return items.join("");
}

function formatKey(key) {
  return key.replaceAll("_", " ");
}

function showEdgeDetails(ele) {
  const edge = state.edgeIndex.get(ele.id());
  if (!edge) return;

  const source = state.nodeIndex.get(edge.source);
  const target = state.nodeIndex.get(edge.target);

  document.getElementById("legend-empty").hidden = true;
  document.getElementById("legend-content").hidden = false;
  document.getElementById("legend-detail-type").textContent = "Relationship";
  document.getElementById("legend-detail-title").textContent = edge.type;

  const bodyEl = document.getElementById("legend-detail-body");
  bodyEl.hidden = false;
  bodyEl.textContent = source && target
    ? `${source.name} → ${target.name}`
    : `${edge.source} → ${edge.target}`;

  const propsEl = document.getElementById("legend-detail-props");
  const items = Object.entries(edge.properties || {})
    .filter(([, value]) => value !== "" && value != null)
    .map(
      ([key, value]) =>
        `<dt>${escapeHtml(formatKey(key))}</dt><dd>${escapeHtml(String(value))}</dd>`
    );
  propsEl.innerHTML = items.join("") || "<dd>(no properties)</dd>";
}

function clearSelection() {
  state.cy?.$(":selected").unselect();
  document.getElementById("legend-empty").hidden = false;
  document.getElementById("legend-content").hidden = true;
}

function setLoading(isLoading, errorMessage = "") {
  document.getElementById("graph-loading").hidden = !isLoading;
  const errorEl = document.getElementById("graph-error");
  if (errorMessage) {
    errorEl.textContent = errorMessage;
    errorEl.hidden = false;
  } else {
    errorEl.hidden = true;
  }
}

async function loadGraph(options = {}) {
  setLoading(true);
  clearSelection();

  const labels = options.labels ?? selectedValues("label-filters");
  const relTypes = options.relTypes ?? selectedValues("rel-filters");
  const focusQuery = (options.focusQuery ?? document.getElementById("node-search").value).trim();

  if (!labels.length) {
    setLoading(false, "Select at least one node type.");
    return;
  }

  const params = new URLSearchParams();
  params.set("labels", labels.join(","));
  if (relTypes.length) params.set("relTypes", relTypes.join(","));
  if (focusQuery) params.set("focusName", focusQuery);

  try {
    const res = await fetch(`/api/graph?${params.toString()}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to load graph");

    indexGraphData(data);
    const elements = DigiMskCy.toElements({
      nodes: data.nodes,
      edges: data.edges,
      options: { truncateChunk: 40 },
    });

    setLoading(false);
    await initCytoscape(elements);

    if (data.mode === "focus" && data.focusNodeId) {
      const focusCyId = [...state.nodeIndex.values()].find(
        (n) => n.elementId === data.focusNodeId
      )?.id;
      if (focusCyId) {
        const focusEle = state.cy.getElementById(focusCyId);
        focusEle.select();
        state.cy.center(focusEle);
      }
    }

    const modeLabel =
      data.mode === "focus"
        ? `focus: ${data.focusName} (${data.focusLabel})`
        : data.mode;
    document.getElementById("graph-mode").textContent = modeLabel;
    document.getElementById("graph-stats").textContent =
      `${data.nodes.length} nodes · ${data.edges.length} relationships`;
  } catch (error) {
    setLoading(false, error.message);
  }
}

async function loadMetadata() {
  const res = await fetch("/api/metadata");
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Failed to load metadata");
  state.metadata = data;

  buildFilterMarkup(
    "label-filters",
    data.nodeLabels,
    "label",
    (item) => `${item.label} <small>(${item.count})</small>`
  );
  buildFilterMarkup(
    "rel-filters",
    data.relationshipTypes,
    "type",
    (item) => `${item.type} <small>(${item.count})</small>`
  );
  populateNodeSearch(data.nodes);
}

function wireControls() {
  document.getElementById("btn-full-graph").addEventListener("click", async () => {
    state.focusNodeId = null;
    document.getElementById("node-search").value = "";
    setAllCheckboxes("label-filters", true);
    setAllCheckboxes("rel-filters", true);
    await loadGraph({ labels: state.metadata.nodeLabels.map((x) => x.label) });
  });

  document.getElementById("btn-apply-filters").addEventListener("click", async () => {
    await loadGraph();
  });

  document.getElementById("btn-clear-filters").addEventListener("click", async () => {
    document.getElementById("node-search").value = "";
    state.focusNodeId = null;
    setAllCheckboxes("label-filters", true);
    setAllCheckboxes("rel-filters", true);
    await loadGraph();
  });

  document.getElementById("btn-fit").addEventListener("click", () => {
    state.cy?.fit(undefined, 40);
  });

  document.getElementById("btn-zoom-in").addEventListener("click", () => {
    state.cy?.zoom(state.cy.zoom() * 1.2);
  });

  document.getElementById("btn-zoom-out").addEventListener("click", () => {
    state.cy?.zoom(state.cy.zoom() / 1.2);
  });

  document.getElementById("btn-logout").addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login.html";
  });
}

async function init() {
  await ensureAuth();
  wireControls();
  await loadMetadata();
  await loadGraph();
}

init().catch((error) => {
  setLoading(false, error.message);
});
