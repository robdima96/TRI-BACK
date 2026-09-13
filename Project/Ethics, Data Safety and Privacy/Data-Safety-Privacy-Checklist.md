# Data Safety, Privacy & Regulatory Checklist

## PHASE A — BEFORE FORMAL DATA COLLECTION (2 months: APRIL 1 2026 - MAY 31 2026)

**A.1 Ethics & research oversight**

- Confirm Principal Investigator is UBC faculty and roles are clear.
- Complete TCPS 2: CORE
- Determine correct REB (BREB vs CREB vs other) given study design, sites, and data types. (https://researchethics.ubc.ca/)
- Register for RISe (ethics submission system) and review applicable guidance notes for your stream.
- Draft research protocol: objectives, methods, inclusion/exclusion, risks/benefits, consent process.
- Define human feedback phases (ratings, rankings, conversation reuse) and whether data will be used for model training (SFT, preference optimization, RLHF-style methods)—reflect accurately in consent.
- If using feedback for weight updates (SFT, DPO, RLHF-style), describe risks (e.g., memorization) and participant withdrawal limits honestly in materials.

If Indigenous peoples or Indigenous data may be involved, plan per TCPS Chapter 9 and applicable OCAP® or community agreements.

**A.2 Privacy & institutional alignment**

- Create data flow diagram: collection → storage → compute (including GPU) → logs → backups → destruction.
- Classify data (e.g., identifiable PHI vs de-identified analytic sets) and document legal authority / institutional basis for holding data.
- Confirm approved UBC (or partner) storage and compute paths—no PHI on unapproved services, personal devices, or non-compliant clouds.
- List subprocessors (APIs, email, support tools) and ensure contracts / institutional agreements allow intended processing. Identifiable PHI never leaves approved UBC systems and never call external APIs with raw PHI—still need inventory of the service, what it processes, where (region), and for what purpose
- Document retention and secure destruction aligned with REB approval and institutional policy.
- Plan access control: least privilege, role-based access, no shared accounts, audit logging for access to PHI.

Plan encryption in transit and at rest for PHI; key management per institutional standards.

**A.3 Safety foundations**

- Write a clear intended-use statement (what the system is and is not; e.g., information/education vs diagnosis).
- Draft red-flag / escalation policy (symptom patterns, crisis mental-health pathways, abuse/vulnerability)—include Canadian/BC crisis and emergency resources (e.g., 911, 988 where applicable).
- Specify human escalation paths (e.g., stop, seek urgent care, contact clinician)—consistent with REB-approved procedures.

Plan incident response: suspected breach, unauthorized access, model output causing harm—roles and notification steps per institutional policy.

## PHASE B — ETHICS SUBMISSION & INFRASTRUCTURE HARDENING (2 months: JUNE 1 2026 - JULY 31 2026)

Parallel: submit for review while building non-PHI prototype.

**B.1 Regulatory**

- Submit full REB application in RISe with data management and security attachments matching actual architecture.
- Respond to ORE clarification requests; revise protocol/consent as needed.

Obtain conditional or full approval before collecting identifiable PHI or linking feedback to identity.

**B.2 Privacy**

- Implement approved storage; verify backups are in approved locations and encrypted.
- Ensure no PHI in Git, public tickets, or unapproved chat tools; use secrets management and scrubbed logs in dev.
- If using UBC ARC or other HPC/GPU environments, confirm PHI/GPU rules with ARC and privacy/IT—before moving identifiable data to compute nodes.

Treat model checkpoints, optimizer states, and detailed training logs as sensitive (potential memorization of training data).

**B.3 Safety**

- Build deterministic overrides: rule-based escalation must be able to override model output for critical pathways.
- Version prompts and model IDs; tie releases to ethics-approved scope.

Start a scenario bank (adversarial and clinical edge cases) for repeatable testing

## PHASE C — CORE DEVELOPMENT WITH PHI (3 months: AUGUST 1 2026 - OCTOBER 31 2026)

**C.1 Regulatory**

- File REB amendments for new data uses, new recruitment channels, or new feedback/training procedures if necessary.

Document participant consent for secondary use (e.g., future analysis, publication, model improvement).

**C.2 Privacy**

- Enforce data minimization: collect only what the study requires; separate direct identifiers from analytic copies where feasible.
- Maintain audit trails for data access and significant system actions (who, when, what).

Review vendor/model changes (API versions, endpoints) for privacy impact.

**C.3 Safety**

- Integrate RAG with citations or explicit limits—reduce unsupported medical claims.
- Use sentiment and similar signals as assistive to emergency escalation.

Add agentic oversight or policy checks on high-risk turns in agentic workflows; log disagreements and safe defaults.

## PHASE D — HUMAN FEEDBACK & MODEL ITERATION (2 months: NOVEMBER 1 2026 - DEC 31 2026)

**D.1 Regulatory**

Ensure human feedback collection (tasks, duration, compensation) matches approved consent and TCPS expectations.

**D.2 Privacy**

- Isolate feedback datasets with same access controls as PHI; document linkage between participant ID and feedback records if applicable.

Secure checkpoint storage; restrict download/copy; plan retention for checkpoints per approval.

**D.3 Safety**

- Run regression tests after each prompt or model change using the scenario bank; track escalation rates and harmful-advice flags.

Red-team sessions (structured probing for harmful or policy-violating outputs); log the findings and planned mitigations.

## PHASE E — PILOT, MONITORING & CLOSE-OUT (3 MONTHS: JANUARY 1 2027 - MARCH 31 2027)

**E.1 Regulatory**

- Define stopping rules for the pilot (safety signals, protocol deviations) and obtain REB alignment if needed.

Plan publication ethics: what can be shared (aggregates, synthetic examples) without re-identification.

**E.2 Privacy**

- Execute secure destruction of data/checkpoints/logs per approval when retention periods end.

Archive non-identifying research records as required by institution and funder.

**E.3 Safety**

- Operate monitoring during pilot (latency, errors, escalations, harmful outputs); incident log.

Post-study review: lessons for governance, model limitations, and handoff if work continues.

## Standing items (ongoing across all phases)

**Regulatory**

Keep TCPS 2 principles visible: respect for persons, concern for welfare, justice. Reassess Health Canada medical device / SaMD implications if intended use shifts toward clinical decision support or deployment outside pure research.

**Privacy**

FIPPA (BC public bodies, including UBC in many research contexts): ongoing accountability for personal information under institutional control. Track provincial/federal privacy developments; subprocessors and AI governance expectations may evolve.

**Safety**

Prompt injection / tool abuse: if agents use tools or retrieve text, mitigate retrieval of malicious instructions. Clinical safety: ongoing updates of guidelines and red-flag lists to stay current.
