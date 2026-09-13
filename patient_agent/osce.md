# Objective Structured Clinical Examination (OSCE), and how AgentClinic used it

## What an OSCE is

An **Objective Structured Clinical Examination** is a standard format in medical education (Harden, 1975; still used in Canadian and many other licensing pathways). Candidates rotate through timed **stations**. Each station is a controlled clinical task with three properties that matter for us:

1. **A specific objective.** The candidate is told what to do (“take a history of this patient’s back pain and decide urgency”), not given the diagnosis.
2. **A standardized patient (the actor).** A person with a script: history they may disclose, findings they can demonstrate, facts they must not volunteer, and a diagnosis they do **not** know.
3. **Partitioned information and a checklist.** The examiner has a marking scheme and the hidden diagnosis. The actor does not. Physical findings and test results are available only if the candidate elicits or orders them.

The point of the OSCE is **objectivity under incomplete information**: every candidate faces the same case, but must gather the case through interaction rather than reading a completed vignette. That is why AgentClinic borrowed the name.

It is **not** the same as a USMLE multiple-choice question. A MedQA item already dumps symptoms, exam, and labs into one paragraph and asks “what is the diagnosis?” An OSCE station withholds that bundle and scores *how* the candidate obtains it.

## How AgentClinic used the OSCE

AgentClinic’s claim is that static medical QA is a poor test of clinical agents. They convert diagnostic questions into **OSCE templates**: structured JSON “stations” that split one case across four LLM agents.

### Source cases

They start from diagnostic questions that already have a ground-truth answer:

| Split | Source | Role |
|---|---|---|
| AgentClinic-MedQA | USMLE / MedQA (215 cases in the published version) | General diagnosis via dialogue |
| AgentClinic-MIMIC-IV | De-identified EHR (PhysioNet DUA) | Real clinical profiles |
| AgentClinic-NEJM | 120 NEJM case challenges (from 932) | Multimodal: dialogue + images |
| AgentClinic-Spec | MedMCQA case reports | 9 specialties |
| AgentClinic-Lang | MedQA translated + native-speaker check | 7 languages |

The excerpt in `temp_excerpt.txt` is the published methods paragraph for this conversion.

### Conversion pipeline

1. Sample a diagnostic question (symptoms + hidden diagnosis).
2. **GPT-4 populates** a structured JSON OSCE file from that vignette.
3. **Humans manually validate** every case.
4. At runtime, **each agent sees only its slice** of the JSON.

Figure 2 in the paper is: USMLE question → OSCE JSON → LLM patient actor.

### The JSON station (information partition)

From Appendix C of the arXiv paper and `agentclinic_medqa.jsonl`:

```
OSCE_Examination
├── Objective_for_Doctor          → doctor agent only
├── Patient_Actor                 → patient agent only
│     Demographics
│     History
│     Symptoms (Primary, Secondary)
│     Past_Medical_History
│     Social_History
│     Review_of_Systems
├── Physical_Examination_Findings → measurement agent only
├── Test_Results                  → measurement agent only
└── Correct_Diagnosis             → moderator only
```

This is the OSCE idea in software: the patient actor knows history and symptoms and **does not** know the diagnosis or the hidden labs; the doctor starts with a one-line objective; the examiner (moderator) holds the answer key.

A real MedQA example (myasthenia gravis station) gives the patient:

- *35-year-old female; 1-month double vision, difficulty climbing stairs, hair-brushing weakness; worse after activity, better after rest; no significant PMH; graphic designer; denies chest pain / SOB / recent infection*

and withholds acetylcholine-receptor antibodies, EMG, and the diagnosis “myasthenia gravis.”

### Patient agent (what they actually prompt)

From the released `PatientAgent` in [agentclinic.py](https://github.com/SamuelSchmidgall/AgentClinic/blob/main/agentclinic.py):

> You are a patient in a clinic who only responds in the form of dialogue. You are being inspected by a doctor who will ask you questions and will perform exams on you in order to understand your disease. Your answer will only be 1-3 sentences in length.
>
> Below is all of your information. {Patient_Actor JSON}. Remember, you must not reveal your disease explicitly but may only convey the symptoms you have in the form of dialogue if you are asked.

Optional **bias** sentences are prepended (self-diagnosis, recency, race, gender, education, …). Dialogue history is concatenated each turn. Temperature is low (0.05). Default cap is **N = 20** doctor turns.

They do **not** fine-tune a patient model. Grounding is the OSCE card plus the prompt.

### How the station is scored

- Doctor may talk to the patient **or** request tests from the measurement agent (each request counts as a turn).
- After N turns, the doctor must give a diagnosis.
- A **moderator** LLM compares that text to `Correct_Diagnosis` and answers only Yes/No (handles “PE” = pulmonary embolism, etc.).
- Extra metrics from the **patient** after the visit: confidence, compliance, consultation (1–10).
- Three clinicians rated 20 English MedQA dialogues (1–10): Doctor 6.2, **Patient 6.7**, Measurement 6.3, Empathy 5.8. Patient-actor complaints: **overly verbose**, repeating the doctor’s question.

### Findings that matter for our design

- Static MedQA accuracy was **only weakly predictive** of AgentClinic accuracy (same cases, interactive format). That is the OSCE lesson: giving the whole vignette up front is a different task.
- Average **coverage** of MedQA facts elicited in dialogue was 67% (72% when the diagnosis was correct, 63% when wrong). Incomplete disclosure changes outcomes.
- GPT-4 patients produced **more new symptomatic detail** than GPT-3.5 patients, who often echoed the question. Choice of patient backbone changes the test.
- N = 10 turns cut accuracy from 52% to 25%; N = 30 slightly *hurt* (context length). Turn budget is a design parameter.
- Clinician realism of the patient actor was only **6.7/10**. The OSCE card grounds *content*; it does not automatically produce genuine speech.

### Persona (PatientSim axes, DigiMSK card)

AgentClinic’s published `Patient_Actor` has no persona object. We add a closed `persona` block after sampling, following PatientSim (Kyung et al., NeurIPS 2025): talking style is orthogonal to the clinical profile.

| Key | Allowed values |
|---|---|
| `personality` | `impatient`, `overanxious`, `distrustful`, `overly_positive`, `verbose`, `neutral` |
| `language_proficiency` | `basic`, `intermediate`, `advanced` |
| `medical_history_recall` | `high_recall`, `low_recall` |
| `cognitive_confusion` | `highly_confused`, `normal` |

Default on stub cards: `neutral` / `advanced` / `high_recall` / `normal`. Persona must not add clinical facts.

`Hidden.reference_labels` is a closed scoring family. Allowed: `mechanical`, `CES`, `fracture`, `malignancy`, `infection`, `vascular`. Leave `[]` until a clinician assigns. DigiMSK Hidden does **not** include `objective_for_bot`, exam, labs, or `correct_diagnosis`.

## What this is not (for DigiMSK)

AgentClinic’s OSCE is a **diagnostic clinic**: doctor + labs + images + open-ended disease label. DigiMSKbot is a **text-only LBP triage chatbot**: it asks until coverage slots are filled, then gives a disposition (home / pharmacy / GP / urgent / ED). We should keep the OSCE *partition* (actor card vs hidden answer) and drop the parts that assume a physician with a measurement agent.
