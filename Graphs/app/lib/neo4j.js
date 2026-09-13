const neo4j = require("neo4j-driver");
const config = require("./config");

let driver;

function getDriver() {
  if (!config.neo4j.uri || !config.neo4j.password) {
    throw new Error(
      "Neo4j credentials missing. Set NEO4J_URI and NEO4J_PASSWORD in Graphs/.env"
    );
  }
  if (!driver) {
    driver = neo4j.driver(
      config.neo4j.uri,
      neo4j.auth.basic(config.neo4j.username, config.neo4j.password)
    );
  }
  return driver;
}

async function runQuery(cypher, params = {}) {
  const session = getDriver().session({ database: config.neo4j.database });
  try {
    const result = await session.run(cypher, params);
    return result.records;
  } finally {
    await session.close();
  }
}

async function verifyConnection() {
  const records = await runQuery("RETURN 1 AS ok, count { (n) } AS nodeCount");
  return {
    ok: true,
    database: config.neo4j.database,
    nodeCount: records[0].get("nodeCount").toNumber(),
  };
}

async function closeDriver() {
  if (driver) {
    await driver.close();
    driver = undefined;
  }
}

module.exports = { getDriver, runQuery, verifyConnection, closeDriver };
