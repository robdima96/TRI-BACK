/**
 * DigiMSK shared Cytoscape presentation kernel.
 *
 * Style, colors, label→size metrics, and element mapping only.
 * Study Arm 3 orchestration and Neo4j explorer chrome stay in their apps.
 *
 * Source of truth: shared/digimsk_cytoscape/digimsk_cytoscape.js
 * Sync copies into study assets + Graphs/app public via scripts/sync_digimsk_cytoscape.py
 *
 * Global: window.DigiMskCy
 */
(function (global) {
  "use strict";

  const NODE_COLORS = {
    Factor: { background: "#2563eb", border: "#1d4ed8", text: "#ffffff" },
    Condition: { background: "#1e40af", border: "#1e3a8a", text: "#ffffff" },
    Chunk: { background: "#dbeafe", border: "#60a5fa", text: "#1e3a8a" },
  };

  /**
   * @param {string} nodeType Factor | Condition | Chunk
   * @param {string} name Display label
   * @returns {{ size: number, textMaxWidth: number }}
   */
  function nodeMetrics(nodeType, name) {
    const text = String(name || nodeType || "").trim() || String(nodeType || "Node");
    const n = text.length;
    if (nodeType === "Chunk") {
      return { size: 44, textMaxWidth: 40 };
    }
    let base;
    let perChar;
    let minS;
    let maxS;
    let widthRatio;
    if (nodeType === "Condition") {
      base = 56;
      perChar = 2.2;
      minS = 56;
      maxS = 120;
      widthRatio = 0.58;
    } else {
      base = 44;
      perChar = 1.8;
      minS = 42;
      maxS = 100;
      widthRatio = 0.72;
    }
    let size = Math.round(base + Math.max(0, n - 8) * perChar);
    size = Math.max(minS, Math.min(maxS, size));
    const textMaxWidth = Math.max(36, Math.round(size * widthRatio));
    return { size, textMaxWidth };
  }

  function colorsFor(nodeType) {
    return NODE_COLORS[nodeType] || NODE_COLORS.Factor;
  }

  /**
   * Cytoscape stylesheet shared by study Arm 3 and the Neo4j explorer.
   * @param {{ edgeWidth?: number, conditionFontSize?: number, baseFontSize?: number }} [opts]
   */
  function cytoscapeStyle(opts) {
    const edgeWidth = (opts && opts.edgeWidth) || 2;
    const conditionFontSize = (opts && opts.conditionFontSize) || 8;
    const baseFontSize = (opts && opts.baseFontSize) || 9;
    return [
      {
        selector: "node",
        style: {
          label: "data(label)",
          "text-valign": "center",
          "text-halign": "center",
          "text-margin-x": 0,
          "text-margin-y": 0,
          "text-justification": "center",
          "text-wrap": "wrap",
          "text-max-width": "data(textMaxWidth)",
          "font-size": baseFontSize,
          "font-weight": 600,
          "line-height": 1.1,
          "background-color": "data(color)",
          "border-color": "data(borderColor)",
          "border-width": 2,
          color: "data(textColor)",
          width: "data(size)",
          height: "data(size)",
        },
      },
      {
        selector: "node[nodeType = 'Chunk']",
        style: {
          shape: "round-rectangle",
          width: "data(size)",
          height: "data(size)",
          "font-size": 8,
          "text-max-width": "data(textMaxWidth)",
        },
      },
      {
        selector: "node[nodeType = 'Condition']",
        style: {
          shape: "diamond",
          width: "data(size)",
          height: "data(size)",
          "font-size": conditionFontSize,
          "text-max-width": "data(textMaxWidth)",
        },
      },
      {
        selector: "node:selected",
        style: { "border-width": 4, "border-color": "#0f172a" },
      },
      {
        selector: "edge",
        style: {
          width: edgeWidth,
          "line-color": "#94a3b8",
          "target-arrow-color": "#94a3b8",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          "font-size": 8,
          color: "#334155",
          "text-rotation": "autorotate",
          "text-margin-y": -6,
          "text-wrap": "none",
          "text-background-opacity": 0,
          "text-outline-width": 0,
        },
      },
      {
        selector: "edge:selected",
        style: {
          width: Math.max(3, edgeWidth + 1),
          "line-color": "#1d4ed8",
          "target-arrow-color": "#1d4ed8",
          color: "#1e40af",
        },
      },
      {
        selector: "node[highlighted = true]",
        style: { "border-width": 4, "border-color": "#f59e0b" },
      },
      {
        selector: "edge[highlighted = true]",
        style: { width: 4, "line-color": "#f59e0b" },
      },
      {
        selector: "node[active = true]",
        style: { "border-width": 5, "border-color": "#0f172a" },
      },
      {
        selector: "edge[active = true]",
        style: {
          width: 5,
          "line-color": "#1d4ed8",
          "target-arrow-color": "#1d4ed8",
        },
      },
    ];
  }

  function truncate(text, max) {
    const s = String(text || "");
    if (s.length <= max) return s;
    return `${s.slice(0, max - 1)}…`;
  }

  /**
   * Build Cytoscape elements from a neutral graph schema.
   * @param {{ nodes: Array<{id:string,name:string,label:string}>, edges: Array<{id:string,source:string,target:string,type:string}>, options?: { truncateChunk?: number } }} graph
   */
  function toElements(graph) {
    const nodesIn = (graph && graph.nodes) || [];
    const edgesIn = (graph && graph.edges) || [];
    const truncateChunk =
      graph && graph.options && graph.options.truncateChunk != null
        ? graph.options.truncateChunk
        : 40;

    const nodes = nodesIn.map((node) => {
      const nodeType = node.label || "Factor";
      const displayLabel =
        nodeType === "Chunk" ? truncate(node.name, truncateChunk) : node.name;
      const metrics = nodeMetrics(nodeType, displayLabel);
      const colors = colorsFor(nodeType);
      return {
        data: {
          id: node.id,
          label: displayLabel,
          fullLabel: node.name,
          nodeType,
          color: colors.background,
          borderColor: colors.border,
          textColor: colors.text,
          size: metrics.size,
          textMaxWidth: metrics.textMaxWidth,
        },
      };
    });

    const edges = edgesIn.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.type,
        edgeType: edge.type,
      },
    }));

    return nodes.concat(edges);
  }

  /**
   * Enrich study/traversal Cytoscape elements that already have
   * data.label + data.nodeType (and optional highlight flags).
   * Fills colors, size, and textMaxWidth from the shared metrics.
   */
  function prepareElements(elements) {
    const list = elements || [];
    return list.map((el) => {
      const data = (el && el.data) || {};
      if (data.source && data.target) {
        return el;
      }
      const nodeType = data.nodeType || "Factor";
      const name = data.label || data.fullLabel || nodeType;
      const metrics = nodeMetrics(nodeType, name);
      const colors = colorsFor(nodeType);
      return {
        ...el,
        data: {
          ...data,
          color: colors.background,
          borderColor: colors.border,
          textColor: colors.text,
          size: metrics.size,
          textMaxWidth: metrics.textMaxWidth,
        },
      };
    });
  }

  const api = {
    NODE_COLORS,
    nodeMetrics,
    colorsFor,
    cytoscapeStyle,
    toElements,
    prepareElements,
    truncate,
  };

  global.DigiMskCy = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
