const { runQuery } = require("./neo4j");

const NODE_LABELS = ["Factor", "Condition", "Chunk"];

function safeElementId(elementId) {
  return `n_${String(elementId).replace(/[^a-zA-Z0-9]/g, "_")}`;
}

function serializeValue(value) {
  if (value === null || value === undefined) return value;
  if (typeof value === "object" && typeof value.toNumber === "function") {
    return value.toNumber();
  }
  if (typeof value === "object" && value.constructor?.name === "Date") {
    return value.toISOString();
  }
  return value;
}

function serializeProperties(props) {
  const out = {};
  for (const [key, value] of Object.entries(props || {})) {
    out[key] = serializeValue(value);
  }
  return out;
}

function primaryLabel(node) {
  const labels = node.labels || [];
  if (labels.includes("Condition")) return "Condition";
  if (labels.includes("Chunk")) return "Chunk";
  if (labels.includes("Factor")) return "Factor";
  return labels[0] || "Node";
}

function nodeDisplayName(node) {
  const props = node.properties || {};
  return props.name || props.chunk_id || primaryLabel(node);
}

function nodeToJson(node) {
  const label = primaryLabel(node);
  const elementId = node.elementId;
  return {
    id: safeElementId(elementId),
    elementId,
    label,
    name: nodeDisplayName(node),
    properties: serializeProperties(node.properties),
  };
}

function relToJson(rel) {
  return {
    id: safeElementId(rel.elementId),
    elementId: rel.elementId,
    type: rel.type,
    source: safeElementId(rel.startNodeElementId),
    target: safeElementId(rel.endNodeElementId),
    sourceElementId: rel.startNodeElementId,
    targetElementId: rel.endNodeElementId,
    properties: serializeProperties(rel.properties),
  };
}

function buildElements(nodes, rels) {
  const nodeMap = new Map();
  for (const node of nodes) {
    if (!node) continue;
    nodeMap.set(node.elementId, nodeToJson(node));
  }
  const edges = [];
  const edgeIds = new Set();
  for (const rel of rels) {
    if (!rel) continue;
    if (edgeIds.has(rel.elementId)) continue;
    edgeIds.add(rel.elementId);
    edges.push(relToJson(rel));
  }
  return { nodes: [...nodeMap.values()], edges };
}

function pruneToFocusComponent(focusElementId, nodes, rels) {
  const adj = new Map();
  for (const rel of rels) {
    const a = rel.startNodeElementId;
    const b = rel.endNodeElementId;
    if (!adj.has(a)) adj.set(a, new Set());
    if (!adj.has(b)) adj.set(b, new Set());
    adj.get(a).add(b);
    adj.get(b).add(a);
  }

  const seen = new Set([focusElementId]);
  const queue = [focusElementId];
  while (queue.length) {
    const current = queue.shift();
    for (const next of adj.get(current) || []) {
      if (!seen.has(next)) {
        seen.add(next);
        queue.push(next);
      }
    }
  }

  return {
    nodes: nodes.filter((n) => seen.has(n.elementId)),
    rels: rels.filter(
      (r) =>
        seen.has(r.startNodeElementId) && seen.has(r.endNodeElementId)
    ),
  };
}

async function resolveFocusNode({ focusNodeId, focusName }) {
  if (focusNodeId) {
    const rows = await runQuery(
      `
      MATCH (n)
      WHERE elementId(n) = $focusNodeId
      RETURN elementId(n) AS id, coalesce(n.name, n.chunk_id) AS name, labels(n) AS labels
      LIMIT 1
      `,
      { focusNodeId }
    );
    if (rows.length) {
      return {
        elementId: rows[0].get("id"),
        name: rows[0].get("name"),
        labels: rows[0].get("labels"),
      };
    }
  }

  const query = (focusName || "").trim();
  if (!query) {
    throw new Error("Focus node not found. Enter a Factor, Condition, or Chunk name.");
  }

  const rows = await runQuery(
    `
    MATCH (n)
    WHERE (n:Factor OR n:Condition OR n:Chunk)
      AND (
        toLower(coalesce(n.name, n.chunk_id, '')) = toLower($query)
        OR toLower(coalesce(n.name, n.chunk_id, '')) STARTS WITH toLower($query)
        OR toLower(coalesce(n.name, n.chunk_id, '')) CONTAINS toLower($query)
      )
    RETURN elementId(n) AS id, coalesce(n.name, n.chunk_id) AS name, labels(n) AS labels
    ORDER BY
      CASE
        WHEN toLower(coalesce(n.name, n.chunk_id, '')) = toLower($query) THEN 0
        WHEN toLower(coalesce(n.name, n.chunk_id, '')) STARTS WITH toLower($query) THEN 1
        ELSE 2
      END,
      size(coalesce(n.name, n.chunk_id, ''))
    LIMIT 1
    `,
    { query }
  );

  if (!rows.length) {
    throw new Error(`No node matching "${query}". Try AAA, Fracture, Fever, etc.`);
  }

  return {
    elementId: rows[0].get("id"),
    name: rows[0].get("name"),
    labels: rows[0].get("labels"),
  };
}

