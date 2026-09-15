// TRI-BACK Red Flags — generated import script
// Open Neo4j Browser (Aura or Desktop), paste sections or run the full file.
// Source: C:\ROBS STUFF\UBC Postdoctoral Fellowship\TRI-BACK\Graphs\backups\red flags\v4\source\red_flags_edges_v4_2026.9.10.csv
// Rows: 86

// --- wipe existing graph ---
MATCH (n) DETACH DELETE n;

// --- schema ---
CREATE CONSTRAINT factor_name IF NOT EXISTS FOR (n:Factor) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT condition_name IF NOT EXISTS FOR (n:Condition) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE;
CREATE INDEX chunk_specific IF NOT EXISTS FOR (c:Chunk) ON (c.is_specific);

// --- data ---
// row 1: r_1
MERGE (factor:Factor {name: 'Age over 50'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_1'})
SET chunk.chunk_string = 'Age over 50 is an independent predisposing risk factor that increases susceptibility to vertebral fracture.',
    chunk.source_rank = '2',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'both',
    chunk.path = 'Osteoporosis',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'both',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_1'
                

                MERGE (mediator:Factor {name: 'Osteoporosis'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'both',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_1'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'both',
                    chain.chunk_id = 'r_1';

// row 2: r_2
MERGE (factor:Factor {name: 'Recent trauma'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_2'})
SET chunk.chunk_string = 'A recent history of trauma is a primary trigger event that indicates high suspicion for a vertebral fracture.',
    chunk.source_rank = '2',
    chunk.edges = 'TRIGGER_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`TRIGGER_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_2';

// row 3: r_3
MERGE (factor:Factor {name: 'Bruising'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_3'})
SET chunk.chunk_string = 'Local bruising or abrasion can indicate recent trauma. In the context of recent, significant trauma, vertebral fracture should be considered as a possible serious pathology.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'mediated',
    chunk.path = 'Recent trauma',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Recent trauma'})
                MERGE (factor)-[med_rel:`SUGGESTIVE_OF`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_3'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_3';

// row 4: r_4
MERGE (factor:Factor {name: 'Female sex'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_4'})
SET chunk.chunk_string = 'Female sex is an independent pre-disposing risk factor that increases susceptibility to vertebral fracture.',
    chunk.source_rank = '2',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'both',
    chunk.path = 'Osteoporosis',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'both',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_4'
                

                MERGE (mediator:Factor {name: 'Osteoporosis'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'both',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_4'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'both',
                    chain.chunk_id = 'r_4';

// row 5: r_5
MERGE (factor:Factor {name: 'Severe pain'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_5'})
SET chunk.chunk_string = 'Pain severity greater than 7/10 (on a 0–10 scale) has been reported in association with vertebral fracture. Severe pain alone is not specific for fracture, but used together with trauma history, age, and other red flags to guide triage urgency.',
    chunk.source_rank = '2',
    chunk.edges = 'ASSOCIATED_WITH',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`ASSOCIATED_WITH`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_5';

// row 6: r_6
MERGE (factor:Factor {name: 'Corticosteroids'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_6'})
SET chunk.chunk_string = 'Prolonged corticosteroid therapy (greater than 5 or 7.5 mg per day over a 3-month period) predisposes to vertebral fracture by weakening bone. It indicates higher suspicion for fracture when pain occurs in a patient with ongoing steroid exposure.',
    chunk.source_rank = '1',
    chunk.edges = 'ASSOCIATED_WITH',
    chunk.path_type = 'mediated',
    chunk.path = 'Osteoporosis',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Osteoporosis'})
                MERGE (factor)-[med_rel:`ASSOCIATED_WITH`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_6'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_6';

// row 7: r_7
MERGE (factor:Factor {name: 'Osteoporosis'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_7'})
SET chunk.chunk_string = 'Osteoporosis predisposes to vertebral fracture by reducing vertebral bone strength. It is a common mechanistic link between chronic risk factors (e.g. older age, prolonged steroids) and fragility-related spinal injury.',
    chunk.source_rank = '2',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_7';

// row 8: r_8
MERGE (factor:Factor {name: 'Alcohol'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_8'})
SET chunk.chunk_string = 'Heavy or excessive alcohol use predisposes to vertebral insufficiency fracture by harming bone health and increasing falls. It raises concern for vertebral fracture, particularly with other fracture risk factors or in the context of trauma.',
    chunk.source_rank = '1',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Osteoporosis',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Osteoporosis'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_8'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_8';

// row 9: r_9
MERGE (factor:Factor {name: 'Nutrient Deficiency'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_9'})
SET chunk.chunk_string = 'Nutritional deficiencies caused by dietary restrictions, eating disorders, or conditions affecting intestinal absorption (e.g. Crohn\'s disease) affects bone health and is a risk factor for vertebral fracture.',
    chunk.source_rank = '1',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Osteoporosis',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Osteoporosis'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_9'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_9';

// row 10: r_10
MERGE (factor:Factor {name: 'Vitamin Deficiency'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_10'})
SET chunk.chunk_string = 'Vitamin D deficiency predisposes to vertebral fracture by weakening bone. Should be used in combination with other risk factors: isolated vitamin D deficiency is a weak stand-alone indicator.',
    chunk.source_rank = '1',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Osteoporosis',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Osteoporosis'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_10'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_10';

// row 11: r_11
MERGE (factor:Factor {name: 'Diabetes'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_11'})
SET chunk.chunk_string = 'Diabetes, especially when poorly controlled, is a risk factor for vertebral fracture due to reduced bone health. Risk will depend on if diabetes is present, how well it is controlled, and whether there are other osteoporosis-related risks (steroids, age, prior fracture). Diabetes alone does not confirm fracture—use it with trauma history, worsening pain, and other red flags to determine triage urgency.',
    chunk.source_rank = '1',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Osteoporosis',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Osteoporosis'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_11'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_11';

// row 12: r_12
MERGE (factor:Factor {name: 'Rheumatoid arthritis'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_12'})
SET chunk.chunk_string = 'Rheumatoid arthritis is a risk factor for vertebral (osteoporotic) fracture. Patients may also have long-term corticosteroid use, which further increases fracture risk. Rheumatoid arthritis alone does not confirm fracture—use it with trauma history, worsening pain, and other red flags to determine triage urgency.',
    chunk.source_rank = '1',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'both',
    chunk.path = 'Corticosteroids',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'both',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_12'
                

                MERGE (mediator:Factor {name: 'Corticosteroids'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'both',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_12'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'both',
                    chain.chunk_id = 'r_12';

// row 13: r_13
MERGE (factor:Factor {name: 'Smoking'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_13'})
SET chunk.chunk_string = 'Smoking increases the risk of vertebral fracture, particularly heavy smoking (more than 20 cigarettes per day). Tobacco exposure worsens bone health and is part of a broader risk-factor profile. Heavy smoking alone does not confirm fracture—use it with trauma history, worsening pain, and other red flags to determine triage urgency.',
    chunk.source_rank = '1',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Osteoporosis',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Osteoporosis'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_13'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_13';

// row 14: r_14
MERGE (factor:Factor {name: 'Osteoarthritis'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_14'})
SET chunk.chunk_string = 'Osteoarthritis may increase clinical concern for vertebral fracture in combination with other red flags; isolated osteoarthritis is a weak stand-alone indicator',
    chunk.source_rank = '2',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_14';

// row 15: r_15
MERGE (factor:Factor {name: 'Neuro motor deficit'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_15'})
SET chunk.chunk_string = 'New or worsening neurologic motor symptoms (leg weakness, poor balance when walking, foot drop) alongside spinal pain raises concern for spinal cord compression as a result of vertebral fracture.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_15';

// row 16: r_16
MERGE (factor:Factor {name: 'Point tenderness'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_16'})
SET chunk.chunk_string = 'Low back point tenderness raises concern for vertebral fracture, especially when combined with concurrent bruising/abrasion and history of trauma. Combine point tenderness with fracture risk factors (age, trauma, osteoporosis, weight-bearing pain) to determine triage urgency —tenderness alone is not sufficient to confirm fracture.',
    chunk.source_rank = '3',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_16';

// row 17: r_17
MERGE (factor:Factor {name: 'Pain weight-bearing'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_17'})
SET chunk.chunk_string = 'Pain that is worse with weight-bearing is a common feature of vertebral fracture. After trauma or insufficiency fracture, pain is often severe and localized to the affected area. This pattern supports mechanical loading of an unstable vertebral segment. Combine with fracture risk factors (age, osteoporosis, trauma, steroids); weight-bearing pain alone is not diagnostic.',
    chunk.source_rank = '3',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_17';

// row 18: r_18
MERGE (factor:Factor {name: 'Neuro sensory deficit'})
MERGE (condition:Condition {name: 'Fracture'})
MERGE (chunk:Chunk {chunk_id: 'r_18'})
SET chunk.chunk_string = 'New or worsening neurologic sensory symptoms (electric shock-like pain, tingling, numbness, loss of proprioception) alongside spinal pain raises concern for spinal cord compression as a result of vertebral fracture.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_18';

// row 19: r_19
MERGE (factor:Factor {name: 'Previous cancer'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_19'})
SET chunk.chunk_string = 'A previous history of cancer is a major risk factor for spinal malignancy, including metastatic spinal disease. The 5 most common cancers to metastasize are breast, prostate, lung, kidney, and thyroid. History of cancer alone does not confirm malignancy; combine with other red flags to guide triage urgency.',
    chunk.source_rank = '1',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_19';

// row 20: r_20
MERGE (factor:Factor {name: 'Age over 50'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_20'})
SET chunk.chunk_string = 'Age over 50 years is an independent predisposing risk factor that increases susceptibility to malignancy.',
    chunk.source_rank = '2',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_20';

// row 21: r_21
MERGE (factor:Factor {name: 'Unexplained weight loss'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_21'})
SET chunk.chunk_string = 'Unexplained weight loss is a worrying red-flag symptom that raises suspicion for malignancy. It is necessary to rule out diet change, increased activity, or medication effects as potential benign causes of weight loss.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_21';

// row 22: r_22
MERGE (factor:Factor {name: 'Refractory pain'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_22'})
SET chunk.chunk_string = 'Lack of improvement in back pain despite appropriate conservative treatment (e.g. activity modification, analgesia, physiotherapy) for at least 6 weeks raises suspicion for spinal malignancy when symptoms persist or worsen.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_22';

// row 23: r_23
MERGE (factor:Factor {name: 'Constant pain'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_23'})
SET chunk.chunk_string = 'Constant or steadily worsening pain that does not improve with position or activity is a red-flag pain profile for malignancy. Interpret alongside cancer history, weight loss, and symptoms—not in isolation.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_23';

// row 24: r_24
MERGE (factor:Factor {name: 'Immunosuppression'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_24'})
SET chunk.chunk_string = 'Immunosuppression from comorbidity or medication (e.g. diabetes, HIV, rheumatoid disease) or indicated by recurrent infections is a red-flag risk factor for malignancy.',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_24';

// row 25: r_25
MERGE (factor:Factor {name: 'Severe pain'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_25'})
SET chunk.chunk_string = 'Pain severity greater than 7/10 (on a 0–10 scale) has been reported in association with vertebral malignancy. Severe pain alone is not specific for malignancy, but used together with cancer history, age, and other red flags to guide triage urgency.',
    chunk.source_rank = '3',
    chunk.edges = 'ASSOCIATED_WITH',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`ASSOCIATED_WITH`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_25';

// row 26: r_26
MERGE (factor:Factor {name: 'Night pain'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_26'})
SET chunk.chunk_string = 'Back pain that wakes you at night and prevents you from settling back to sleep is a red-flag symptom to consider in spinal malignancy, especially when pain is progressive, unfamiliar, and accompanied by prior cancer or unexplained weight loss.',
    chunk.source_rank = '3',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_26';

// row 27: r_27
MERGE (factor:Factor {name: 'Smoking'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_27'})
SET chunk.chunk_string = 'Smoking increases the risk of vertebral malignancy, particularly heavy smoking (more than 20 cigarettes per day). Tobacco exposure is linked to cancer, worsens bone health, and is part of a broader risk-factor profile. Heavy smoking alone does not confirm malignancy—use it with cancer history, worsening pain, and other red flags to determine triage urgency.',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_27';

// row 28: r_28
MERGE (factor:Factor {name: 'Neuro motor deficit'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_28'})
SET chunk.chunk_string = 'New or worsening neurologic motor symptoms (leg weakness, poor balance when walking, foot drop) alongside spinal pain raises concern for spinal cord compression by tumour.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_28';

// row 29: r_29
MERGE (factor:Factor {name: 'Neuro sensory deficit'})
MERGE (condition:Condition {name: 'Malignancy'})
MERGE (chunk:Chunk {chunk_id: 'r_29'})
SET chunk.chunk_string = 'New or worsening neurologic sensory symptoms (electric shock-like pain, tingling, numbness, loss of proprioception) alongside spinal pain raises concern for spinal cord compression by tumour.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_29';

// row 30: r_30
MERGE (factor:Factor {name: 'Recent surgery'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_30'})
SET chunk.chunk_string = 'Recent spinal, abdominal, or pelvic surgery is a route for postoperative spinal infection. When back pain follows a recent procedure, clarify fever, chills, night sweats, and wound problems before attributing pain to a mechanical cause.',
    chunk.source_rank = '0',
    chunk.edges = 'CONFIRM_AGAINST',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'tbd',
    chunk.evidence_level = 'tbd',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`CONFIRM_AGAINST`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_30';

// row 31: r_31
MERGE (factor:Factor {name: 'Refractory pain'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_31'})
SET chunk.chunk_string = 'Failure to improve with appropriate conservative care raises suspicion for serious spinal pathology generally, not malignancy alone. When pain is refractory, clarify infection features (fever, chills, night sweats, intravenous drug use, immunosuppression) alongside malignancy features.',
    chunk.source_rank = '0',
    chunk.edges = 'CONFIRM_AGAINST',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'tbd',
    chunk.evidence_level = 'tbd',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`CONFIRM_AGAINST`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_31';

// row 32: r_32
MERGE (factor:Factor {name: 'Point tenderness'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_32'})
SET chunk.chunk_string = 'Focal spinal tenderness occurs in vertebral osteomyelitis and discitis as well as in fracture. When point tenderness is present without a clear traumatic mechanism, clarify fever, chills, night sweats, intravenous drug use, and immunosuppression.',
    chunk.source_rank = '0',
    chunk.edges = 'CONFIRM_AGAINST',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'tbd',
    chunk.evidence_level = 'tbd',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`CONFIRM_AGAINST`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_32';

// row 33: r_33
MERGE (factor:Factor {name: 'Unexplained weight loss'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_33'})
SET chunk.chunk_string = 'Unexplained weight loss is a red-flag symptom that raises suspicion for spinal infection. It is necessary to rule out diet change, increased activity, or medication effects as potential benign causes of weight loss.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_33';

// row 34: r_34
MERGE (factor:Factor {name: 'Fever'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_34'})
SET chunk.chunk_string = 'Fever since the onset of spinal pain is a red-flag symptom for spinal infection and forms part of the classic triad with back pain and potential neurological dysfunction. Absence of fever does not rule out spinal infection- interpret alongside intravenous drug use history, recent infections, and symptoms.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_34';

// row 35: r_35
MERGE (factor:Factor {name: 'Chills'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_35'})
SET chunk.chunk_string = 'Chills since the onset of back pain are a spinal infection red flag, screened alongside fever. Absence of chills does not rule out spinal infection- interpret alongside intravenous drug use history, recent infections, and symptoms.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_35';

// row 36: r_36
MERGE (factor:Factor {name: 'Night sweats'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_36'})
SET chunk.chunk_string = 'Night sweats since the onset of back pain are a spinal infection red flag, screened alongside fever. Absence of night sweats does not rule out spinal infection- interpret alongside intravenous drug use history, recent infections, and symptoms.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_36';

// row 37: r_37
MERGE (factor:Factor {name: 'Age over 50'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_37'})
SET chunk.chunk_string = 'Age over 50 years is an independent predisposing risk factor that increases susceptibility to spinal infection.',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Immunosuppression',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Immunosuppression'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_37'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_37';

// row 38: r_38
MERGE (factor:Factor {name: 'IV drug user'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_38'})
SET chunk.chunk_string = 'Intravenous (IV) drug use is associated with an increased risk of spinal infection. When assessing back pain, ask about current or past recreational drug use and route of administration (oral versus IV) in a non-judgmental way. Known IV drug users warrant a lower threshold for infection screening (fever, chills, progressive pain, neurological symptoms).',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_38';

// row 39: r_39
MERGE (factor:Factor {name: 'Immunosuppression'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_39'})
SET chunk.chunk_string = 'Immunosuppression from comorbidity or medication (e.g. diabetes, HIV, rheumatoid disease) or indicated by recurrent infections is a red-flag risk factor for spinal infection.',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_39';

// row 40: r_40
MERGE (factor:Factor {name: 'Constant pain'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_40'})
SET chunk.chunk_string = 'Constant or steadily worsening pain that does not improve with position or activity is a red-flag pain profile for spinal infection. Interpret alongside infection history, fever, and symptoms—not in isolation.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_40';

// row 41: r_41
MERGE (factor:Factor {name: 'Night pain'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_41'})
SET chunk.chunk_string = 'Back pain that wakes you at night and prevents you from settling back to sleep is a red-flag symptom to consider in spinal infection, especially when pain becomes constant, more intense, or is accompanied by fever, chills, feeling unwell, or progressive limitation of movement.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_41';

// row 42: r_42
MERGE (factor:Factor {name: 'Severe pain'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_42'})
SET chunk.chunk_string = 'Pain severity greater than 7/10 (on a 0–10 scale) has been reported in association with spinal infection. Severe pain alone is not specific for infection, but used together with infection history, IV drug use, fever, chills, and night sweats to guide triage urgency.',
    chunk.source_rank = '3',
    chunk.edges = 'ASSOCIATED_WITH',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`ASSOCIATED_WITH`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_42';

// row 43: r_43
MERGE (factor:Factor {name: 'Neuro motor deficit'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_43'})
SET chunk.chunk_string = 'New or worsening neurologic motor symptoms (leg weakness, poor balance when walking, foot drop) alongside spinal pain raises concern for spinal cord compression by abscess following spinal infection.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_43';

// row 44: r_44
MERGE (factor:Factor {name: 'Neuro sensory deficit'})
MERGE (condition:Condition {name: 'Infection'})
MERGE (chunk:Chunk {chunk_id: 'r_44'})
SET chunk.chunk_string = 'New or worsening neurologic sensory symptoms (electric shock-like pain, tingling, numbness, loss of proprioception) alongside spinal pain raises concern for spinal cord compression by abscess following spinal infection.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_44';

// row 45: r_45
MERGE (factor:Factor {name: 'Neuro sensory deficit'})
MERGE (condition:Condition {name: 'CES'})
MERGE (chunk:Chunk {chunk_id: 'r_45'})
SET chunk.chunk_string = 'New or worsening neurologic sensory symptoms (electric shock-like pain, tingling, numbness, loss of proprioception) may precede bilateral symptoms or may be more detectable on one side. Clarifying whether symptoms are unilateral or bilateral is important for urgency stratification.',
    chunk.source_rank = '3',
    chunk.edges = 'CONFIRM_AGAINST',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`CONFIRM_AGAINST`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_45';

// row 46: r_46
MERGE (factor:Factor {name: 'Neuro motor deficit'})
MERGE (condition:Condition {name: 'CES'})
MERGE (chunk:Chunk {chunk_id: 'r_46'})
SET chunk.chunk_string = 'New or worsening neurologic motor symptoms (leg weakness, poor balance when walking, foot drop) may precede bilateral symptoms or may be more detectable on one side. Clarifying whether symptoms are unilateral or bilateral is important for urgency stratification.',
    chunk.source_rank = '3',
    chunk.edges = 'CONFIRM_AGAINST',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`CONFIRM_AGAINST`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_46';

// row 47: r_47
MERGE (factor:Factor {name: 'Bilat neuro motor deficit'})
MERGE (condition:Condition {name: 'CES'})
MERGE (chunk:Chunk {chunk_id: 'r_47'})
SET chunk.chunk_string = 'New or worsening neurologic motor symptoms (leg weakness, poor balance when walking, foot drop) in both limbs alongside spinal pain is worrying for cauda equina syndrome (CES).',
    chunk.source_rank = '3',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_47';

// row 48: r_48
MERGE (factor:Factor {name: 'Bilat neuro sensory deficit'})
MERGE (condition:Condition {name: 'CES'})
MERGE (chunk:Chunk {chunk_id: 'r_48'})
SET chunk.chunk_string = 'New or worsening neurologic sensory symptoms (electric shock-like pain, tingling, numbness, loss of proprioception) in both limbs alongside spinal pain is worrying for cauda equina syndrome (CES).',
    chunk.source_rank = '3',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_48';

// row 49: r_49
MERGE (factor:Factor {name: 'Bladder dysfunction'})
MERGE (condition:Condition {name: 'CES'})
MERGE (chunk:Chunk {chunk_id: 'r_49'})
SET chunk.chunk_string = 'Urinary retention (can\'t fully empty) and incontinence (can\'t hold it / make it to the bathroom) are specific symptoms of cauda equina syndrome.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_49';

// row 50: r_50
MERGE (factor:Factor {name: 'Bowel dysfunction'})
MERGE (condition:Condition {name: 'CES'})
MERGE (chunk:Chunk {chunk_id: 'r_50'})
SET chunk.chunk_string = 'Bowel dysfunction (loss of rectal sensation, constipation) and fecal incontinence (can\'t hold it / make it to the bathroom) are specific symptoms of cauda equina syndrome.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_50';

// row 51: r_51
MERGE (factor:Factor {name: 'Saddle anaesthesia'})
MERGE (condition:Condition {name: 'CES'})
MERGE (chunk:Chunk {chunk_id: 'r_51'})
SET chunk.chunk_string = 'Loss of sensation around the perineum, buttocks, inner thighs, genitals, and anus are specific symptoms of cauda equina syndrome.',
    chunk.source_rank = '2',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The diagnostic value of Red Flags in thoracolumbar pain: a systematic review | author: Maselli F | year: 2022 | authority: Disability and Rehabilitation | doi: https://doi.org/10.1080/09638288.2020.1804626',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_51';

// row 52: r_52
MERGE (factor:Factor {name: 'Severe pain'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_52'})
SET chunk.chunk_string = 'Pain severity greater than 7/10 (on a 0-10 scale), particularly sudden, tearing, or unfamiliar pain, can accompany expansion or rupture of an abdominal aortic aneurysm. Severe pain alone is not specific for aneurysm, but used together with abdominal or groin radiation, age over 50, male sex, smoking, hypertension, and cardiovascular history to guide triage urgency.',
    chunk.source_rank = '3',
    chunk.edges = 'ASSOCIATED_WITH',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'tbd',
    chunk.evidence_level = 'tbd',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`ASSOCIATED_WITH`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_52';

// row 53: r_53
MERGE (factor:Factor {name: 'Abdominal pain'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_53'})
SET chunk.chunk_string = 'In patients presenting with low back pain, abdominal pain that radiates or extends toward the groin raises concern for abdominal aortic aneurysm,  a vascular emergency. Combine abdominal or groin pain with age over 50, smoking, and hypertension to determine triage urgency.',
    chunk.source_rank = '3',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_53';

// row 54: r_54
MERGE (factor:Factor {name: 'Cardiovascular disease'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_54'})
SET chunk.chunk_string = 'Patients with a history of peripheral vascular disease or coronary artery disease are at an elevated risk of developing an abdominal aortic aneurysm.',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_54';

// row 55: r_55
MERGE (factor:Factor {name: 'Age over 50'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_55'})
SET chunk.chunk_string = 'Age over 50 years is an independent predisposing risk factor that increases susceptibility to abdominal aortic aneurysm.',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_55';

// row 56: r_56
MERGE (factor:Factor {name: 'Smoking'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_56'})
SET chunk.chunk_string = 'Smoking increases the risk of abdominal aortic aneurysm, particularly heavy smoking (more than 20 cigarettes per day). Heavy smoking alone does not confirm abdominal aortic aneurysm—use it with cardiovascular history, abdominal/groin pain, and other red flags to determine triage urgency.',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'both',
    chunk.path = 'Cardiovascular disease',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'both',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_56'
                

                MERGE (mediator:Factor {name: 'Cardiovascular disease'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'both',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_56'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'both',
                    chain.chunk_id = 'r_56';

// row 57: r_57
MERGE (factor:Factor {name: 'Male sex'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_57'})
SET chunk.chunk_string = 'Abdominal aortic aneurysm occurs substantially more often in men. Male sex alone does not confirm abdominal aortic aneurysm—use it with cardiovascular history, abdominal/groin pain, and other red flags to determine triage urgency.',
    chunk.source_rank = '4',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The Global and Regional Prevalence of Abdominal Aortic Aneurysms: A Systematic Review and Modeling Analysis | author: Song, Peige | year: 2023 | authority: Annals of Surgery | doi: https://doi.org/10.1097/SLA.0000000000005716',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_57';

// row 58: r_58
MERGE (factor:Factor {name: 'Hypertension'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_58'})
SET chunk.chunk_string = 'Hypertension is a common predisposing risk factor for abdominal aortic aneurysm. In patients with low back pain, poorly controlled or long-standing hypertension raises baseline concern when aneurysm is in the differential, especially with abdominal or groin radiation, age over 50, smoking, male sex, or known peripheral vascular or coronary disease. Hypertension alone does not confirm AAA—use it with symptom and examination findings to determine triage urgency.',
    chunk.source_rank = '4',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Cardiovascular disease',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The Global and Regional Prevalence of Abdominal Aortic Aneurysms: A Systematic Review and Modeling Analysis | author: Song, Peige | year: 2023 | authority: Annals of Surgery | doi: https://doi.org/10.1097/SLA.0000000000005716',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Cardiovascular disease'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_58'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_58';

// row 59: r_59
MERGE (factor:Factor {name: 'Diabetes'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_59'})
SET chunk.chunk_string = 'Diabetes, especially when poorly controlled, is a risk factor for abdominal aortic aneurysm. The presence of diabetes increases concern for abdominal aortic aneurysm when pain is abdominal or radiates to the groin, or when other vascular red flags are present. Control and duration matter clinically, but diabetes alone does not confirm aneurysm; pair with abdominal symptoms, age, smoking, hypertension, and history of cardiovascular disease to determine triage urgency.',
    chunk.source_rank = '4',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Cardiovascular disease',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The Global and Regional Prevalence of Abdominal Aortic Aneurysms: A Systematic Review and Modeling Analysis | author: Song, Peige | year: 2023 | authority: Annals of Surgery | doi: https://doi.org/10.1097/SLA.0000000000005716',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Cardiovascular disease'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_59'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_59';

// row 60: r_60
MERGE (factor:Factor {name: 'Family history of AAA'})
MERGE (condition:Condition {name: 'AAA'})
MERGE (chunk:Chunk {chunk_id: 'r_60'})
SET chunk.chunk_string = 'A family history of abdominal aortic aneurysm—especially in a first-degree relative (parent, sibling, or child)—is an independent predisposing risk factor that substantially increases lifetime risk of aneurysm. In patients with low back pain, this history raises baseline concern, particularly with abdominal or groin radiation, age over 50, male sex, smoking, hypertension, or known vascular disease. Family history alone does not confirm abdominal aortic aneurysm; use it with current symptoms and examination to determine triage urgency.',
    chunk.source_rank = '3',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: The use of red flags in screening patients in physiotherapy: narrative review. | author: Maselli F | year: 2019 | authority: University of Genova | doi: https://hdl.handle.net/20.500.14242/101517',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_60';

// row 61: r_61
MERGE (factor:Factor {name: 'Severe pain'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_61'})
SET chunk.chunk_string = 'Pain severity greater than 7/10 (on a 0-10 scale) may accompany deep vein thrombosis, including inferior vena cava thrombosis presenting as low back pain. Severe pain alone is not specific for thrombosis, but used together with calf pain, calf swelling, calf redness (especially unilateral), recent surgery, and immobility to guide triage urgency.',
    chunk.source_rank = '5',
    chunk.edges = 'ASSOCIATED_WITH',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'tbd',
    chunk.evidence_level = 'tbd',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`ASSOCIATED_WITH`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_61';

// row 62: r_62
MERGE (factor:Factor {name: 'Hypercoagulability'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_62'})
SET chunk.chunk_string = 'Hypercoagulability (lower clotting threshold of the blood associated with many causes including malignancy, Factor V Leiden, pregnancy, estrogen therapy, or inflammatory states) predisposes to deep vein thrombosis. In low back pain, it raises concern when there is calf pain (especially unilateral) or swelling, recent surgery, or prolonged immobility. Deep vein thrombosis at the level of the inferior vena cava can also present as back pain. Hypercoagulability alone does not confirm deep vein thrombosis—combine with other risk factors and red flags to determine triage urgency.',
    chunk.source_rank = '5',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Patients with inferior vena cava thrombosis frequently present with lower back pain and bilateral lower-extremity deep vein thrombosis | author: Kraft, Christiane | year: 2013 | authority: European Journal of Vascular Medicine | doi: https://doi.org/10.1024/0301-1526/a000288',
    chunk.evidence_level = 'OBS',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_62';

// row 63: r_63
MERGE (factor:Factor {name: 'Venous stasis'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_63'})
SET chunk.chunk_string = 'Venous stasis (slowed venous flow in the legs) is a core mechanism for deep vein thrombosis in Virchow’s triad. It is relevant in low back pain when the person has had prolonged bed rest, long travel, casting, or reduced mobility. Stasis increases baseline concern for deep vein thrombosis alongside calf swelling or calf pain; it does not confirm thrombosis without supporting signs. Consider in combination with other red flags to determine triage urgency.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_63';

// row 64: r_64
MERGE (factor:Factor {name: 'Endothelial injury'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_64'})
SET chunk.chunk_string = 'Endothelial injury to vein walls (e.g. from recent surgery, trauma, central venous access) completes Virchow’s triad and is a risk faactor for deep vein thrombosis. With low back pain, recent operative or venous injury history increases concern when calf pain, swelling, or redness (especially if unilateral) appears. Endothelial injury alone is not sufficient to diagnose deep vein thrombosis. Consider together with other risk factors to determine triage urgency.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_64';

// row 65: r_65
MERGE (factor:Factor {name: 'Previous DVT'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_65'})
SET chunk.chunk_string = 'A previous deep vein thrombosis or pulmonary embolism strongly increases the risk of recurrent clot. In low back pain, prior clot raises concern when new calf swelling, pain, or warmth (especially if unilateral) develops, particularly after surgery or immobilisation. History of deep vein thrombosis alone does not indicate new clot- consider together with other red flags and risk factors to determine triage urgency.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_65';

// row 66: r_66
MERGE (factor:Factor {name: 'Calf redness'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_66'})
SET chunk.chunk_string = 'Calf redness with pain or swelling (especially if unilateral) suggests possible deep vein thrombosis in low back pain. Most deep vein thromboses start in the deep veins of the calf and travel up the vascular system. Calf redness alone is not an indicator of deep vein thrombosis- consider together with calf pain, calf swelling, and predisposing risk factors to determine triage urgency.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_66';

// row 67: r_67
MERGE (factor:Factor {name: 'Calf pain'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_67'})
SET chunk.chunk_string = 'Calf pain with redness or swelling (especially if unilateral) suggests possible deep vein thrombosis in low back pain. Most deep vein thromboses start in the deep veins of the calf and travel up the vascular system. Calf pain alone is not an indicator of deep vein thrombosis- consider together with calf redness, calf swelling, and predisposing risk factors to determine triage urgency.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_67';

// row 68: r_68
MERGE (factor:Factor {name: 'Calf swelling'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_68'})
SET chunk.chunk_string = 'Calf swelling with pain or redness (especially if unilateral) suggests possible deep vein thrombosis in low back pain. Most deep vein thromboses start in the deep veins of the calf and travel up the vascular system. Calf swelling alone is not an indicator of deep vein thrombosis- consider together with calf pain, calf redness, and predisposing risk factors to determine triage urgency.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_68';

// row 69: r_69
MERGE (factor:Factor {name: 'Recent surgery'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_69'})
SET chunk.chunk_string = 'Recent surgery (especially major abdominal, orthopaedic, or pelvic procedures within the last 4 weeks) is a well-established risk factor for deep vein thrombosis due to vessel wall injury. Recent surgery alone is not an indicator of deep vein thrombosis- consider together with calf pain, calf redness, calf swelling, and predisposing risk factors to determine triage urgency',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Endothelial injury',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Endothelial injury'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_69'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_69';

// row 70: r_70
MERGE (factor:Factor {name: 'Prolonged bed rest'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_70'})
SET chunk.chunk_string = 'Prolonged bed rest or immobilisation for at least 3 days causes venous stasis and is a known risk factor for pulmonary embolism and deep vein thrombosis. In low back pain with reduced activity or hospitalisation, consider immobility in the context of recent surgery, calf swelling, calf redness, and calf pain to determine triage urgency.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Venous stasis',
    chunk.is_specific = true,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Venous stasis'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_70'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_70';

// row 71: r_71
MERGE (factor:Factor {name: 'Age over 50'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_71'})
SET chunk.chunk_string = 'Age over 50 years is an independent predisposing risk factor that increases susceptibility to deep vein thrombosis.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_71';

// row 72: r_72
MERGE (factor:Factor {name: 'Diabetes'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_72'})
SET chunk.chunk_string = 'Diabetes contributes to hypercoagulability- in the context of low back pain, it modestly raises concern for deep vein thrombosis when calf pain/redness/swelling (especially unilateral), recent surgery, or immobilisation is present. Diabetes alone does not confirm deep vein thrombosis.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Hypercoagulability',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Hypercoagulability'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_72'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_72';

// row 73: r_73
MERGE (factor:Factor {name: 'Hypertension'})
MERGE (condition:Condition {name: 'DVT'})
MERGE (chunk:Chunk {chunk_id: 'r_73'})
SET chunk.chunk_string = 'Hypertension contributes to hypercoagulability- in the context of low back pain, it modestly raises concern for deep vein thrombosis when calf pain/redness/swelling (especially unilateral), recent surgery, or immobilisation is present. Hypertension alone does not confirm deep vein thrombosis.',
    chunk.source_rank = '6',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Hypercoagulability',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Diagnosis of Venous Thromboembolism | author: Canas, Alicia | year: 2025 | authority: Medical Clinics | doi: https://10.1016/j.mcna.2025.01.006',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Hypercoagulability'})
                MERGE (factor)-[med_rel:`RISK_FACTOR_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_73'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_73';

// row 74: r_74
MERGE (factor:Factor {name: 'Movement-related pain'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_74'})
SET chunk.chunk_string = 'Movement-related pain that changes with bending, twisting, sitting, standing, or activityâ€”rather than remaining constant and non-mechanicalâ€”is the core clinical pattern of a non-specific mechanical cause. Use this pattern with other mechanical features; movement-related pain alone does not exclude serious pathology when strong red-flag clusters are present.',
    chunk.source_rank = '9',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Low Back Pain | author: Chiodo Anthony | year: 2020 | authority: University of Michigan | doi: https://www.ncbi.nlm.nih.gov/books/NBK572334/',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_74';

// row 75: r_75
MERGE (factor:Factor {name: 'Pain relieved by rest'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_75'})
SET chunk.chunk_string = 'Pain that eases with rest or a change of position is typical of non-specific mechanical low back pain and contrasts with constant progressive pain that does not improve with position or activity (a non-mechanical red-flag profile for malignancy or infection). Rest relief alone is not diagnosticâ€”interpret alongside absence of systemic and neurologic red flags.',
    chunk.source_rank = '9',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Low Back Pain | author: Chiodo Anthony | year: 2020 | authority: University of Michigan | doi: https://www.ncbi.nlm.nih.gov/books/NBK572334/',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_75';

// row 76: r_76
MERGE (factor:Factor {name: 'Activity-related onset'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_76'})
SET chunk.chunk_string = 'Acute or subacute onset after ordinary loadingâ€”lifting, bending, twisting, gardening, or similar activityâ€”without major trauma is a common trigger for non-specific mechanical low back pain. Distinguish from Recent trauma with high-energy impact or fall, which raises fracture concern. Activity-related onset supports a mechanical cause when neurologic, infectious, and malignancy red flags are absent.',
    chunk.source_rank = '9',
    chunk.edges = 'TRIGGER_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Mechanical loading',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Low Back Pain | author: Chiodo Anthony | year: 2020 | authority: University of Michigan | doi: https://www.ncbi.nlm.nih.gov/books/NBK572334/',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Mechanical loading'})
                MERGE (factor)-[med_rel:`TRIGGER_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_76'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_76';

// row 77: r_77
MERGE (factor:Factor {name: 'Mechanical loading'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_77'})
SET chunk.chunk_string = 'Mechanical loading of spinal soft tissues (discs, facet joints, muscles, ligaments) is the conceptual pathway through which everyday activity and posture provoke non-specific mechanical low back pain. It is the common mediator linking activity-related onset, sitting intolerance, and load-sensitive symptoms to a non-specific mechanical cause rather than to serious spinal pathology.',
    chunk.source_rank = '9',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Low Back Pain | author: Chiodo Anthony | year: 2020 | authority: University of Michigan | doi: https://www.ncbi.nlm.nih.gov/books/NBK572334/',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_77';

// row 78: r_78
MERGE (factor:Factor {name: 'Prior similar episodes'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_78'})
SET chunk.chunk_string = 'A history of similar prior low back pain episodes that settled with time or simple care raises the likelihood that the current episode is again a non-specific mechanical cause. Recurrent mechanical episodes are common; prior episodes alone do not exclude a new serious pathology if unfamiliar features or red-flag clusters appear.',
    chunk.source_rank = '10',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Recurrence of low back pain is common: a prospective inception cohort study | author:  da Silva Tatiane | year: 2019 | authority: Journal of Physiotherapy | doi: https://doi.org/10.1016/j.jphys.2019.04.010',
    chunk.evidence_level = 'OBS',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_78';

// row 79: r_79
MERGE (factor:Factor {name: 'Lumbar stiffness'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_79'})
SET chunk.chunk_string = 'Reduced lumbar range of motion due to pain or muscle spasm is common in non-specific mechanical low back pain and in many serious spinal conditions. Limited motion supports a mechanical musculoskeletal presentation when pain is movement-related and systemic or cauda equina features are absent; do not use stiffness alone to rule out serious pathology.',
    chunk.source_rank = '11',
    chunk.edges = 'ASSOCIATED_WITH',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Restriction in lateral bending range of motion, lumbar lordosis, and hamstring flexibility predicts the development of low back pain: a systematic review of prospective cohort studies | author:  Sadler  Sean | year: 2017 | authority: BMC Musculoskeletal Disorders | https://doi.org/10.1186/s12891-017-1534-0',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`ASSOCIATED_WITH`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_79';

// row 80: r_80
MERGE (factor:Factor {name: 'Fluctuating pain'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_80'})
SET chunk.chunk_string = 'Pain severity that fluctuates through the dayâ€”waxing and waning with activity, posture, or restâ€”favours a non-specific mechanical cause over constant, steadily progressive pain (a red-flag profile for malignancy or infection). Fluctuating pain is common and not specific; interpret with other mechanical features and red-flag screening.',
    chunk.source_rank = '8',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Nonspecific Low Back Pain | author: Chiarotto Alessandro | year: 2022 | authority: New England Journal of Medicine | doi: https://doi.org/10.1056/NEJMcp2032396',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_80';

// row 81: r_81
MERGE (factor:Factor {name: 'Improves with conservative care'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_81'})
SET chunk.chunk_string = 'Early improvement with conservative care (activity modification, simple analgesia, physiotherapy) supports a non-specific mechanical cause and aligns with frameworks that begin a trial of therapy when concerning red-flag features are few or absent. Lack of expected improvement (refractory pain) instead raises suspicion for serious pathology and should not be attributed to mechanical causes alone.',
    chunk.source_rank = '1',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: International Framework for Red Flags for Potential Serious Spinal Pathologies | author: Finucane L | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://doi.org/10.2519/jospt.2020.9971',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_81';

// row 82: r_82
MERGE (factor:Factor {name: 'Prolonged sitting aggravates'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_82'})
SET chunk.chunk_string = 'Pain aggravated by prolonged sitting is a common load-sensitive mechanical pattern in non-specific low back pain. Sitting intolerance raises baseline concern for a mechanical cause when other red flags are absent; combine with movement-related variation and relief by position change rather than treating sitting aggravation in isolation.',
    chunk.source_rank = '12',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'mediated',
    chunk.path = 'Mechanical loading',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Evaluation of Nonspecific Low Back Pain Using a New Detailed Visual Analogue Scale for Patients in Motion, Standing, and Sitting: Characterizing Nonspecific Low Back Pain in Elderly Patients | author: Aoki Yasuchika | year: 2012 | authority: Pain Research and Treatment | doi: https://doi.org/10.1155/2012/680496',
    chunk.evidence_level = 'OBS',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Mechanical loading'})
                MERGE (factor)-[med_rel:`SUGGESTIVE_OF`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_82'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_82';

// row 83: r_83
MERGE (factor:Factor {name: 'Position change relief'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_83'})
SET chunk.chunk_string = 'Pain that eases after changing posture (for example lying on the side, standing after sitting, or gentle movement) is characteristic of non-specific mechanical low back pain and contrasts with pain that never settles with position. Position-change relief supports a mechanical cause alongside fluctuating, movement-related symptoms.',
    chunk.source_rank = '14',
    chunk.edges = 'SUGGESTIVE_OF',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Does Movement Change When Low Back Pain Changes? A Systematic Review | author: Wernli Kevin | year: 2020 | authority: Journal of Orthopaedic and Sports Physical Therapy | doi: https://www.jospt.org/doi/10.2519/jospt.2020.9635',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`SUGGESTIVE_OF`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_83';

// row 84: r_84
MERGE (factor:Factor {name: 'Severe pain'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_84'})
SET chunk.chunk_string = 'Pain severity greater than 7/10 can occur in non-specific mechanical low back pain as well as in serious spinal pathology. Severe pain alone is not specific for either; when the pattern is mechanical (movement-related, fluctuating, relieved by rest or position) and strong red-flag clusters are absent, severe pain remains compatible with a non-specific mechanical cause.',
    chunk.source_rank = '7',
    chunk.edges = 'ASSOCIATED_WITH',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Non-specific low back pain | author: Maher Chris | year: 2017 | authority: Lancet | doi: https://doi.org/10.1016/S0140-6736(16)30970-9',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`ASSOCIATED_WITH`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_84';

// row 85: r_85
MERGE (factor:Factor {name: 'Osteoarthritis'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_85'})
SET chunk.chunk_string = 'Osteoarthritis and degenerative spinal changes are common background findings and may contribute to activity-related mechanical low back pain. Osteoarthritis alone does not confirm a non-specific mechanical cause and is only a weak fracture indicator; interpret within the overall mechanical pattern and red-flag screen.',
    chunk.source_rank = '13',
    chunk.edges = 'RISK_FACTOR_FOR',
    chunk.path_type = 'direct',
    chunk.path = '',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Facet joint syndrome: from diagnosis to interventional management | author: Perolat, Romain | year: 2018 | authority: Insights into Imaging | https://doi.org/10.1007/s13244-018-0638-x',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (factor)-[direct_rel:`RISK_FACTOR_FOR`]->(condition)
                SET direct_rel.path_type = 'direct',
                    direct_rel.via_mediation = false,
                    direct_rel.chunk_id = 'r_85';

// row 86: r_86
MERGE (factor:Factor {name: 'Heavy lifting'})
MERGE (condition:Condition {name: 'Non-specific Mechanical Cause'})
MERGE (chunk:Chunk {chunk_id: 'r_86'})
SET chunk.chunk_string = 'Lifting heavy weights is a physical risk factor for nonspecific low back pain, and lifting is among the most commonly cited triggers of acute episodes (including in emergency presentations). Prefer a non-specific mechanical interpretation when onset follows ordinary lifting without major trauma and neurologic, infectious, and malignancy red flags are absent.',
    chunk.source_rank = '9',
    chunk.edges = 'TRIGGER_FOR',
    chunk.path_type = 'mediated',
    chunk.path = 'Mechanical loading',
    chunk.is_specific = false,
    chunk.is_guideline = false,
    chunk.evidence = 'title: Low Back Pain | author: Chiodo Anthony | year: 2020 | authority: University of Michigan | doi: https://www.ncbi.nlm.nih.gov/books/NBK572334/',
    chunk.evidence_level = 'SRMA',
    chunk.loc = 'low back'
MERGE (chunk)-[:DESCRIBES]->(factor)
MERGE (chunk)-[:APPLIES_TO]->(condition)


                MERGE (mediator:Factor {name: 'Mechanical loading'})
                MERGE (factor)-[med_rel:`TRIGGER_FOR`]->(mediator)
                SET med_rel.path_type = 'mediated',
                    med_rel.via_mediation = true,
                    med_rel.chunk_id = 'r_86'
                MERGE (mediator)-[chain:CONTRIBUTES_TO]->(condition)
                SET chain.path_type = 'mediated',
                    chain.chunk_id = 'r_86';

// --- verify ---
RETURN
  count { (f:Factor) } AS factors,
  count { (c:Condition) } AS conditions,
  count { (ch:Chunk) } AS chunks,
  count { ()-[r]->() } AS relationships;