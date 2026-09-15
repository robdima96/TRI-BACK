/* Study Arm 3: per-condition GraphRAG traversal panel (orchestration only).
 * Presentation: shared TriBackCy (colors, metrics, stylesheet, prepareElements).
 */
(function () {
  const stateByRoot = new WeakMap();

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function applyHighlight(cy, nodeIds, edgeIds) {
    const nodeSet = new Set(nodeIds || []);
    const edgeSet = new Set(edgeIds || []);
    cy.nodes().forEach((node) => {
      node.data("highlighted", nodeSet.has(node.id()));
      node.data("active", false);
    });
    cy.edges().forEach((edge) => {
      edge.data("highlighted", edgeSet.has(edge.id()));
      edge.data("active", false);
    });
  }

  function applyStepFocus(cy, step) {
    if (!step) return;
    const nodeSet = new Set(step.nodeIds || []);
    const edgeSet = new Set(step.edgeIds || []);
    cy.nodes().forEach((node) => {
      node.data("active", nodeSet.has(node.id()));
    });
    cy.edges().forEach((edge) => {
      edge.data("active", edgeSet.has(edge.id()));
    });
  }

  function mountGraph(container, elements) {
    if (typeof cytoscape === "undefined") {
      container.textContent = "Cytoscape is not loaded.";
      return null;
    }
    const Cy = typeof TriBackCy !== "undefined" ? TriBackCy : (typeof DigiMskCy !== "undefined" ? DigiMskCy : undefined);
    if (typeof Cy === "undefined") {
      container.textContent = "TriBackCy presentation module is not loaded.";
      return null;
    }
    container.innerHTML = "";
    const prepared = Cy.prepareElements(elements || []);
    const cy = cytoscape({
      container,
      elements: prepared,
      style: Cy.cytoscapeStyle(),
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.2,
      layout: { name: "breadthfirst", directed: true, padding: 16 },
    });
    cy.fit(undefined, 20);
    return cy;
  }

  function renderSharedSteps(container, sharedSteps, visible) {
    if (!visible) {
      container.hidden = true;
      container.innerHTML = "";
      return;
    }
    const steps = sharedSteps || [];
    if (!steps.length) {
      container.hidden = true;
      container.innerHTML = "";
      return;
    }
    container.hidden = false;
    container.innerHTML = `
      <ol class="traversal-step-list traversal-shared-list">
        ${steps
          .map(
            (step) =>
              `<li>
                <span class="traversal-step-num">${step.step}</span>
                ${escapeHtml(step.summary || "")}
              </li>`
          )
          .join("")}
      </ol>
    `;
  }

  function viewsFromPayload(payload) {
    if (payload && (Object.prototype.hasOwnProperty.call(payload, "intake") ||
        Object.prototype.hasOwnProperty.call(payload, "disposition"))) {
      const views = [];
      if (payload.intake) {
        views.push({
          key: "intake",
          title: "Question path",
          payload: payload.intake,
          showAllConditions: true,
          showShared: true,
        });
      }
      if (payload.disposition) {
        views.push({
          key: "disposition",
          title: "Why this advice",
          payload: payload.disposition,
          showAllConditions: false,
          showShared: false,
        });
      }
      return views;
    }
    return [
      {
        key: "disposition",
        title: "",
        payload: payload,
        showAllConditions: false,
        showShared: false,
      },
    ];
  }

  function topRankedCondition(conditions) {
    if (!conditions || !conditions.length) return [];
    const sorted = conditions.slice().sort((a, b) => {
      const ra = Number(a.rank);
      const rb = Number(b.rank);
      const rankA = Number.isFinite(ra) ? ra : Number.POSITIVE_INFINITY;
      const rankB = Number.isFinite(rb) ? rb : Number.POSITIVE_INFINITY;
      if (rankA !== rankB) return rankA - rankB;
      return Number(b.riskScore || 0) - Number(a.riskScore || 0);
    });
    return [sorted[0]];
  }

  function renderConditionTabs(tabsEl, conditions, onSelect) {
    tabsEl.innerHTML = conditions
      .map((cond, idx) => {
        const active = idx === 0 ? " active" : "";
        const disabled = onSelect ? "" : " disabled";
        return `
          <button type="button" class="traversal-tab${active}" data-index="${idx}"${disabled}>
            <span class="traversal-tab-rank">#${cond.rank}</span>
            <span class="traversal-tab-name">${escapeHtml(cond.condition)}</span>
            <span class="traversal-tab-score">${Number(cond.riskScore).toFixed(1)}</span>
          </button>
        `;
      })
      .join("");
    if (!onSelect) return;
    tabsEl.querySelectorAll(".traversal-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        const idx = Number(tab.getAttribute("data-index"));
        onSelect(idx);
      });
    });
  }

  function renderConditionSteps(stepsEl, condition, onStepClick) {
    const factorLine =
      condition.supportingFactors && condition.supportingFactors.length
        ? `<p class="traversal-meta">Supporting factors: ${escapeHtml(
            condition.supportingFactors.join(", ")
          )}</p>`
        : "";
    const meta = `
      <p class="traversal-meta">
        Risk score <strong>${Number(condition.riskScore).toFixed(1)}</strong>
        · rank #${condition.rank}
        · ${condition.pathCount || 0} path(s)
      </p>
      ${factorLine}
    `;
    const steps = condition.steps || [];
    const stepItems = steps.length
      ? steps
          .map(
            (step, idx) =>
              `<li><button type="button" class="traversal-step-btn" data-step-index="${idx}">
                <span class="traversal-step-num">${step.step}</span>
                ${escapeHtml(step.summary)}
              </button></li>`
          )
          .join("")
      : `<li class="traversal-muted">No path steps recorded for this condition.</li>`;

    stepsEl.innerHTML = `
      ${meta}
      <ol class="traversal-step-list">${stepItems}</ol>
    `;

    stepsEl.querySelectorAll(".traversal-step-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.getAttribute("data-step-index"));
        onStepClick(idx);
      });
    });
  }

  function selectCondition(root, index) {
    const state = stateByRoot.get(root);
    if (!state || !state.payload.conditions[index]) return;

    state.activeIndex = index;
    const condition = state.payload.conditions[index];

    root.querySelectorAll(".traversal-tab").forEach((tab) => {
      tab.classList.toggle("active", Number(tab.getAttribute("data-index")) === index);
    });

    if (state.cy) {
      state.cy.destroy();
      state.cy = null;
    }
    state.cy = mountGraph(state.graphEl, condition.elements);
    if (state.cy) {
      applyHighlight(
        state.cy,
        (condition.highlight && condition.highlight.nodeIds) || [],
        (condition.highlight && condition.highlight.edgeIds) || []
      );
    }

    renderConditionSteps(state.stepsEl, condition, (stepIdx) => {
      const step = condition.steps[stepIdx];
      if (!state.cy || !step) return;
      applyHighlight(
        state.cy,
        (condition.highlight && condition.highlight.nodeIds) || [],
        (condition.highlight && condition.highlight.edgeIds) || []
      );
      applyStepFocus(state.cy, step);
      state.cy.fit(state.cy.elements().filter("[active = true]"), 30);
    });
  }

  function renderTraversalPanel(root) {
    const raw = root.getAttribute("data-traversal");
    if (!raw) return;

    let payload;
    try {
      payload = JSON.parse(raw);
    } catch (_) {
      root.textContent = "Invalid traversal payload.";
      return;
    }

    const views = viewsFromPayload(payload).filter((view) => {
      const data = view.payload || {};
      return (data.conditions && data.conditions.length) || (data.sharedSteps && data.sharedSteps.length);
    });
    if (!views.length) {
      root.textContent = "No candidate conditions in this traversal.";
      return;
    }

    root.innerHTML = views
      .map(
        (view, viewIdx) => `
      <div class="traversal-panel" data-view="${escapeHtml(view.key)}">
        ${view.title ? `<h3 class="traversal-view-title">${escapeHtml(view.title)}</h3>` : ""}
        <div class="traversal-shared" data-view-index="${viewIdx}"></div>
        <div class="traversal-tabs" data-view-index="${viewIdx}"></div>
        <div class="traversal-body">
          <div class="traversal-graph" data-view-index="${viewIdx}"></div>
          <div class="traversal-steps" data-view-index="${viewIdx}"></div>
        </div>
      </div>
    `
      )
      .join("");

    views.forEach((view, viewIdx) => {
      const panel = root.querySelectorAll(".traversal-panel")[viewIdx];
      if (!panel) return;
      const data = { ...view.payload };
      const conditions = view.showAllConditions
        ? data.conditions || []
        : topRankedCondition(data.conditions || []);
      data.conditions = conditions;

      const sharedEl = panel.querySelector(".traversal-shared");
      const tabsEl = panel.querySelector(".traversal-tabs");
      const graphEl = panel.querySelector(".traversal-graph");
      const stepsEl = panel.querySelector(".traversal-steps");

      renderSharedSteps(sharedEl, data.sharedSteps || [], view.showShared);

      const state = {
        payload: data,
        graphEl,
        stepsEl,
        cy: null,
        activeIndex: 0,
      };
      stateByRoot.set(panel, state);

      if (conditions.length) {
        renderConditionTabs(
          tabsEl,
          conditions,
          view.showAllConditions ? (idx) => selectCondition(panel, idx) : null
        );
        selectCondition(panel, 0);
      } else {
        tabsEl.innerHTML = "";
        graphEl.innerHTML = "";
        stepsEl.innerHTML = `<p class="traversal-muted">No graph paths for this question yet.</p>`;
      }
    });
  }

  function boot() {
    document.querySelectorAll(".traversal-debug[data-traversal]").forEach((el) => {
      if (el.getAttribute("data-rendered") === "1") return;
      el.setAttribute("data-rendered", "1");
      renderTraversalPanel(el);
    });

    document.querySelectorAll(".graph-block[data-graph]").forEach((el) => {
      if (el.getAttribute("data-rendered") === "1") return;
      el.setAttribute("data-rendered", "1");
      const wrapper = document.createElement("div");
      wrapper.className = "traversal-debug";
      wrapper.setAttribute("data-traversal", el.getAttribute("data-graph") || "");
      el.replaceWith(wrapper);
      renderTraversalPanel(wrapper);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  const obs = new MutationObserver(boot);
  obs.observe(document.body, { childList: true, subtree: true });
})();
