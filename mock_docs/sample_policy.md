# Katalon Internal Policy & Overview

Welcome to the Katalon internal knowledge base. This policy document serves as the official reference guide covering standard software testing guidelines, version control practices, CI/CD deployment protocols, and data security standards for all engineering team members.

---

## 1. Introduction to Brok Knowledge Assistant
Brok is your internal enterprise AI assistant designed to help developers, testers, and project managers navigate technical documentation, architectural standards, and team workflows efficiently. Always verify critical deployments and security policies with senior engineering leadership.

---

## 2. Software Testing Guidelines
All code contributions must adhere to high-quality software reliability standards before merging into production branches.

* **Test Coverage Requirements:** 
  * Core backend modules and services must maintain a minimum unit test coverage of **80%**.
  * Integration tests are required for all external API connectors and database queries.
* **Testing Frameworks & Execution:**
  * Backend services utilize `pytest` for unit and integration testing.
  * Automated end-to-end (E2E) UI and API testing must be executed using Katalon Studio and REST Assured.
* **Bug Reporting & Triage:**
  * Critical bugs must be logged in Jira with reproduction steps, environment logs, and affected component tags within 2 hours of discovery.

---

## 3. Version Control & Git Workflow
To ensure smooth collaboration across distributed engineering teams, all repositories follow a standardized Git branching strategy.

* **Branch Naming Conventions:**
  * Feature branches: `feature/short-description` (e.g., `feature/rag-vector-search`)
  * Bug fixes: `bugfix/issue-id-description` (e.g., `bugfix/102-socket-timeout`)
  * Release branches: `release/vX.X.X`
* **Pull Request (PR) Requirements:**
  * Every PR requires at least **two peer reviews** from core team members before merging into `main` or development branches.
  * PR descriptions must include a summary of changes, testing verification steps, and Jira ticket links.
* **Commit Message Standards:**
  * Use clear, imperative mood headers (e.g., `feat: add pgvector connection fallback`, `fix: resolve uvicorn container exit code 127`).

---

## 4. Deployment & CI/CD Protocols
Deployment to staging and production environments is fully automated via containerized CI/CD pipelines.

* **Containerization & Runtime:**
  * All services must be packaged using Docker and deployed via modern cloud runtimes such as Fly.io or Supabase.
  * Production web servers must run on **Uvicorn** with asynchronous ASGI configurations rather than synchronous WSGI servers.
* **Staging Environment Validation:**
  * Changes are automatically deployed to the staging environment upon merging into the development branch.
  * Smoke tests and health checks (`/health`) must return `200 OK` before promotion to production.
* **Rollback Procedures:**
  * In the event of a deployment failure or infinite crash loop (such as exit code 127), engineers must inspect live machine logs (`fly logs`) and utilize `fly deploy --strategy rolling` to revert to the last stable release.

---

## 5. Security & PII Compliance
Protecting customer data and internal intellectual property is a core engineering mandate.

* **Environment Variables & Secrets:**
  * Never hardcode API keys, database connection strings, or Slack tokens (`xoxb`, `xapp`) into source code.
  * All sensitive credentials must be managed via secure environment variables or platform secret managers (`fly secrets set`).
* **Personally Identifiable Information (PII):**
  * Ingestion pipelines must apply sanitization and masking techniques to strip raw PII logs before storing text chunks in vector databases.