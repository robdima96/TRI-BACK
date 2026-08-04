(() => {
  const chartEl = document.getElementById("chart-data");
  if (chartEl) {
    let payload = { labels: [], round_trip_ms: [], user_words: [], idle_before_turn_sec: [] };
    try {
      payload = JSON.parse(chartEl.textContent || "{}");
    } catch (_) {
      /* ignore */
    }
    const labels = payload.labels || [];
    if (labels.length && window.Chart) {
      const ink = "#1c1b19";
      const muted = "#5c574f";
      const green = "#0b6e4f";
      const blue = "#1f3a5f";

      const rtt = document.getElementById("chart-rtt");
      if (rtt) {
        new Chart(rtt, {
          type: "bar",
          data: {
            labels,
            datasets: [
              {
                label: "round_trip_ms",
                data: payload.round_trip_ms || [],
                backgroundColor: green,
                borderRadius: 6,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { ticks: { color: muted }, grid: { display: false } },
              y: { ticks: { color: muted }, grid: { color: "#e8e2d8" } },
            },
          },
        });
      }

      const words = document.getElementById("chart-words");
      if (words) {
        new Chart(words, {
          type: "line",
          data: {
            labels,
            datasets: [
              {
                label: "user words",
                data: payload.user_words || [],
                borderColor: blue,
                backgroundColor: "rgba(31,58,95,0.12)",
                tension: 0.25,
                yAxisID: "y",
              },
              {
                label: "idle sec",
                data: payload.idle_before_turn_sec || [],
                borderColor: "#9a4d0a",
                backgroundColor: "rgba(154,77,10,0.1)",
                tension: 0.25,
                yAxisID: "y1",
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: ink } } },
            scales: {
              x: { ticks: { color: muted }, grid: { display: false } },
              y: {
                position: "left",
                ticks: { color: muted },
                grid: { color: "#e8e2d8" },
                title: { display: true, text: "words", color: muted },
              },
              y1: {
                position: "right",
                ticks: { color: muted },
                grid: { drawOnChartArea: false },
                title: { display: true, text: "idle (s)", color: muted },
              },
            },
          },
        });
      }
    }
  }

  const popup = document.getElementById("turn-popup");
  if (!popup) return;

  function esc(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function itemList(items) {
    if (!items || !items.length) {
      return '<p class="empty">None logged for this turn.</p>';
    }
    return (
      "<ul>" +
      items
        .map((it) => {
          const text = esc(it.text || "");
          const meta = esc([it.kind, it.label, it.source].filter(Boolean).join(" · "));
          return `<li><strong>${text}</strong><br/><span style="color:#5c574f;font-size:0.8rem">${meta}</span></li>`;
        })
        .join("") +
      "</ul>"
    );
  }

  function coverageHtml(orch) {
    if (!orch) {
      return '<p class="empty">No orchestrator / coverage snapshot for this turn.</p>';
    }
    const cov = orch.coverage || {};
    const ready = Boolean(cov.ready_for_disposition ?? orch.coverage_ready);
    const missing = cov.missing_slots || [];
    const missingText = missing.length
      ? missing
          .map((m) => (typeof m === "string" ? m : m.slot || JSON.stringify(m)))
          .join(", ")
      : "none";
    const cls = ready ? "coverage-box" : "coverage-box incomplete";
    return `
      <div class="${cls}">
        <div><strong>ready_for_disposition:</strong> ${esc(ready)}</div>
        <div><strong>question_mode:</strong> ${esc(orch.question_mode)}</div>
        <div><strong>slot_being_asked:</strong> ${esc(orch.slot_being_asked ?? "—")}</div>
        <div><strong>questions_asked:</strong> ${esc(orch.questions_asked ?? "—")}</div>
        <div><strong>missing_slots:</strong> ${esc(missingText)}</div>
        <div><strong>escalated:</strong> ${esc(orch.escalated)}</div>
        ${orch.safety_reason ? `<div><strong>safety_reason:</strong> ${esc(orch.safety_reason)}</div>` : ""}
      </div>
    `;
  }

  function renderPopup(turn) {
    const extraction = turn.extraction || {};
    const newItems = extraction.new_items || [];
    const bySource = extraction.by_source || {};
    const eng = turn.engagement || {};
    popup.innerHTML = `
      <h4>Turn ${esc(turn.turn_index)}</h4>
      <h5>Checklist items added</h5>
      ${itemList(newItems)}
      <h5>By source</h5>
      ${
        Object.keys(bySource).length
          ? Object.entries(bySource)
              .map(
                ([src, rows]) =>
                  `<div style="margin-bottom:6px"><strong>${esc(src)}</strong> (${(rows || []).length})</div>${itemList(rows || [])}`
              )
              .join("")
          : '<p class="empty">No by_source breakdown.</p>'
      }
      <h5>Coverage / orchestrator</h5>
      ${coverageHtml(turn.orchestrator)}
      <h5>Engagement (this turn)</h5>
      ${
        eng && Object.keys(eng).length
          ? `<div class="coverage-box">
              <div>words: ${esc(eng.user_word_count ?? "—")}</div>
              <div>round_trip_ms: ${esc(eng.round_trip_ms ?? "—")}</div>
              <div>idle_before_turn_sec: ${esc(eng.idle_before_turn_sec ?? "—")}</div>
            </div>`
          : '<p class="empty">No engagement row.</p>'
      }
    `;
  }

  function placePopup(clientX, clientY) {
    const pad = 14;
    popup.classList.add("visible");
    popup.setAttribute("aria-hidden", "false");
    const rect = popup.getBoundingClientRect();
    let left = clientX + 16;
    let top = clientY + 16;
    if (left + rect.width > window.innerWidth - pad) {
      left = clientX - rect.width - 16;
    }
    if (top + rect.height > window.innerHeight - pad) {
      top = window.innerHeight - rect.height - pad;
    }
    left = Math.max(pad, left);
    top = Math.max(pad, top);
    popup.style.left = `${left}px`;
    popup.style.top = `${top}px`;
  }

  document.querySelectorAll("[data-turn-popup]").forEach((el) => {
    let turn;
    try {
      turn = JSON.parse(el.getAttribute("data-turn") || "{}");
    } catch (_) {
      turn = {};
    }
    el.addEventListener("mouseenter", (ev) => {
      renderPopup(turn);
      placePopup(ev.clientX, ev.clientY);
    });
    el.addEventListener("mousemove", (ev) => placePopup(ev.clientX, ev.clientY));
    el.addEventListener("mouseleave", () => {
      popup.classList.remove("visible");
      popup.setAttribute("aria-hidden", "true");
    });
  });
})();