async function fetchMetadata() {
  const labelRows = await runQuery(
    `
    MATCH (n)
    WHERE n:Factor OR n:Condition OR n:Chunk
    UNWIND labels(n) AS label
    WITH label
    WHERE label IN $labels
    RETURN label, count(*) AS count
    ORDER BY label
    `,
    { labels: NODE_LABELS }
  );

  const relRows = await runQuery(
    `
    MATCH ()-[r]->()
    RETURN DISTINCT type(r) AS type, count(r) AS count
    ORDER BY type
    `
  );

  const nodeListRows = await runQuery(
    `
    MATCH (n)
    WHERE n:Factor OR n:Condition OR n:Chunk
    RETURN
      elementId(n) AS id,
      labels(n) AS labels,
      coalesce(n.name, n.chunk_id, head(labels(n))) AS name
    ORDER BY name
    `
  );

  return {
    nodeLabels: labelRows.map((row) => ({
      label: row.get("label"),
      count: row.get("count").toNumber(),
    })),
    relationshipTypes: relRows.map((row) => ({
      type: row.get("type"),
      count: row.get("count").toNumber(),
    })),
    nodes: nodeListRows.map((row) => {
      const labels = row.get("labels");
      const elementId = row.get("id");
      return {
        id: safeElementId(elementId),
        elementId,
        labels,
        name: row.get("name"),
        label: primaryLabel({ labels }),
      };
    }),
  };
}

async function fetchGraph({ labels, relTypes, focusNodeId, focusName }) {
  const activeLabels =
    labels && labels.length ? labels.filter((l) => NODE_LABELS.includes(l)) : NODE_LABELS;
  const activeRelTypes = relTypes && relTypes.length ? relTypes : null;

  if (focusNodeId || focusName) {
    return fetchFocusSubgraph({
      focusNodeId,
      focusName,
      labels: activeLabels,
      relTypes: activeRelTypes,
    });
  }

  if (!activeLabels.length) {
    return { mode: "filtered", nodes: [], edges: [] };
  }

  const params = { labels: activeLabels, relTypes: activeRelTypes };
  let relFilter = "AND ($relTypes IS NULL OR type(r) IN $relTypes)";

  const cypher = `
    MATCH (n)
    WHERE any(l IN labels(n) WHERE l IN $labels)
    OPTIONAL MATCH (n)-[r]->(m)
    WHERE m IS NOT NULL
      AND any(l IN labels(m) WHERE l IN $labels)
      ${relFilter}
    WITH collect(DISTINCT n) AS nodeList, collect(DISTINCT r) AS relList
    RETURN nodeList AS nodes, [x IN relList WHERE x IS NOT NULL] AS rels
  `;

  const records = await runQuery(cypher, params);
  const nodes = records[0]?.get("nodes") || [];
  const rels = records[0]?.get("rels") || [];

  return {
    mode: activeRelTypes || (labels && labels.length) ? "filtered" : "full",
    ...buildElements(nodes, rels),
  };
}

async function fetchFocusSubgraph({ focusNodeId, focusName, labels, relTypes }) {
  const focus = await resolveFocusNode({ focusNodeId, focusName });
  const params = {
    focusNodeId: focus.elementId,
    labels,
    relTypes,
  };

  const cypher = `
    MATCH (focus)
    WHERE elementId(focus) = $focusNodeId

    OPTIONAL MATCH (focus)-[r1]-(n1)
    WHERE n1 <> focus
      AND any(l IN labels(n1) WHERE l IN $labels)
      AND ($relTypes IS NULL OR type(r1) IN $relTypes)

    OPTIONAL MATCH (n2)-[r2]-(mid:Factor)-[r3]-(focus)
    WHERE focus:Condition
      AND n2 <> focus AND mid <> focus
      AND any(l IN labels(n2) WHERE l IN $labels)
      AND any(l IN labels(mid) WHERE l IN $labels)
      AND ($relTypes IS NULL OR type(r2) IN $relTypes)
      AND ($relTypes IS NULL OR type(r3) IN $relTypes)

    OPTIONAL MATCH (chunk:Chunk)-[r4:DESCRIBES]-(fac:Factor)-[r5]-(focus)
    WHERE chunk <> focus AND fac <> focus
      AND 'Chunk' IN $labels
      AND any(l IN labels(fac) WHERE l IN $labels)
      AND ($relTypes IS NULL OR type(r4) IN $relTypes)
      AND ($relTypes IS NULL OR type(r5) IN $relTypes)

    WITH focus,
      collect(DISTINCT n1) + collect(DISTINCT n2) + collect(DISTINCT mid)
        + collect(DISTINCT chunk) + collect(DISTINCT fac) AS neighbors,
      collect(DISTINCT r1) + collect(DISTINCT r2) + collect(DISTINCT r3)
        + collect(DISTINCT r4) + collect(DISTINCT r5) AS rels

    RETURN [focus] + [n IN neighbors WHERE n IS NOT NULL] AS nodes,
      [r IN rels WHERE r IS NOT NULL] AS rels
  `;

  const records = await runQuery(cypher, params);
  let nodes = records[0]?.get("nodes") || [];
  let rels = records[0]?.get("rels") || [];

  const pruned = pruneToFocusComponent(focus.elementId, nodes, rels);

  return {
    mode: "focus",
    focusNodeId: focus.elementId,
    focusName: focus.name,
    focusLabel: primaryLabel({ labels: focus.labels }),
    ...buildElements(pruned.nodes, pruned.rels),
  };
}

module.exports = {
  NODE_LABELS,
  safeElementId,
  resolveFocusNode,
  fetchMetadata,
  fetchGraph,
};
