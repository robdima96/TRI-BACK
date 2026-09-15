/** Unit checks for shared TriBackCy presentation kernel (Node). */
const path = require("path");
const assert = require("assert");

const TriBackCy = require(path.join(__dirname, "tri_back_cytoscape.js"));
const DigiMskCy = TriBackCy;

const short = TriBackCy.nodeMetrics("Condition", "Fracture");
const long = TriBackCy.nodeMetrics(
  "Condition",
  "Non-specific Mechanical Cause"
);
assert.ok(long.size > short.size, "long condition should be larger");
assert.ok(long.textMaxWidth > short.textMaxWidth);
assert.ok(long.size >= 90);
assert.strictEqual(DigiMskCy, TriBackCy, "legacy DigiMskCy alias");

const prepared = TriBackCy.prepareElements([
  { data: { id: "c1", label: "Non-specific Mechanical Cause", nodeType: "Condition" } },
  { data: { id: "e1", source: "a", target: "b", label: "RISK_FACTOR_FOR" } },
]);
assert.strictEqual(prepared[0].data.size, long.size);
assert.ok(prepared[0].data.color);
assert.strictEqual(prepared[1].data.source, "a");

const els = TriBackCy.toElements({
  nodes: [{ id: "f1", name: "Age over 50", label: "Factor" }],
  edges: [{ id: "e1", source: "f1", target: "c1", type: "RISK_FACTOR_FOR" }],
});
assert.strictEqual(els.length, 2);
assert.ok(els[0].data.size);
assert.strictEqual(els[1].data.label, "RISK_FACTOR_FOR");

const style = TriBackCy.cytoscapeStyle();
assert.ok(style.some((r) => r.selector === "edge[confirmAgainst = true]"));
assert.ok(style.some((r) => r.selector === "node[askTarget = true]"));
assert.ok(style.some((r) => r.selector === "node[dimmed = true]"));
const edgeRule = style.find((r) => r.selector === "edge");
assert.strictEqual(edgeRule.style["text-rotation"], "autorotate");
assert.strictEqual(edgeRule.style["text-background-opacity"], 0);

console.log("tri_back_cytoscape tests OK");
