#!/usr/bin/env python3
"""
Company presets for demo data generation, analytics, and advising.

Each preset defines: company name, employees, topics (with keywords and ranges),
projects, struggle signals, team-wide weaknesses, and curated advisor sources.

Active preset is controlled by data/.active_preset (default: "startup").
"""

from __future__ import annotations

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "data")
PRESET_FILE = os.path.join(DATA_DIR, ".active_preset")


# ═══════════════════════════════════════════════════════════════════════════
# PRESET 1: Vague Tech Startup
# ═══════════════════════════════════════════════════════════════════════════

STARTUP = {
    "name": "startup",
    "company": "Valon AI",
    "description": "General-purpose SaaS startup building a platform product",

    "employees": [
        "Alice Chen", "Bob Martinez", "Carol Nguyen", "Dave Patel", "Eve Kim",
        "Frank Johnson", "Grace Liu", "Hank Williams", "Iris Tanaka", "Jake Brown",
        "Kara Singh", "Leo Garcia", "Mia Robinson", "Nate Foster", "Olivia Park",
        "Paul Davis", "Quinn Adams", "Rosa Hernandez", "Sam Wright", "Tina Brooks",
    ],

    "employee_models": {
        "Alice Chen": "claude-sonnet-4",   "Bob Martinez": "gpt-4o",
        "Carol Nguyen": "cursor-default",  "Dave Patel": "claude-opus-4",
        "Eve Kim": "gemini-2.5-pro",       "Frank Johnson": "github-copilot",
        "Grace Liu": "claude-sonnet-4",    "Hank Williams": "o4-mini",
        "Iris Tanaka": "deepseek-v3",      "Jake Brown": "gpt-4o",
        "Kara Singh": "claude-haiku-4",    "Leo Garcia": "cursor-default",
        "Mia Robinson": "claude-sonnet-4", "Nate Foster": "windsurf-default",
        "Olivia Park": "claude-opus-4",    "Paul Davis": "gemini-2.5-flash",
        "Quinn Adams": "github-copilot",   "Rosa Hernandez": "aider-default",
        "Sam Wright": "gpt-4o",            "Tina Brooks": "deepseek-r1",
    },

    "projects": {
        "Valon-Platform":  {"key": "VAL",   "components": ["auth", "billing", "api-gateway", "notifications"]},
        "Valon-Servicing": {"key": "ENG",   "components": ["loan-ops", "payments", "escrow", "investor-reporting"]},
        "Valon-Portal":    {"key": "DATA",  "components": ["borrower-ui", "admin-dashboard", "document-upload"]},
        "Valon-DataHub":   {"key": "ML",    "components": ["etl-pipelines", "feature-store", "model-registry", "analytics"]},
        "Valon-InfraCore": {"key": "INFRA", "components": ["k8s-cluster", "ci-cd", "monitoring", "secrets-mgmt"]},
    },

    "epics": [
        {"key": "VAL-EPIC-1",  "name": "New Onboarding Platform",         "project": "Valon-Portal",    "topics": ["Frontend Development", "Backend API Development", "Security & Auth", "Database & Schema Design"], "ticket_count": 35, "status": "in_progress", "target_date": "2025-08-15"},
        {"key": "ENG-EPIC-2",  "name": "Cloud to On-Prem Migration",      "project": "Valon-InfraCore", "topics": ["Cloud Infrastructure", "CI/CD & DevOps", "Security & Auth", "Database & Schema Design"], "ticket_count": 28, "status": "in_progress", "target_date": "2025-09-01"},
        {"key": "ML-EPIC-3",   "name": "ML Model Serving Pipeline v2",    "project": "Valon-DataHub",   "topics": ["ML & AI Integration", "Data Engineering", "Performance Optimization", "Monitoring & Observability"], "ticket_count": 22, "status": "in_progress", "target_date": "2025-07-30"},
        {"key": "VAL-EPIC-4",  "name": "SOC2 Compliance Overhaul",        "project": "Valon-Platform",  "topics": ["Security & Auth", "Testing & QA", "Code Review & Refactoring", "Monitoring & Observability"], "ticket_count": 40, "status": "planning", "target_date": "2025-10-01"},
        {"key": "DATA-EPIC-5", "name": "Real-time Analytics Dashboard",    "project": "Valon-DataHub",   "topics": ["Frontend Development", "Data Engineering", "Backend API Development", "Performance Optimization"], "ticket_count": 18, "status": "done", "target_date": "2025-05-15"},
        {"key": "ENG-EPIC-6",  "name": "Billing System Rewrite",          "project": "Valon-Servicing", "topics": ["Backend API Development", "Database & Schema Design", "Testing & QA", "Security & Auth"], "ticket_count": 30, "status": "in_progress", "target_date": "2025-08-30"},
    ],

    "topics": {
        "Backend API Development": {
            "keywords": [
                "python", "fastapi", "django", "rest-api", "graphql", "endpoint",
                "serializer", "middleware", "authentication", "rate-limiting",
                "pagination", "versioning", "microservice", "grpc", "webhook",
                "request-handling", "response-model",
            ],
            "duration_range": (30, 120),
            "token_range": (800, 3500),
        },
        "Frontend Development": {
            "keywords": [
                "react", "typescript", "nextjs", "component", "state-management",
                "hooks", "redux", "css-modules", "tailwind", "responsive",
                "accessibility", "webpack", "vite", "storybook", "jsx",
                "client-side", "dom",
            ],
            "duration_range": (25, 100),
            "token_range": (600, 2800),
        },
        "Database & Schema Design": {
            "keywords": [
                "postgresql", "mysql", "schema", "migration", "index",
                "query-optimization", "orm", "sqlalchemy", "normalization",
                "foreign-key", "partitioning", "replication", "read-replica",
                "connection-pool", "transaction", "deadlock", "vacuum",
            ],
            "duration_range": (35, 130),
            "token_range": (700, 3200),
        },
        "CI/CD & DevOps": {
            "keywords": [
                "github-actions", "terraform", "ansible", "docker", "kubernetes",
                "helm", "ci-pipeline", "cd-pipeline", "deployment", "rollback",
                "blue-green", "canary", "artifact", "registry", "iac",
                "provisioning", "secrets-management",
            ],
            "duration_range": (20, 90),
            "token_range": (500, 2200),
        },
        "Testing & QA": {
            "keywords": [
                "pytest", "unit-test", "integration-test", "e2e", "coverage",
                "mocking", "fixtures", "snapshot-test", "regression", "flaky-test",
                "test-plan", "assertion", "parametrize", "load-test", "contract-test",
                "mutation-testing", "tdd",
            ],
            "duration_range": (15, 75),
            "token_range": (400, 1800),
        },
        "Security & Auth": {
            "keywords": [
                "oauth2", "jwt", "rbac", "encryption", "tls", "cors",
                "csrf", "xss", "sql-injection", "secrets-rotation", "vault",
                "sso", "mfa", "penetration-test", "vulnerability-scan",
                "compliance", "audit-log",
            ],
            "duration_range": (40, 150),
            "token_range": (900, 4000),
        },
        "Data Engineering": {
            "keywords": [
                "etl", "pipeline", "airflow", "dbt", "spark", "kafka",
                "data-lake", "warehouse", "snowflake", "bigquery", "parquet",
                "avro", "batch-processing", "streaming", "data-quality",
                "lineage", "orchestration",
            ],
            "duration_range": (30, 120),
            "token_range": (700, 3000),
        },
        "ML & AI Integration": {
            "keywords": [
                "model-training", "inference", "fine-tuning", "embeddings",
                "vector-db", "rag", "prompt-engineering", "llm", "transformer",
                "feature-engineering", "evaluation", "mlops", "model-serving",
                "a-b-test-ml", "hyperparameter", "tokenizer", "langchain",
            ],
            "duration_range": (45, 180),
            "token_range": (1200, 5000),
        },
        "Performance Optimization": {
            "keywords": [
                "profiling", "caching", "redis", "memcached", "latency",
                "throughput", "bottleneck", "flame-graph", "memory-leak",
                "connection-pool", "lazy-loading", "cdn", "compression",
                "concurrency", "async", "batch", "denormalization",
            ],
            "duration_range": (35, 140),
            "token_range": (800, 3500),
        },
        "Cloud Infrastructure": {
            "keywords": [
                "aws", "gcp", "azure", "ec2", "s3", "lambda", "iam",
                "vpc", "load-balancer", "auto-scaling", "cloudformation",
                "cost-optimization", "multi-region", "disaster-recovery",
                "service-mesh", "api-gateway", "dns",
            ],
            "duration_range": (25, 110),
            "token_range": (600, 2800),
        },
        "Monitoring & Observability": {
            "keywords": [
                "datadog", "grafana", "prometheus", "alerting", "logging",
                "tracing", "opentelemetry", "slo", "sli", "sla", "incident",
                "runbook", "dashboard", "pagerduty", "metrics", "apm",
                "structured-logging",
            ],
            "duration_range": (15, 70),
            "token_range": (400, 1600),
        },
        "Code Review & Refactoring": {
            "keywords": [
                "pull-request", "code-review", "refactor", "tech-debt",
                "linting", "static-analysis", "type-checking", "mypy",
                "eslint", "prettier", "dry", "solid", "design-pattern",
                "abstraction", "modularization", "deprecation", "cleanup",
            ],
            "duration_range": (10, 55),
            "token_range": (300, 1400),
        },
    },

    "struggle_signals": {
        ("Bob Martinez", "Security & Auth"):        {"duration_mult": 2.4, "token_mult": 2.6},
        ("Iris Tanaka", "ML & AI Integration"):     {"duration_mult": 2.2, "token_mult": 2.5},
        ("Paul Davis", "Database & Schema Design"): {"duration_mult": 2.0, "token_mult": 2.3},
        ("Dave Patel", "Frontend Development"):     {"duration_mult": 1.6, "token_mult": 1.7},
        ("Grace Liu", "Data Engineering"):          {"duration_mult": 1.5, "token_mult": 1.6},
        ("Quinn Adams", "Backend API Development"): {"duration_mult": 1.4, "token_mult": 1.5},
        ("Quinn Adams", "CI/CD & DevOps"):          {"duration_mult": 1.5, "token_mult": 1.4},
        ("Quinn Adams", "Testing & QA"):            {"duration_mult": 1.4, "token_mult": 1.4},
        ("Quinn Adams", "Cloud Infrastructure"):    {"duration_mult": 1.4, "token_mult": 1.5},
        ("Mia Robinson", "Performance Optimization"): {"duration_mult": 1.6, "token_mult": 1.8},
    },

    "team_wide_struggles": {
        "Security & Auth":      {"duration_mult": 1.4, "token_mult": 1.5, "error_boost": 4},
        "ML & AI Integration":  {"duration_mult": 1.3, "token_mult": 1.4, "error_boost": 3},
    },

    "curated_sources": {
        "Security & Auth": {
            "standards": ["OWASP Top 10 (2025)", "NIST Cybersecurity Framework", "CIS Benchmarks"],
            "tools": ["Snyk", "SonarQube", "Trivy", "HashiCorp Vault", "Semgrep", "Dependabot"],
            "training": ["PortSwigger Web Security Academy (free)", "OWASP WebGoat", "Hack The Box"],
            "practices": ["shift-left security scanning in CI", "secret rotation automation", "RBAC with least-privilege"],
        },
        "ML & AI Integration": {
            "standards": ["MLOps maturity model (Google)", "Responsible AI practices"],
            "tools": ["MLflow", "Weights & Biases", "DVC", "LangChain", "vLLM", "Hugging Face Transformers"],
            "training": ["fast.ai (free)", "Hugging Face NLP Course (free)", "DeepLearning.AI short courses"],
            "practices": ["model versioning and experiment tracking", "prompt evaluation frameworks", "RAG pipeline testing"],
        },
        "Database & Schema Design": {
            "standards": ["Database reliability engineering principles"],
            "tools": ["Alembic", "Flyway", "pganalyze", "Atlas (Ariga)", "Bytebase"],
            "training": ["Use The Index, Luke (free)", "CMU Database Course (free videos)"],
            "practices": ["no-lock migrations", "query plan analysis", "connection pooling (PgBouncer)"],
        },
        "Frontend Development": {
            "standards": ["WCAG 2.2 accessibility", "Core Web Vitals"],
            "tools": ["Storybook", "Playwright", "Lighthouse CI", "Chromatic"],
            "training": ["Epic React (Kent C. Dodds)", "web.dev Learn (free)"],
            "practices": ["component-driven development", "visual regression testing", "bundle size budgets"],
        },
        "Performance Optimization": {
            "standards": ["Google SRE workbook perf chapters"],
            "tools": ["py-spy", "Locust", "k6", "Grafana Tempo", "Redis Insight"],
            "training": ["Systems Performance by Brendan Gregg", "High Performance Python"],
            "practices": ["continuous profiling in production", "load testing in CI", "latency budgets per endpoint"],
        },
        "Data Engineering": {
            "standards": ["Data mesh principles", "Data quality dimensions"],
            "tools": ["dbt", "Great Expectations", "Apache Airflow", "Dagster", "Delta Lake"],
            "training": ["Data Engineering Zoomcamp (free)", "dbt Learn (free)"],
            "practices": ["data contracts between teams", "pipeline idempotency", "data freshness SLAs"],
        },
        "CI/CD & DevOps": {
            "standards": ["DORA metrics", "12-factor app"],
            "tools": ["GitHub Actions", "ArgoCD", "Renovate", "Earthly"],
            "training": ["Google SRE Book (free)", "DevOps Handbook"],
            "practices": ["trunk-based development", "feature flags over long branches", "deploy frequency tracking"],
        },
        "Cloud Infrastructure": {
            "standards": ["AWS Well-Architected Framework"],
            "tools": ["Terraform", "Pulumi", "Infracost", "AWS Trusted Advisor"],
            "training": ["AWS Solutions Architect course", "Terraform Associate cert"],
            "practices": ["infrastructure as code review process", "cost tagging strategy", "DR runbooks"],
        },
        "Testing & QA": {
            "standards": ["Testing pyramid", "Shift-left testing"],
            "tools": ["pytest", "Playwright", "Testcontainers", "mutmut"],
            "training": ["Test-Driven Development by Example"],
            "practices": ["contract testing between services", "flaky test quarantine", "coverage gates in CI"],
        },
        "Monitoring & Observability": {
            "standards": ["OpenTelemetry specification", "SLO/SLI framework"],
            "tools": ["Grafana stack", "Datadog", "Honeycomb", "OpenTelemetry Collector"],
            "training": ["Observability Engineering (book)"],
            "practices": ["structured logging standard", "distributed tracing adoption", "SLO-based alerting"],
        },
        "Code Review & Refactoring": {
            "standards": ["Google Engineering Practices (code review guide)"],
            "tools": ["SonarQube", "CodeClimate", "Semgrep", "Sourcery"],
            "training": ["Refactoring by Martin Fowler"],
            "practices": ["PR size limits", "automated style enforcement"],
        },
        "Backend API Development": {
            "standards": ["OpenAPI 3.1", "gRPC best practices"],
            "tools": ["FastAPI", "Swagger/OpenAPI codegen", "Pact (contract testing)"],
            "training": ["API Design Patterns (book)", "FastAPI docs tutorial (free)"],
            "practices": ["API versioning strategy", "request validation at boundaries", "rate limiting"],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# PRESET 2: Fintech
# ═══════════════════════════════════════════════════════════════════════════

FINTECH = {
    "name": "fintech",
    "company": "NovaPay",
    "description": "Fintech company building payment infrastructure and lending products",

    "employees": [
        "Amir Hassan", "Brenda Zhao", "Carlos Mendez", "Diana Frost", "Elijah Okonkwo",
        "Fatima Al-Rashid", "George Petrov", "Hannah Olsen", "Ivan Kovac", "Julia Santos",
        "Kevin Tran", "Linda Park", "Marco Ricci", "Nina Johansson", "Oscar Blanco",
        "Priya Sharma", "Reuben Stein", "Sofia Andersson", "Tariq Hussain", "Uma Patel",
    ],

    "employee_models": {
        "Amir Hassan": "claude-opus-4",     "Brenda Zhao": "gpt-4o",
        "Carlos Mendez": "claude-sonnet-4", "Diana Frost": "cursor-default",
        "Elijah Okonkwo": "o3",             "Fatima Al-Rashid": "gemini-2.5-pro",
        "George Petrov": "claude-sonnet-4", "Hannah Olsen": "github-copilot",
        "Ivan Kovac": "deepseek-r1",        "Julia Santos": "claude-sonnet-4",
        "Kevin Tran": "gpt-4o",             "Linda Park": "windsurf-default",
        "Marco Ricci": "o4-mini",           "Nina Johansson": "cursor-default",
        "Oscar Blanco": "claude-haiku-4",   "Priya Sharma": "claude-opus-4",
        "Reuben Stein": "aider-default",    "Sofia Andersson": "gpt-4o",
        "Tariq Hussain": "gemini-2.5-flash","Uma Patel": "deepseek-v3",
    },

    "projects": {
        "NovaPay-Core":       {"key": "PAY",  "components": ["payment-engine", "settlement", "clearing", "reconciliation"]},
        "NovaPay-Lending":    {"key": "LND",  "components": ["underwriting", "loan-origination", "servicing", "collections"]},
        "NovaPay-Compliance": {"key": "CMP",  "components": ["kyc-aml", "regulatory-reporting", "audit-trail", "sanctions-screening"]},
        "NovaPay-Risk":       {"key": "RSK",  "components": ["fraud-detection", "credit-scoring", "risk-models", "exposure-monitoring"]},
        "NovaPay-Platform":   {"key": "PLT",  "components": ["merchant-portal", "developer-api", "webhooks", "sandbox"]},
    },

    "epics": [
        {"key": "PAY-EPIC-1",  "name": "Real-Time Settlement Engine",     "project": "NovaPay-Core",       "topics": ["Payment Processing", "Transaction Security", "Ledger & Reconciliation", "API Gateway & Integration"], "ticket_count": 32, "status": "in_progress", "target_date": "2025-08-20"},
        {"key": "CMP-EPIC-2",  "name": "AML/KYC Automation Platform",     "project": "NovaPay-Compliance", "topics": ["Compliance & Regulatory", "Fraud Detection & Prevention", "Transaction Security", "Risk Modeling"], "ticket_count": 25, "status": "in_progress", "target_date": "2025-09-15"},
        {"key": "RSK-EPIC-3",  "name": "ML Credit Scoring v3",            "project": "NovaPay-Risk",       "topics": ["Risk Modeling", "Fraud Detection & Prevention", "Data Pipeline & ETL", "Performance & Latency"], "ticket_count": 20, "status": "planning", "target_date": "2025-10-01"},
        {"key": "PLT-EPIC-4",  "name": "Developer API Portal Redesign",   "project": "NovaPay-Platform",   "topics": ["API Gateway & Integration", "Merchant & Partner Portal", "Testing & Certification", "Payment Processing"], "ticket_count": 28, "status": "in_progress", "target_date": "2025-08-01"},
        {"key": "LND-EPIC-5",  "name": "Instant Loan Decisioning",        "project": "NovaPay-Lending",    "topics": ["Lending & Underwriting", "Risk Modeling", "Compliance & Regulatory", "Performance & Latency"], "ticket_count": 22, "status": "done", "target_date": "2025-05-30"},
    ],

    "topics": {
        "Payment Processing": {
            "keywords": [
                "payment", "transaction", "settlement", "clearing", "ledger",
                "double-entry", "idempotency", "reconciliation", "payout",
                "refund", "chargeback", "ach", "wire", "iso8583",
                "payment-gateway", "stripe", "plaid",
            ],
            "duration_range": (40, 160),
            "token_range": (1000, 4500),
        },
        "Regulatory Compliance": {
            "keywords": [
                "kyc", "aml", "bsa", "pci-dss", "sox", "gdpr",
                "regulatory-reporting", "sanctions", "ofac", "fincen",
                "compliance-audit", "risk-assessment", "sar", "ctr",
                "consumer-protection", "dodd-frank", "cfpb",
            ],
            "duration_range": (50, 180),
            "token_range": (1200, 5000),
        },
        "Fraud Detection": {
            "keywords": [
                "fraud", "anomaly-detection", "rules-engine", "velocity-check",
                "device-fingerprint", "ip-geolocation", "chargeback-prevention",
                "machine-learning-fraud", "graph-analysis", "behavioral-biometrics",
                "3d-secure", "risk-scoring", "false-positive", "case-management",
                "suspicious-activity", "real-time-scoring", "fraud-ring",
            ],
            "duration_range": (45, 170),
            "token_range": (1100, 4800),
        },
        "Transaction Systems": {
            "keywords": [
                "acid", "distributed-transaction", "saga", "event-sourcing",
                "cqrs", "eventual-consistency", "two-phase-commit", "outbox-pattern",
                "message-broker", "exactly-once", "at-least-once", "dead-letter-queue",
                "retry-policy", "circuit-breaker", "bulkhead", "backpressure",
                "rate-limiter",
            ],
            "duration_range": (35, 140),
            "token_range": (900, 4000),
        },
        "Risk Modeling": {
            "keywords": [
                "credit-score", "probability-of-default", "loss-given-default",
                "exposure-at-default", "var", "stress-test", "monte-carlo",
                "logistic-regression", "xgboost", "feature-importance",
                "model-validation", "backtesting", "regulatory-capital",
                "risk-weight", "expected-loss", "unexpected-loss", "concentration-risk",
            ],
            "duration_range": (50, 200),
            "token_range": (1300, 5500),
        },
        "Financial APIs": {
            "keywords": [
                "open-banking", "plaid", "mx", "finicity", "api-versioning",
                "webhook", "oauth2", "api-key", "rate-limit", "idempotency-key",
                "pagination", "sandbox", "test-mode", "merchant-onboarding",
                "developer-portal", "sdk", "openapi-spec",
            ],
            "duration_range": (25, 100),
            "token_range": (600, 2800),
        },
        "Ledger & Accounting": {
            "keywords": [
                "general-ledger", "double-entry", "journal-entry", "chart-of-accounts",
                "accrual", "cash-basis", "trial-balance", "balance-sheet",
                "income-statement", "subledger", "intercompany", "currency-conversion",
                "fx-rate", "gaap", "ifrs", "month-end-close", "amortization",
            ],
            "duration_range": (40, 150),
            "token_range": (900, 4000),
        },
        "Data Infrastructure": {
            "keywords": [
                "etl", "pipeline", "data-warehouse", "snowflake", "redshift",
                "dbt", "airflow", "kafka", "streaming", "batch",
                "data-lake", "parquet", "delta-lake", "data-quality",
                "lineage", "schema-registry", "cdc",
            ],
            "duration_range": (30, 120),
            "token_range": (700, 3000),
        },
        "Security & Encryption": {
            "keywords": [
                "encryption-at-rest", "encryption-in-transit", "hsm", "key-management",
                "tokenization", "pci-dss", "vault", "mTLS", "certificate-rotation",
                "secrets-management", "zero-trust", "penetration-test",
                "vulnerability-scan", "soc2", "iso27001", "access-control",
                "audit-log",
            ],
            "duration_range": (40, 160),
            "token_range": (1000, 4500),
        },
        "Real-time Systems": {
            "keywords": [
                "websocket", "server-sent-events", "pub-sub", "event-driven",
                "low-latency", "high-throughput", "in-memory", "redis",
                "kafka-streams", "flink", "real-time-analytics", "cep",
                "time-series", "tick-data", "market-data", "feed-handler",
                "order-matching",
            ],
            "duration_range": (35, 150),
            "token_range": (900, 4200),
        },
        "Testing & Certification": {
            "keywords": [
                "integration-test", "contract-test", "regression", "load-test",
                "chaos-engineering", "pci-certification", "penetration-test",
                "compliance-test", "end-to-end", "sandbox-test", "mock-bank",
                "test-harness", "golden-path", "negative-test", "boundary-test",
                "fuzz-test", "certification-audit",
            ],
            "duration_range": (20, 90),
            "token_range": (500, 2200),
        },
        "Infrastructure & SRE": {
            "keywords": [
                "kubernetes", "docker", "terraform", "aws", "gcp",
                "high-availability", "disaster-recovery", "failover",
                "blue-green", "canary", "slo", "sli", "error-budget",
                "incident-response", "runbook", "on-call", "observability",
            ],
            "duration_range": (25, 110),
            "token_range": (600, 2800),
        },
    },

    "struggle_signals": {
        ("Carlos Mendez", "Regulatory Compliance"):   {"duration_mult": 2.3, "token_mult": 2.5},
        ("Hannah Olsen", "Fraud Detection"):          {"duration_mult": 2.1, "token_mult": 2.4},
        ("Reuben Stein", "Risk Modeling"):             {"duration_mult": 2.0, "token_mult": 2.2},
        ("Elijah Okonkwo", "Ledger & Accounting"):    {"duration_mult": 1.7, "token_mult": 1.8},
        ("Sofia Andersson", "Real-time Systems"):      {"duration_mult": 1.6, "token_mult": 1.7},
        ("Priya Sharma", "Payment Processing"):        {"duration_mult": 1.5, "token_mult": 1.5},
        ("Priya Sharma", "Transaction Systems"):       {"duration_mult": 1.4, "token_mult": 1.5},
        ("Priya Sharma", "Financial APIs"):            {"duration_mult": 1.4, "token_mult": 1.4},
        ("Priya Sharma", "Security & Encryption"):     {"duration_mult": 1.5, "token_mult": 1.4},
        ("Kevin Tran", "Data Infrastructure"):         {"duration_mult": 1.6, "token_mult": 1.7},
    },

    "team_wide_struggles": {
        "Regulatory Compliance":  {"duration_mult": 1.4, "token_mult": 1.5, "error_boost": 5},
        "Fraud Detection":        {"duration_mult": 1.3, "token_mult": 1.3, "error_boost": 3},
    },

    "curated_sources": {
        "Regulatory Compliance": {
            "standards": ["PCI DSS v4.0", "BSA/AML requirements", "SOX compliance", "GDPR", "CFPB guidelines"],
            "tools": ["Alloy (KYC)", "Sardine (fraud+compliance)", "Unit21", "ComplyAdvantage", "Hummingbird"],
            "training": ["ACAMS certification", "PCI SSC training", "FinCEN advisories"],
            "practices": ["automated regulatory reporting", "continuous KYC monitoring", "sanctions screening in real-time"],
        },
        "Fraud Detection": {
            "standards": ["EMV 3DS 2.0", "PSD2 SCA requirements"],
            "tools": ["Sardine", "Featurespace", "Feedzai", "Sift", "Riskified", "DataVisor"],
            "training": ["ACFE fraud examination", "Kaggle fraud detection competitions"],
            "practices": ["real-time scoring with ML models", "velocity rules + ML ensemble", "false positive rate tracking"],
        },
        "Payment Processing": {
            "standards": ["ISO 8583", "ISO 20022", "Nacha ACH rules", "PCI DSS"],
            "tools": ["Stripe Connect", "Plaid", "Modern Treasury", "Moov Financial", "Dwolla"],
            "training": ["Payments 101 by Stripe (free)", "ACH rules handbook"],
            "practices": ["idempotency keys on all mutations", "double-entry ledger pattern", "reconciliation automation"],
        },
        "Risk Modeling": {
            "standards": ["Basel III/IV capital requirements", "IFRS 9 expected credit loss"],
            "tools": ["XGBoost", "LightGBM", "SHAP (explainability)", "Evidently AI (monitoring)", "MLflow"],
            "training": ["Credit Risk Modeling in Python (Udemy)", "CFA Institute risk primers"],
            "practices": ["model validation with holdout sets", "champion-challenger framework", "regulatory model documentation"],
        },
        "Transaction Systems": {
            "standards": ["Saga pattern (Microservices Patterns)", "CQRS/ES best practices"],
            "tools": ["Temporal.io", "Apache Kafka", "Debezium (CDC)", "EventStoreDB"],
            "training": ["Designing Data-Intensive Applications (book)", "Temporal.io tutorials"],
            "practices": ["outbox pattern for reliable messaging", "idempotent consumers", "dead letter queue monitoring"],
        },
        "Security & Encryption": {
            "standards": ["PCI DSS v4.0", "SOC 2 Type II", "ISO 27001", "NIST 800-53"],
            "tools": ["HashiCorp Vault", "AWS KMS", "Thales HSM", "Snyk", "Trivy"],
            "training": ["PCI SSC QSA training", "SANS SEC540"],
            "practices": ["tokenization of card data", "certificate rotation automation", "zero-trust network architecture"],
        },
        "Ledger & Accounting": {
            "standards": ["US GAAP", "IFRS", "ASC 606 revenue recognition"],
            "tools": ["Modern Treasury", "Hledger", "Beancount", "Netsuite", "Sage Intacct"],
            "training": ["Double-entry accounting fundamentals", "Financial accounting for engineers"],
            "practices": ["immutable journal entries", "automated month-end close", "multi-currency handling"],
        },
        "Financial APIs": {
            "standards": ["Open Banking (PSD2/FDX)", "OpenAPI 3.1"],
            "tools": ["Plaid", "MX", "Finicity", "Postman", "Speakeasy (SDK gen)"],
            "training": ["Plaid developer docs", "Open Banking APIs course"],
            "practices": ["idempotency keys", "webhook signature verification", "sandbox parity with production"],
        },
        "Data Infrastructure": {
            "standards": ["Data mesh principles", "Data quality dimensions"],
            "tools": ["dbt", "Great Expectations", "Airflow", "Snowflake", "Fivetran"],
            "training": ["Data Engineering Zoomcamp (free)", "dbt Learn (free)"],
            "practices": ["data contracts", "pipeline idempotency", "data freshness SLAs"],
        },
        "Real-time Systems": {
            "standards": ["Reactive Manifesto", "LMAX architecture"],
            "tools": ["Apache Kafka", "Apache Flink", "Redis Streams", "RabbitMQ", "Ably"],
            "training": ["Designing Data-Intensive Applications", "Kafka: The Definitive Guide"],
            "practices": ["backpressure handling", "exactly-once semantics", "time-series partitioning"],
        },
        "Testing & Certification": {
            "standards": ["PCI DSS testing requirements", "SOC 2 audit prep"],
            "tools": ["Postman", "Pact", "Testcontainers", "Locust", "Gremlin (chaos)"],
            "training": ["Test-Driven Development by Example"],
            "practices": ["mock bank simulators", "compliance test automation", "chaos engineering in staging"],
        },
        "Infrastructure & SRE": {
            "standards": ["Google SRE principles", "DORA metrics"],
            "tools": ["Terraform", "ArgoCD", "Datadog", "PagerDuty", "Spacelift"],
            "training": ["Google SRE Book (free)", "AWS Well-Architected labs"],
            "practices": ["error budget policies", "automated incident response", "DR failover testing quarterly"],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# PRESET 3: Medical Tech
# ═══════════════════════════════════════════════════════════════════════════

MEDTECH = {
    "name": "medtech",
    "company": "MedCore Systems",
    "description": "Healthcare technology company building EHR integrations and clinical platforms",

    "employees": [
        "Adrian Wells", "Beth Kowalski", "Chiara Romano", "Derek Okafor", "Elena Vasquez",
        "Finn Larsson", "Gina Morales", "Hassan Demir", "Ingrid Hoffman", "James Whitfield",
        "Keiko Nakamura", "Liam O'Brien", "Maria Gonzalez", "Naveen Reddy", "Olga Ivanova",
        "Patrick Byrne", "Quinn Delgado", "Rachel Kim", "Stefan Novak", "Tanya Petrova",
    ],

    "employee_models": {
        "Adrian Wells": "claude-sonnet-4",  "Beth Kowalski": "gpt-4o",
        "Chiara Romano": "claude-opus-4",   "Derek Okafor": "cursor-default",
        "Elena Vasquez": "gemini-2.5-pro",  "Finn Larsson": "claude-sonnet-4",
        "Gina Morales": "o4-mini",          "Hassan Demir": "github-copilot",
        "Ingrid Hoffman": "claude-opus-4",  "James Whitfield": "gpt-4o",
        "Keiko Nakamura": "deepseek-v3",    "Liam O'Brien": "windsurf-default",
        "Maria Gonzalez": "claude-sonnet-4","Naveen Reddy": "claude-haiku-4",
        "Olga Ivanova": "deepseek-r1",      "Patrick Byrne": "aider-default",
        "Quinn Delgado": "cursor-default",  "Rachel Kim": "gemini-2.5-flash",
        "Stefan Novak": "o3",               "Tanya Petrova": "gpt-4o",
    },

    "projects": {
        "MedCore-EHR":       {"key": "EHR",  "components": ["patient-records", "clinical-notes", "orders", "lab-results"]},
        "MedCore-Telehealth": {"key": "TH",   "components": ["video-consult", "async-messaging", "e-prescribe", "scheduling"]},
        "MedCore-Imaging":   {"key": "IMG",  "components": ["dicom-viewer", "ai-detection", "pacs-integration", "reporting"]},
        "MedCore-Analytics":  {"key": "ANA",  "components": ["population-health", "clinical-dashboards", "quality-measures", "registry"]},
        "MedCore-Platform":  {"key": "PLT",  "components": ["identity", "consent-management", "audit-logging", "api-gateway"]},
    },

    "epics": [
        {"key": "EHR-EPIC-1",  "name": "FHIR R4 Migration",              "project": "MedCore-EHR",        "topics": ["EHR Integration", "Healthcare API Development", "HIPAA & Compliance", "Clinical Data Modeling"], "ticket_count": 38, "status": "in_progress", "target_date": "2025-09-01"},
        {"key": "TH-EPIC-2",   "name": "Async Telehealth Platform",      "project": "MedCore-Telehealth", "topics": ["Telehealth & RPM", "Healthcare API Development", "Medical Device Integration", "HIPAA & Compliance"], "ticket_count": 24, "status": "in_progress", "target_date": "2025-08-15"},
        {"key": "IMG-EPIC-3",  "name": "AI Radiology Triage System",     "project": "MedCore-Imaging",    "topics": ["Clinical Decision Support", "Medical Imaging Pipeline", "Healthcare ML/AI", "Clinical Data Modeling"], "ticket_count": 20, "status": "planning", "target_date": "2025-10-15"},
        {"key": "ANA-EPIC-4",  "name": "Population Health Dashboard",    "project": "MedCore-Analytics",  "topics": ["Healthcare Analytics", "Clinical Data Modeling", "EHR Integration", "HIPAA & Compliance"], "ticket_count": 26, "status": "in_progress", "target_date": "2025-08-01"},
        {"key": "PLT-EPIC-5",  "name": "Zero-Trust Identity Overhaul",   "project": "MedCore-Platform",   "topics": ["HIPAA & Compliance", "Healthcare API Development", "Pharmacy & Medication Systems", "Clinical Workflow Automation"], "ticket_count": 30, "status": "done", "target_date": "2025-05-20"},
    ],

    "topics": {
        "EHR Integration": {
            "keywords": [
                "hl7", "fhir", "cda", "ccda", "adt", "orm", "oru",
                "epic", "cerner", "allscripts", "interoperability",
                "patient-matching", "mpi", "interface-engine", "mirth",
                "smart-on-fhir", "bulk-fhir",
            ],
            "duration_range": (45, 180),
            "token_range": (1200, 5000),
        },
        "HIPAA & Compliance": {
            "keywords": [
                "hipaa", "phi", "baa", "encryption-at-rest", "access-control",
                "audit-log", "breach-notification", "minimum-necessary",
                "de-identification", "safe-harbor", "expert-determination",
                "hitrust", "soc2-health", "21-cfr-part-11", "gdpr-health",
                "consent-management", "data-retention",
            ],
            "duration_range": (50, 200),
            "token_range": (1300, 5500),
        },
        "Clinical Data Pipelines": {
            "keywords": [
                "etl", "clinical-data", "data-warehouse", "omop", "i2b2",
                "pcornet", "data-harmonization", "terminology-mapping",
                "snomed", "icd-10", "loinc", "rxnorm", "ndc",
                "quality-measure", "hedis", "clinical-registry",
                "real-world-data",
            ],
            "duration_range": (40, 160),
            "token_range": (1000, 4500),
        },
        "Medical Imaging": {
            "keywords": [
                "dicom", "pacs", "orthanc", "ohif-viewer", "cornerstone",
                "medical-ai", "cad", "segmentation", "classification",
                "radiology", "pathology", "xray", "ct-scan", "mri",
                "fda-clearance", "clinical-validation", "annotation",
            ],
            "duration_range": (50, 200),
            "token_range": (1300, 5500),
        },
        "Patient Portal": {
            "keywords": [
                "patient-portal", "my-chart", "patient-engagement",
                "appointment-scheduling", "secure-messaging", "bill-pay",
                "health-records-access", "proxy-access", "mobile-health",
                "patient-intake", "digital-forms", "e-consent",
                "accessibility", "multilingual", "health-literacy",
                "cures-act", "information-blocking",
            ],
            "duration_range": (25, 100),
            "token_range": (600, 2800),
        },
        "Telehealth": {
            "keywords": [
                "video-consultation", "webrtc", "async-telehealth",
                "remote-monitoring", "rpm", "wearable-integration",
                "e-prescribing", "epcs", "surescripts", "telehealth-consent",
                "state-licensure", "cross-state", "reimbursement",
                "cpt-telehealth", "store-and-forward", "peripheral-devices",
                "waiting-room",
            ],
            "duration_range": (30, 120),
            "token_range": (800, 3500),
        },
        "Clinical Decision Support": {
            "keywords": [
                "cds", "clinical-rules", "alert-fatigue", "drug-interaction",
                "allergy-check", "dose-range-check", "order-set",
                "evidence-based", "clinical-pathway", "sepsis-detection",
                "deterioration-score", "news2", "qsofa", "bpa",
                "clinical-ai", "nlp-clinical", "predictive-model",
            ],
            "duration_range": (45, 180),
            "token_range": (1100, 4800),
        },
        "Lab & Pharmacy Systems": {
            "keywords": [
                "lis", "lims", "lab-order", "lab-result", "reference-range",
                "critical-value", "auto-verification", "cpoe",
                "medication-reconciliation", "formulary", "ndc-code",
                "barcode-scanning", "unit-dose", "pharmacy-workflow",
                "controlled-substance", "drug-database", "first-databank",
            ],
            "duration_range": (35, 140),
            "token_range": (900, 4000),
        },
        "Identity & Access": {
            "keywords": [
                "oauth2", "saml", "sso", "mfa", "rbac", "abac",
                "break-glass", "emergency-access", "provider-credentialing",
                "npi", "dea-number", "patient-identity", "mpi",
                "biometric", "smart-card", "piv", "session-management",
            ],
            "duration_range": (30, 120),
            "token_range": (800, 3200),
        },
        "Infrastructure & DevOps": {
            "keywords": [
                "hipaa-cloud", "aws-hipaa", "baa", "encrypted-vpc",
                "kubernetes", "docker", "terraform", "ci-cd",
                "infrastructure-as-code", "disaster-recovery",
                "backup-validation", "monitoring", "alerting",
                "incident-response", "phi-logging", "audit-trail",
                "penetration-test",
            ],
            "duration_range": (25, 110),
            "token_range": (600, 2800),
        },
        "Quality & Testing": {
            "keywords": [
                "clinical-validation", "usability-testing", "ehr-certification",
                "onc-certification", "cehrt", "meaningful-use",
                "interoperability-test", "connectathon", "integration-test",
                "regression", "clinical-scenario", "edge-case",
                "safety-testing", "risk-analysis", "fmea",
                "iec-62304", "software-validation",
            ],
            "duration_range": (30, 120),
            "token_range": (700, 3000),
        },
        "Reporting & Analytics": {
            "keywords": [
                "quality-measure", "hedis", "cms-star-rating", "mips",
                "population-health", "risk-stratification", "cohort-analysis",
                "clinical-dashboard", "tableau-health", "power-bi",
                "data-visualization", "benchmarking", "outcomes-research",
                "value-based-care", "cost-analysis", "utilization-review",
                "registry-reporting",
            ],
            "duration_range": (25, 100),
            "token_range": (600, 2800),
        },
    },

    "struggle_signals": {
        ("Beth Kowalski", "HIPAA & Compliance"):       {"duration_mult": 2.3, "token_mult": 2.6},
        ("Hassan Demir", "Medical Imaging"):            {"duration_mult": 2.1, "token_mult": 2.4},
        ("Liam O'Brien", "Clinical Decision Support"):  {"duration_mult": 2.0, "token_mult": 2.2},
        ("Derek Okafor", "EHR Integration"):            {"duration_mult": 1.6, "token_mult": 1.7},
        ("Tanya Petrova", "Lab & Pharmacy Systems"):    {"duration_mult": 1.5, "token_mult": 1.6},
        ("Quinn Delgado", "Clinical Data Pipelines"):   {"duration_mult": 1.4, "token_mult": 1.5},
        ("Quinn Delgado", "Telehealth"):                {"duration_mult": 1.5, "token_mult": 1.4},
        ("Quinn Delgado", "Patient Portal"):            {"duration_mult": 1.4, "token_mult": 1.4},
        ("Quinn Delgado", "Reporting & Analytics"):     {"duration_mult": 1.4, "token_mult": 1.5},
        ("Ingrid Hoffman", "Identity & Access"):        {"duration_mult": 1.6, "token_mult": 1.8},
    },

    "team_wide_struggles": {
        "HIPAA & Compliance":         {"duration_mult": 1.4, "token_mult": 1.5, "error_boost": 5},
        "Clinical Decision Support":  {"duration_mult": 1.3, "token_mult": 1.4, "error_boost": 4},
    },

    "curated_sources": {
        "HIPAA & Compliance": {
            "standards": ["HIPAA Security Rule", "HIPAA Privacy Rule", "HITRUST CSF v11", "21 CFR Part 11", "ONC Cures Act"],
            "tools": ["Vanta (HIPAA automation)", "Drata", "Tugboat Logic", "AWS HIPAA eligible services", "Aptible"],
            "training": ["HIPAA training (HHS.gov, free)", "HITRUST Academy", "CHPS certification"],
            "practices": ["PHI access logging and review", "minimum necessary enforcement", "BAA management automation"],
        },
        "Clinical Decision Support": {
            "standards": ["HL7 CDS Hooks", "CMS Meaningful Use CDS requirements", "AMA clinical guidelines"],
            "tools": ["CDS Hooks (HL7)", "OpenCDS", "SMART on FHIR apps", "Clinical Quality Language (CQL)", "Arden Syntax"],
            "training": ["HL7 FHIR Connectathon (free)", "Clinical informatics board prep"],
            "practices": ["alert fatigue reduction (tiered alerting)", "evidence-based rule curation", "CDS committee governance"],
        },
        "EHR Integration": {
            "standards": ["HL7 FHIR R4/R5", "HL7 v2.x ADT/ORM/ORU", "C-CDA 2.1", "USCDI v4"],
            "tools": ["Mirth Connect", "Rhapsody", "HAPI FHIR Server", "SMART on FHIR", "Firely"],
            "training": ["HL7 FHIR Fundamentals (free course)", "Corepoint training"],
            "practices": ["patient matching with probabilistic MPI", "FHIR subscription for real-time sync", "interface monitoring dashboards"],
        },
        "Medical Imaging": {
            "standards": ["DICOM 3.0", "IHE profiles (XDS, XCA)", "FDA 510(k) for SaMD"],
            "tools": ["Orthanc (open-source PACS)", "OHIF Viewer", "Cornerstone.js", "MONAI (medical AI)", "3D Slicer"],
            "training": ["RSNA informatics courses", "MONAI tutorials (free)"],
            "practices": ["DICOM de-identification before AI training", "clinical validation studies", "FDA pre-submission feedback"],
        },
        "Clinical Data Pipelines": {
            "standards": ["OMOP CDM v5.4", "PCORnet CDM", "USCDI data classes"],
            "tools": ["OHDSI tools (Atlas, Achilles)", "dbt", "Great Expectations", "Apache Airflow", "Koalas"],
            "training": ["OHDSI community tutorials (free)", "Data Engineering Zoomcamp (free)"],
            "practices": ["terminology mapping validation (SNOMED-ICD crosswalk)", "data quality dashboards", "cohort validation"],
        },
        "Lab & Pharmacy Systems": {
            "standards": ["CLIA regulations", "USP 800", "DEA EPCS requirements"],
            "tools": ["First Databank (drug DB)", "Surescripts", "RxNorm API (NLM)", "Lab Corp API"],
            "training": ["ASHP informatics certificate", "Lab information systems training"],
            "practices": ["auto-verification rules with fallback", "medication reconciliation workflows", "critical value notification SLAs"],
        },
        "Patient Portal": {
            "standards": ["ONC Cures Act information blocking", "WCAG 2.2", "Health Literacy guidelines"],
            "tools": ["Healthwise (patient education)", "Twilio (secure messaging)", "Stripe (healthcare billing)"],
            "training": ["UX for Healthcare (book)", "web.dev accessibility course (free)"],
            "practices": ["proxy access workflows (minors, caregivers)", "multilingual content strategy", "patient-reported outcomes integration"],
        },
        "Telehealth": {
            "standards": ["CMS telehealth billing rules", "State licensure compact", "DEA EPCS for telehealth"],
            "tools": ["Twilio Video (HIPAA)", "Vonage (HIPAA)", "Zoom for Healthcare", "Doxy.me"],
            "training": ["ATA telehealth certification", "CMS telehealth billing updates"],
            "practices": ["state licensure verification automation", "e-prescribing with EPCS", "peripheral device integration testing"],
        },
        "Identity & Access": {
            "standards": ["NIST 800-63 digital identity", "HIPAA access controls"],
            "tools": ["Okta (healthcare)", "Auth0", "Ping Identity", "Imprivata (SSO for clinicians)"],
            "training": ["CISSP healthcare domain", "NIST identity guidelines"],
            "practices": ["break-glass access with audit trail", "provider credentialing verification", "session timeout for PHI screens"],
        },
        "Infrastructure & DevOps": {
            "standards": ["HIPAA technical safeguards", "SOC 2 Type II"],
            "tools": ["Aptible (HIPAA PaaS)", "AWS GovCloud", "Terraform", "Datadog"],
            "training": ["AWS healthcare competency", "Aptible HIPAA guides"],
            "practices": ["PHI-aware logging (redaction)", "encrypted backups with restore testing", "BAA coverage for all vendors"],
        },
        "Quality & Testing": {
            "standards": ["ONC Health IT Certification (g)(10)", "IEC 62304 medical device software", "ISO 14971 risk management"],
            "tools": ["Cypress (ONC test harness)", "Inferno (FHIR testing)", "Postman", "Testcontainers"],
            "training": ["IEC 62304 training", "ONC certification program guide"],
            "practices": ["clinical scenario-based testing", "FMEA for safety-critical features", "traceability matrix for requirements"],
        },
        "Reporting & Analytics": {
            "standards": ["CMS quality reporting (MIPS/APM)", "HEDIS measures", "UDS reporting"],
            "tools": ["Tableau", "Power BI", "Arcadia (population health)", "Innovaccer"],
            "training": ["HEDIS certification", "Population health analytics courses"],
            "practices": ["measure validation with clinical SMEs", "risk stratification model monitoring", "automated registry submission"],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════════════

ALL_PRESETS = {
    "startup": STARTUP,
    "fintech": FINTECH,
    "medtech": MEDTECH,
}


def get_active_preset_name() -> str:
    if os.path.exists(PRESET_FILE):
        with open(PRESET_FILE) as f:
            name = f.read().strip()
            if name in ALL_PRESETS:
                return name
    return "startup"


def set_active_preset(name: str) -> None:
    if name not in ALL_PRESETS:
        raise ValueError(f"Unknown preset: {name}. Available: {list(ALL_PRESETS.keys())}")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PRESET_FILE, "w") as f:
        f.write(name)


def get_active_preset() -> dict:
    return ALL_PRESETS[get_active_preset_name()]


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        name = sys.argv[1]
        set_active_preset(name)
        p = ALL_PRESETS[name]
        print(f"Active preset: {name} — {p['company']} ({p['description']})")
    else:
        print(f"Active: {get_active_preset_name()}")
        print(f"Available: {', '.join(ALL_PRESETS.keys())}")
