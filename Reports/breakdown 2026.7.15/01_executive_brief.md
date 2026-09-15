# TRI-BACK — Executive Brief

TRI-BACK is a **musculoskeletal triage chatbot** for a research study. A simple chat website talks to a clinical engine on our servers. That engine builds a **checklist** of what the person told us, asks follow-up questions when needed, then offers a **care recommendation**. Rules and evidence decide the path; an AI language model (Google Vertex Gemini, or a local backup model) only helps with **wording**.

## What happens in a conversation

After each message, the system updates the checklist (for example age, pain severity, what helps or worsens symptoms). Then it chooses one of three paths:

- **Question mode** — Important details are still missing. The system picks the next topic and asks **one** question.
- **Disposition mode** — Enough information is in. Local evidence is gathered, a recommendation is drafted, and a safety check can override it if needed.
- **Escalate** — Certain high-risk patterns appear. The person gets a fixed urgent-care message (no open-ended advice).

The research study compares three display styles (**arms**). All three use the **same** clinical engine. Only the screen layout changes after the recommendation:

- **Arm 1** — Short recommendation only
- **Arm 2** — Recommendation plus a short plain-language explanation
- **Arm 3** — Recommendation plus a visual knowledge-graph panel

## On our machines vs the AI model

**Runs here (local):** reading the message, filling the checklist, deciding whether to ask or advise, searching local evidence libraries, safety overrides, and study-arm display.

**AI model (Vertex Gemini):** phrasing the next question, optionally suggesting checklist details that code must still accept, and drafting recommendation text from evidence it was given.

Evidence search and safety stay local. The model does not choose the next clinical topic, does not search the open internet, and cannot skip the safety gate.

## Simple rule of thumb

**Checklist in → question or advice out. Code steers. The model writes sentences.**

Study chats are saved as session files for analysis (including checklist and optional explanations). Citation chips are not shown in the chat screen. There is no WhatsApp channel yet; the live path is the study website to the bot API.
