const path = require("path");
const dotenv = require("dotenv");

const APP_DIR = path.resolve(__dirname, "..");
const GRAPHS_DIR = path.resolve(APP_DIR, "..");

dotenv.config({ path: path.join(APP_DIR, ".env") });
dotenv.config({ path: path.join(GRAPHS_DIR, ".env"), override: false });

function normalizeUri(uri) {
  const trimmed = (uri || "").trim();
  if (!trimmed) return "";
  if (!trimmed.includes("://")) {
    const instanceId = trimmed.split("/")[0].split(":")[0];
    return `neo4j+s://${instanceId}.databases.neo4j.io`;
  }
  return trimmed;
}

function resolveDatabase(uri, username, explicit) {
  if (explicit && explicit.trim()) return explicit.trim();
  if (uri.includes(".databases.neo4j.io")) {
    const host = uri.split("://")[1].split("/")[0].split(":")[0];
    const instanceId = host.split(".")[0];
    if (instanceId) return instanceId;
  }
  if (username && username !== "neo4j") return username;
  return "neo4j";
}

const uri = normalizeUri(process.env.NEO4J_URI);
const username = (process.env.NEO4J_USERNAME || "neo4j").trim();
const password = (process.env.NEO4J_PASSWORD || "").trim();
const database = resolveDatabase(uri, username, process.env.NEO4J_DATABASE || "");

module.exports = {
  appDir: APP_DIR,
  graphsDir: GRAPHS_DIR,
  port: Number(process.env.PORT || 3847),
  appPassword: (process.env.APP_PASSWORD || "").trim(),
  sessionSecret: (process.env.SESSION_SECRET || "digimsk-graph-dev-secret").trim(),
  neo4j: { uri, username, password, database },
  graphVersion: "red flags/v1",
};
