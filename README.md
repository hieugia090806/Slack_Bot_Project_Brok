# Internal Assistant for Enterprise Knowledge (Slack App Bot)

A Retrieval-Augmented Generation (RAG) assistant that lives inside Slack and answers employees' questions from internal knowledge sources, starting with Confluence, in **English and Vietnamese**, with **source citations** and **deny-by-default channel whitelisting**.

> **Unit:** COS40005 Computing Technology Project A, Swinburne University of Technology
> **Client / sponsor:** Mr. Phat (Eric) Pham, Cloud Solutions Architect, Vietnam International Bank (VIB), via the AWS First Cloud Journey (FCAJ) programme
> **Project manager:** Truong Ngoc Gia Hieu
> **Timeline:** 29 September 2026 to 6 December 2026
> **Release in progress:** Alpha (proof of concept, Project A, Weeks 5 to 12)

---

## Table of Contents

1. [Project Status](#project-status)
2. [Background and Problem](#background-and-problem)
3. [Goals and Success Metrics](#goals-and-success-metrics)
4. [Scope](#scope)
5. [System Architecture](#system-architecture)
6. [Technology Stack](#technology-stack)
7. [Planned Repository Structure](#planned-repository-structure)
8. [Getting Started](#getting-started)
9. [Requirements Summary](#requirements-summary)
10. [Delivery Plan](#delivery-plan)
11. [Team and Workflow](#team-and-workflow)
12. [Project Documents](#project-documents)
13. [Risks, Constraints and Cost](#risks-constraints-and-cost)
14. [Security and Data Handling](#security-and-data-handling)
15. [Roadmap Beyond Alpha](#roadmap-beyond-alpha)
16. [References](#references)
17. [License](#license)
18. [Contact](#contact)

---

## Project Status

The project is in the **planning and set-up phase**. Sprint 1 (Weeks 5 to 6) covered initiation, the repository, the Slack and Confluence sandboxes and the architecture decisions. Build work starts in Sprint 2 (Week 7).

At the time of writing this repository contains the project documentation only (see [Project Documents](#project-documents)). Source code is added as each sprint delivers. Sections marked **(planned)** describe the intended design, not finished work.

## Background and Problem

Company knowledge is spread across several disconnected places: Confluence spaces (for example Products, Legal, Policies and Benefits), documentation sites, project repositories and forums. Employees lose time searching, switch context away from their main communication tool, and ask colleagues the same questions repeatedly. General search tools also do not make it clear whether the person asking is allowed to see a given document.

This project builds a Slack-native assistant that gives accurate, cited answers from the knowledge base while keeping access inside approved channels.

## Goals and Success Metrics

| Goal | Target |
|------|--------|
| Retrieval and answer accuracy | At least **80%** on an agreed bilingual (English and Vietnamese) test set, in each language |
| Response time | Average **under 3 seconds** end to end per Slack interaction |
| Whitelist compliance | **100%** adherence to channel isolation; no answers outside whitelisted channels |
| Search-time reduction | About **40%** improvement in information retrieval speed during pilot evaluation |
| Cost | **Zero additional spend** during the proof-of-concept phase |

Accuracy is graded against a written checklist (pass, partial or fail) by two independent graders. Latency is reported as mean, median and 95th percentile.

## Scope

**In scope (Alpha)**
- REST-based Confluence ingestion that fetches pages from selected spaces and converts the HTML (including tables and macros) into clean Markdown
- Handling of embedded image assets associated with pages
- Chunking, multilingual (English and Vietnamese) embeddings and indexing into a local vector database
- A Slack app built with the Bolt SDK in **Socket Mode** that answers `@mentions` in threads
- RAG engine with prompt templates that require source citations, language detection and a fallback reply when no relevant context is found
- Security middleware: channel-level whitelist (deny by default) and Slack Single Sign-On user validation
- Handover pack: source code, architecture designs, deployment instructions, test evidence and a Technical Specification Document

**Out of scope for this phase**
- Deployment and hosting on VIB's production cloud environment
- Mobile apps or platforms other than Slack
- Department-specific assistants and advanced production log management
- Ongoing maintenance, support or infrastructure provisioning after the agreed handover

## System Architecture

The solution is a secure, modular RAG pipeline with four layers.

```
                 Slack workspace (employee asks via @mention)
                                   |
                                   v
 +--------------------------------------------------------------+
 | 1. Presentation layer: Slack Bolt app (Socket Mode)          |
 |    app_mention events, Block Kit answers, clickable sources  |
 +--------------------------------------------------------------+
                                   |
                                   v
 +--------------------------------------------------------------+
 | 2. Security and authentication middleware                    |
 |    channel whitelist (deny by default) + Slack SSO validation|
 +--------------------------------------------------------------+
                                   |
                                   v
 +--------------------------------------------------------------+
 | 3. RAG core and business logic                               |
 |    language detection -> retrieval -> LLM answer with        |
 |    mandatory citations -> fallback if nothing relevant       |
 +--------------------------------------------------------------+
                                   |
                                   v
 +--------------------------------------------------------------+
 | 4. Data ingestion and storage                                |
 |    Confluence REST API -> HTML to Markdown -> chunk ->       |
 |    multilingual embeddings -> vector database                |
 +--------------------------------------------------------------+
```

**Design principles**
- **Swappable adapters.** The knowledge source, vector store and LLM are reached through small adapter interfaces, so each can be replaced without touching the core.
- **Pipeline of understanding, decision and generation.** Language detection and query clean-up act as the understanding step, retrieval with a fallback reply as the decision step, and the cited LLM answer as the generation step.
- **No public endpoints in the PoC.** Socket Mode uses a persistent WebSocket connection, so no public webhook, domain or SSL set-up is needed during development. An HTTP Events API option will be described in the specification for production hosting.

**Alternatives considered and not chosen:** commercial enterprise search (Slack AI, Atlassian Rovo) because of subscription cost and limited customisation; the HTTP Events API for the PoC because it needs public infrastructure; and direct LLM prompting without retrieval because of hallucination risk and no access to private, changing content.

## Technology Stack

| Area | Choice | Status |
|------|--------|--------|
| Language | Python | Decided |
| Slack integration | Slack Bolt SDK, Socket Mode, Block Kit | Decided |
| Knowledge source | Confluence REST API (mock space `VIB-Mock-Knowledge` for development) | Decided |
| Embeddings | Multilingual (English and Vietnamese) embedding model | Model to be selected |
| Vector store | Qdrant, Chroma or FAISS, versus PostgreSQL with pgvector | **Open**, decision record due Week 7 |
| LLM | Local open-source model via Ollama, or an approved API (for example AWS Bedrock) | **Open**, decision record due Week 7 |
| Orchestration | LangChain or LlamaIndex (or a thin custom layer) | To be confirmed |
| Environment | Containerised development environment | Planned |

The decision rule for the open items is: choose the smallest stack that meets the accuracy and under-3-second targets on the team's hardware at zero cost, with metadata filtering available for access control.

## Planned Repository Structure

This is the intended layout. Folders are created as the related sprint work lands.

```
Slack_Bot_Project_Brok/
├── Documents/              # Charter, proposal, plan, minutes, reference papers (present)
├── src/
│   ├── slack_app/          # Bolt app, Socket Mode, event handlers (planned)
│   ├── security/           # Channel whitelist and SSO middleware (planned)
│   ├── rag/                # Retriever, prompts, language handling (planned)
│   ├── ingestion/          # Confluence connector, HTML to Markdown, chunking (planned)
│   └── adapters/           # Source, vector store and LLM interfaces (planned)
├── config/                 # Whitelist, spaces, model and index settings (planned)
├── tests/                  # Parser, middleware, retrieval and benchmark tests (planned)
├── docker/                 # Containerised dev environment (planned)
├── .env.example            # Placeholder variable names only, never real secrets (planned)
└── README.md
```

## Getting Started

Setup instructions will be finalised when the Sprint 2 code lands. The expected prerequisites are:

- Python 3.10 or later
- A Slack workspace where you can create an app with Socket Mode enabled
- Access to a Confluence space (the team uses the mock space `VIB-Mock-Knowledge`)
- Docker (for the local vector database)
- Optionally, [Ollama](https://ollama.com) for a local LLM

Configuration is kept in configuration files and environment variables, never in code. **Do not commit tokens, API keys or secrets.** Secret scanning runs on every pull request.

```bash
git clone https://github.com/hieugia090806/Slack_Bot_Project_Brok.git
cd Slack_Bot_Project_Brok
```

## Requirements Summary

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 to FR4 | Fetch Confluence pages with metadata, convert to clean Markdown, handle images, chunk and index with multilingual embeddings | High |
| FR5 | Respond to `@mentions` in a Slack thread through a Bolt app in Socket Mode | High |
| FR6 to FR8 | Retrieve relevant chunks, generate an answer with an LLM, include at least one clickable Confluence citation, and answer in the language of the question | High |
| FR9 | Clear fallback message when no relevant context is found | Medium |
| FR10 and FR11 | Process only whitelisted channels (deny all others) and validate the asking user through Slack SSO | High |
| FR12 and FR13 | Block Kit formatting; cache frequent responses to protect response time | Medium and High |
| FR14 | Whitelist, spaces, model and index settings live in configuration, not in code | High |

**Non-functional highlights:** at least 80% accuracy per language; mean response under 3 seconds; 100% whitelist compliance with no secrets in the repository; only mock or approved low-sensitivity data in development; graceful behaviour when the LLM or vector database is unavailable, with Socket Mode reconnection; swappable adapters; zero additional spend.

## Delivery Plan

Project A follows two-week sprints (Sprints 1 to 4 cover Weeks 5 to 12).

| Phase | Weeks | Focus |
|-------|-------|-------|
| Sprint 1: Initiation | 5 to 6 | Charter, proposal, plan, GitHub repository, Slack and Confluence sandboxes, architecture research |
| Sprint 2: Data foundation, Slack gateway and security | 7 to 8 | Confluence ingestion, Markdown conversion, embeddings and indexing, Bolt and Socket Mode app, channel whitelist, SSO validation |
| Sprint 3: RAG core and integration | 9 to 10 | Retriever and LLM, citation prompts, bilingual handling, Slack integration, accuracy, latency and security validation |
| Sprint 4: Specification and handover | 11 to 12 | Technical Specification Document sent to Mr. Phat on **2 December 2026**; project handover on **6 December 2026** |

## Team and Workflow

| Member | Role |
|--------|------|
| Truong Ngoc Gia Hieu | Project manager; repository, backlog, risk register and client liaison |
| Pham Nguyen Minh Hoang | Slack framework investigation and interface |
| Nguyen Quang Khai | Team member |
| Lu Nhat Hoang | Team member |
| Duong Nguyen Dang | Team member |
| Le Xuan Ny | Documentation coordination |

Role labels beyond the project manager are proposals recorded in the Team and Project Plan, and members confirm or correct them there.

**Git workflow**
- `main` is protected and reserved for showcase-ready releases. **No direct pushes to `main`.**
- `develop` is the main integration branch.
- All work happens on `feature/*` branches and is merged through pull requests with **at least one peer review**.
- Use semantic commit messages (for example `feat: add Confluence connector`, `fix: handle empty page body`).

## Project Documents

All planning documents are in the [`Documents/`](Documents/) folder.

| Document | Purpose |
|----------|---------|
| Project Proposal | Summary, desired outcome, schedule, budget and resources |
| Project Charter | Scope, goals and metrics, milestones, costs, risks and assumptions |
| Project Team and Project Plan | Team code of conduct, requirements, architecture, backlog, quality plan, risk register |
| Project Description Summary | Allocated projects for the September 2026 intake (this project is VIB 1) |
| Meeting minutes, 22 October 2026 | Open decisions on platform costs, framework and architecture |
| Chatbot System Architecture (reference paper) | Generic NLU, dialogue manager and generator architecture |
| A Repository-First Framework for Democratizing Chatbot Development (reference paper) | Layered design with swappable adapters |

## Risks, Constraints and Cost

- **Zero-cost constraint.** The PoC relies on free-tier and open-source tools. The 22 October meeting recorded that subscription options for Slack and Confluence are still under review and no cost decision has been made.
- **Fixed timeline.** Twelve weeks, with the specification due on 2 December.
- **Hard-to-parse content.** Confluence pages with HTML tables, macros and embedded images need dedicated conversion.
- **LLM latency and throttling.** Mitigated with response caching and optimised retrieval.
- **Hardware limits.** Local models need enough memory; the team uses containerised environments and shared index snapshots, with local fallbacks (Socket Mode and Ollama) if free-tier services are down.
- **Future production cost.** Estimated at roughly 50 to 85 USD per month for cloud hosting, a managed vector database and LLM tokens; this is outside the PoC.

The full risk register (with likelihood, impact, mitigation and owner) is in the Team and Project Plan.

## Security and Data Handling

- Channel whitelist is **deny by default**; the bot ignores every channel not explicitly approved.
- Slack SSO validates the identity of the asking user before an answer is returned.
- Development uses **mock or approved low-sensitivity data only**. No personal data goes into logs or the repository.
- Secrets live in environment variables and are never committed.
- Access control by document-level role is a Beta feature (see below).

## Roadmap Beyond Alpha

Beta features, not part of the Alpha release: context re-ranking, conversation memory, role-based access control, incremental synchronisation, additional data sources (GitHub repositories and internal documents), audit logging, user feedback buttons and a production-readiness plan.

## References

1. M. Mohammed and M. M. Aref, "Chatbot System Architecture," Ain Shams University.
2. Boonsri and Buranasaksee, "A Repository-First Framework for Democratizing Chatbot Development."

Full reference lists are in the Team and Project Plan.

## License

This is an academic project for COS40005 at Swinburne University of Technology. A licence has not yet been chosen; until one is added, all rights are reserved by the authors. Client data and VIB materials must not be published.

## Contact

**Truong Ngoc Gia Hieu** (Project Manager)
Email: giahieutruongngoc@gmail.com
GitHub: [hieugia090806](https://github.com/hieugia090806)
