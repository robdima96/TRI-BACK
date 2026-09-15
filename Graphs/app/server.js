const path = require("path");
const express = require("express");
const session = require("express-session");
const config = require("./lib/config");
const { verifyConnection, closeDriver } = require("./lib/neo4j");
const { fetchMetadata, fetchGraph } = require("./lib/graphApi");

const app = express();

app.use(express.json());
app.use(
  session({
    name: "tri_back.graph.sid",
    secret: config.sessionSecret,
    resave: false,
    saveUninitialized: false,
    cookie: {
      httpOnly: true,
      sameSite: "lax",
      maxAge: 12 * 60 * 60 * 1000,
    },
  })
);

function requireAuth(req, res, next) {
  if (req.session?.authenticated) return next();
  if (req.path.startsWith("/api/")) {
    return res.status(401).json({ error: "Authentication required" });
  }
  return res.redirect("/login.html");
}

app.post("/api/auth/login", (req, res) => {
  const password = (req.body?.password || "").trim();
  if (!config.appPassword) {
    return res.status(500).json({
      error: "APP_PASSWORD is not configured. Set it in Graphs/app/.env",
    });
  }
  if (password !== config.appPassword) {
    return res.status(401).json({ error: "Invalid password" });
  }
  req.session.authenticated = true;
  res.json({ ok: true });
});

app.post("/api/auth/logout", (req, res) => {
  req.session.destroy(() => {
    res.json({ ok: true });
  });
});

app.get("/api/auth/status", (req, res) => {
  res.json({ authenticated: Boolean(req.session?.authenticated) });
});

app.get("/api/health", async (_req, res) => {
  try {
    const status = await verifyConnection();
    res.json({ ok: true, graphVersion: config.graphVersion, ...status });
  } catch (err) {
    res.status(503).json({ ok: false, error: err.message });
  }
});

app.get("/api/metadata", requireAuth, async (_req, res) => {
  try {
    const metadata = await fetchMetadata();
    res.json(metadata);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/graph", requireAuth, async (req, res) => {
  try {
    const labels = parseList(req.query.labels);
    const relTypes = parseList(req.query.relTypes);
    const focusNodeId = (req.query.focusNodeId || "").trim() || null;
    const focusName = (req.query.focusName || "").trim() || null;

    const graph = await fetchGraph({ labels, relTypes, focusNodeId, focusName });
    res.json(graph);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

function parseList(value) {
  if (!value) return [];
  return String(value)
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

app.get("/index.html", requireAuth, (_req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

app.use(express.static(path.join(__dirname, "public"), { index: false }));

app.get("/", requireAuth, (_req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

app.listen(config.port, async () => {
  console.log(`TRI-BACK Graph Explorer: http://localhost:${config.port}`);
  if (!config.appPassword) {
    console.warn("WARNING: APP_PASSWORD is not set. Copy .env.example to .env");
  }
  try {
    const status = await verifyConnection();
    console.log(
      `Neo4j connected (${status.database}) — ${status.nodeCount} nodes in database`
    );
  } catch (err) {
    console.warn(`Neo4j connection check failed: ${err.message}`);
  }
});

process.on("SIGINT", async () => {
  await closeDriver();
  process.exit(0);
});
