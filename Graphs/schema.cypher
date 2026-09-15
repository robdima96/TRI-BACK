// TRI-BACK Red Flags — graph schema (constraints applied automatically on import)

// Nodes
// (:Factor {name})           — symptoms, traits, AND path mediators (shared label)
// (:Condition {name})       — red-flag diagnoses (parent_id)
// (:Chunk {chunk_id, ...})  — evidence rows from CSV

// Relationships (from CSV edges column, dynamic type)
// (:Factor)-[:RISK_FACTOR_FOR|SUGGESTIVE_OF|...]->(:Condition)     — direct / both
// (:Factor)-[:...]->(:Factor)                                       — source → path mediator
// (:Factor)-[:CONTRIBUTES_TO]->(:Condition)                         — path mediator → condition
// (:Chunk)-[:DESCRIBES]->(:Factor)
// (:Chunk)-[:APPLIES_TO]->(:Condition)

// path mediators use the same Factor label as source_nodes because they are clinical
// concepts that can appear in either role (e.g. Osteoporosis as mediator and as a
// direct risk factor in separate rows). MERGE on name unifies them.
