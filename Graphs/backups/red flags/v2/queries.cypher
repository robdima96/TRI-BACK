// TRI-BACK Red Flags knowledge graph — starter queries for Neo4j Browser / Bloom

// Backup: red flags v1



// --- Overview: condition hub (symptoms linked to each diagnosis) ---

MATCH (f:Factor)-[r]->(c:Condition)

RETURN c, r, f

LIMIT 200;



// --- Full graph around vertebral fracture ---

MATCH path = (f:Factor)-[*1..2]-(c:Condition {name: 'Fracture'})

RETURN path

LIMIT 100;



// --- Evidence chunks for a condition ---

MATCH (ch:Chunk)-[:APPLIES_TO]->(c:Condition {name: 'CES'})

MATCH (ch)-[:DESCRIBES]->(f:Factor)

RETURN ch.chunk_id, f.name, ch.is_specific, ch.chunk_string

ORDER BY ch.is_specific DESC, f.name;



// --- Mediated pathways (e.g. steroids -> osteoporosis -> fracture) ---

MATCH (src:Factor)-[r1]->(mid:Factor)-[r2:CONTRIBUTES_TO]->(c:Condition)

RETURN src, r1, mid, r2, c;



// --- Discriminators: highly specific red flags across conditions ---

MATCH (ch:Chunk {is_specific: true})-[:DESCRIBES]->(f:Factor)

MATCH (ch)-[:APPLIES_TO]->(c:Condition)

RETURN c.name AS condition, f.name AS discriminator, ch.chunk_id

ORDER BY condition;



// --- Multi-condition symptom: where one factor points to several diagnoses ---

MATCH (f:Factor)-[]->(c:Condition)

WITH f, collect(DISTINCT c.name) AS conditions

WHERE size(conditions) > 1

RETURN f.name AS factor, conditions

ORDER BY size(conditions) DESC, factor;



// --- Styled view for Browser (color by node type) ---

MATCH (n)

OPTIONAL MATCH (n)-[r]->(m)

RETURN n, r, m

LIMIT 300;

