# Thesis Diagrams (Mermaid)

These render on GitHub and in Mermaid-aware editors (VS Code + Mermaid extension,
mermaid.live). To use in the thesis: paste into https://mermaid.live, then
**Export as PNG/SVG** and insert as a figure. Each diagram reflects the as-built
system.

---

## Figure 4.1 — System architecture (three-tier)

```mermaid
flowchart TB
    subgraph Client["Presentation Tier — React SPA (Vite + Tailwind)"]
        UI["Role-aware UI:\nCirculars · Upload · Approvals · Dashboard · Chatbot · Audit"]
        AX["Axios + JWT interceptor"]
        UI --> AX
    end

    subgraph Server["Application Tier — Flask REST API"]
        direction TB
        BP["Blueprints:\nauth · users · circulars · summaries\ndashboard · chatbot · notifications · audit"]
        SVC["Services:\nsecurity/RBAC · audit · distribution\nemail · pdf_extract · tokens"]
        AI["AI layer:\npipeline · vector_index · chatbot · llm_summarizer"]
        BP --> SVC
        BP --> AI
    end

    subgraph Data["Data Tier"]
        DB[("MySQL 8\n14 tables")]
        FAISS[("FAISS index\n+ chunk metadata")]
        CACHE[("Local model cache")]
    end

    OLLAMA["Ollama runtime\n(Llama 3.2 3B) — localhost"]

    AX -->|"HTTPS /api/*"| BP
    SVC --> DB
    AI --> DB
    AI --> FAISS
    AI --> CACHE
    AI -->|"HTTP localhost:11434"| OLLAMA

    classDef tier fill:#e6f3f3,stroke:#0e7c7b,color:#073f3f;
    class Client,Server,Data tier;
```

---

## Figure 4.2 — Entity–Relationship Diagram (core)

```mermaid
erDiagram
    USERS ||--o{ ACKNOWLEDGEMENTS : makes
    USERS ||--o{ NOTIFICATIONS : receives
    USERS ||--o{ CIRCULARS : uploads
    USERS ||--o{ CHAT_CONVERSATIONS : owns
    USERS ||--o{ AUDIT_LOG : acts
    DEPARTMENTS ||--o{ USERS : employs
    DEPARTMENTS ||--o{ CIRCULAR_DEPARTMENTS : routed
    CIRCULARS ||--o{ CIRCULAR_DEPARTMENTS : routed_to
    CIRCULARS ||--|| SUMMARIES : has
    CIRCULARS ||--o{ CLASSIFICATIONS : categorised
    CIRCULARS ||--o{ ACKNOWLEDGEMENTS : tracked
    CIRCULARS ||--o{ NOTIFICATIONS : about
    CIRCULARS ||--o{ CHANGE_REQUESTS : flagged
    CIRCULARS ||--o{ CIRCULARS : amends
    CATEGORIES ||--o{ CLASSIFICATIONS : names
    CHAT_CONVERSATIONS ||--o{ CHAT_LOG : contains

    USERS {
        int id PK
        string username
        string email
        string full_name
        string password_hash
        string role
        int department_id FK
        bool is_active
    }
    CIRCULARS {
        int id PK
        string circular_number
        string title
        date issue_date
        text extracted_text
        string priority
        string status
        datetime ack_deadline
        int uploaded_by FK
        int amends_circular_id FK
        int approved_by FK
        json distribution_intent
        datetime published_at
    }
    SUMMARIES {
        int id PK
        int circular_id FK
        text summary_text
        json entities
        int word_count
        string bart_model
        float processing_seconds
        float rouge_score
    }
    CLASSIFICATIONS {
        int id PK
        int circular_id FK
        string category
        bool is_manual
    }
    CATEGORIES {
        int id PK
        string name
    }
    ACKNOWLEDGEMENTS {
        int id PK
        int circular_id FK
        int user_id FK
        string status
        datetime read_at
        datetime acknowledged_at
        bool is_late
    }
    NOTIFICATIONS {
        int id PK
        int user_id FK
        int circular_id FK
        string message
        string link
        bool is_read
    }
    CHAT_CONVERSATIONS {
        int id PK
        int user_id FK
        int circular_id FK
        string title
    }
    CHAT_LOG {
        int id PK
        int conversation_id FK
        text question
        text answer
        json citations
    }
    AUDIT_LOG {
        int id PK
        int user_id FK
        string action
        string entity_type
        int entity_id
        string detail
        datetime created_at
    }
    DEPARTMENTS {
        int id PK
        string name
        string code
    }
    CIRCULAR_DEPARTMENTS {
        int circular_id FK
        int department_id FK
    }
    CHANGE_REQUESTS {
        int id PK
        int circular_id FK
        int requester_id FK
        string status
    }
```

---

## Figure 4.3 — Domain model (class diagram)

```mermaid
classDiagram
    class User {
        +int id
        +str username
        +str email
        +str full_name
        +str password_hash
        +str role
        +bool is_active
        +datetime last_login
    }
    class Department {
        +int id
        +str name
        +str code
        +str description
    }
    class Circular {
        +int id
        +str circular_number
        +str title
        +date issue_date
        +text extracted_text
        +str priority
        +str status
        +datetime ack_deadline
        +int uploaded_by
        +int approved_by
        +int amends_circular_id
        +json distribution_intent
        +datetime published_at
    }
    class Summary {
        +int id
        +int circular_id
        +text summary_text
        +json entities
        +int word_count
        +str bart_model
        +float processing_seconds
        +float rouge_score
    }
    class Category {
        +int id
        +str name
    }
    class Classification {
        +int id
        +int circular_id
        +str category
        +float confidence
        +bool is_manual
    }
    class Acknowledgement {
        +int id
        +int circular_id
        +int user_id
        +str status
        +datetime read_at
        +datetime acknowledged_at
        +bool is_late
    }
    class Notification {
        +int id
        +int user_id
        +int circular_id
        +str message
        +bool is_read
    }
    class CircularDepartment {
        +int circular_id
        +int department_id
        +datetime routed_at
    }
    class ChatConversation {
        +int id
        +int user_id
        +int circular_id
        +str title
    }
    class ChatLog {
        +int id
        +int conversation_id
        +text question
        +text answer
        +json citations
    }
    class AuditLog {
        +int id
        +int user_id
        +str action
        +str entity_type
        +int entity_id
        +str detail
    }
    class ChangeRequest {
        +int id
        +int circular_id
        +int requester_id
        +str status
        +str admin_reply
    }

    Department "1" --o "*" User : employs
    User "1" --o "*" Circular : uploads
    User "1" --o "*" Circular : approves
    Circular "1" --o "0..1" Summary : has
    Circular "1" --o "*" Classification : categorised
    Category "1" --o "*" Classification : names
    Circular "*" --o "*" Department : routed (CircularDepartment)
    Circular "1" --o "*" Acknowledgement : tracked
    User "1" --o "*" Acknowledgement : makes
    Circular "1" --o "*" Notification : about
    User "1" --o "*" Notification : receives
    Circular "0..1" --o "*" Circular : amends
    User "1" --o "*" ChatConversation : owns
    ChatConversation "1" --o "*" ChatLog : contains
    User "1" --o "*" AuditLog : acts
    Circular "1" --o "*" ChangeRequest : flagged
```

> Note: `Classification.category` and `Category.name` are linked by name
> (string), not a hard FK, so administrators can rename/remove categories without
> orphaning existing classifications.

---

## Figure 4.4 — Circular lifecycle (state diagram)

```mermaid
stateDiagram-v2
    [*] --> uploaded : Admin uploads PDF
    uploaded --> processing : Generate summary
    processing --> review : Summary ready
    processing --> failed : Error
    failed --> processing : Retry
    review --> pending_approval : Admin submits\n(category + departments)
    pending_approval --> published : Compliance Officer approves
    pending_approval --> review : Compliance Officer rejects\n(with reason)
    published --> processing : Regenerate summary
    published --> [*]
```

---

## Figure 4.5 — End-to-end circular workflow (activity diagram)

```mermaid
flowchart TB
    start(("Start")) --> up["Administrator uploads circular PDF"]
    up --> ext["System extracts text (PyMuPDF)"]
    ext --> ocr{"Text usable?"}
    ocr -- "no" --> tess["Run Tesseract OCR"]
    tess --> sum
    ocr -- "yes" --> sum["Generate AI summary (LLM / BART fallback)"]
    sum --> rev["Administrator reviews & edits summary"]
    rev --> cls["Assign category + target departments"]
    cls --> sub["Submit for approval"]
    sub --> pend["Status: pending_approval"]
    pend --> check{"Compliance Officer decision"}

    check -- "Reject (with reason)" --> notifyA["Notify maker with reason"]
    notifyA --> rev

    check -- "Approve" --> pub["Status: published; record approver"]
    pub --> fork1[" "]
    fork1 --> route["Route to department employees"]
    fork1 --> idx["Rebuild FAISS vector index"]
    route --> ack["Create acknowledgements + notify + email"]
    idx --> join1[" "]
    ack --> join1
    join1 --> read["Employee reads circular"]
    read --> conf{"Acknowledged before deadline?"}
    conf -- "no" --> remind["Send reminder + flag late"]
    remind --> read
    conf -- "yes" --> done["Compliance tracked as complete"]
    done --> stop(("End"))

    audit["Every step written to immutable audit log"]
    audit -.-> pend
    audit -.-> pub

    classDef bar fill:#0e7c7b,stroke:#0e7c7b,color:#0e7c7b;
    class fork1,join1 bar;
```

> Modelled as a UML activity diagram: rounded nodes are start/end, diamonds are
> decisions, and the fork/join after publication shows that distribution and
> vector-index rebuild happen in parallel. The audit log annotation runs across
> the whole flow.

---

## Figure 5.1 — Summarization pipeline (flowchart)

```mermaid
flowchart LR
    A["PDF upload"] --> B["PyMuPDF text extraction"]
    B --> C{"Scanned or\ngarbled page?"}
    C -- yes --> D["Tesseract OCR (300 DPI)"]
    C -- no --> E["Use text layer"]
    D --> F["Clean text:\nstrip headers/footers,\ntable artefacts"]
    E --> F
    F --> G{"Ollama\navailable?"}
    G -- yes --> H["LLM summarise\n(faithful prompt:\nOverview + Key Points)"]
    G -- no --> I["Fallback:\nspaCy -> BERT select -> BART"]
    H --> J["Validate + clean output\n(strip preamble/echo)"]
    I --> J
    J --> K["Extract key terms"]
    K --> L["Store summary\n(status: review)"]
```

---

## Figure 5.2 — RAG chatbot pipeline (flowchart)

```mermaid
flowchart LR
    Q["User question"] --> RW["LLM query rewriting\n(fix typos, keep domain terms)"]
    RW --> DEN["Dense retrieval\n(SBERT + FAISS)"]
    RW --> SPA["Sparse retrieval\n(BM25)"]
    DEN --> RRF["Reciprocal Rank Fusion"]
    SPA --> RRF
    RRF --> SCOPE["Scope filter\n(circular / global,\ndemote superseded)"]
    SCOPE --> GATE{"Relevance gate\n(global only:\nbest cosine >= 0.25?)"}
    GATE -- "no (off-topic)" --> REJ["Reply: 'I could not find\nthat in the circulars'\n(no LLM call)"]
    GATE -- yes --> CTX["Top-k passages as context"]
    CTX --> GEN["LLM grounded generation\n(cite circular numbers,\nrefuse if unsupported)"]
    GEN --> ANS["Answer + citations"]
    ANS --> LOG["Persist to conversation"]
```

---

## Figure 5.3 — Four-eyes approval workflow (sequence diagram)

```mermaid
sequenceDiagram
    actor Admin as Administrator (Maker)
    participant Sys as System
    actor CO as Compliance Officer (Checker)
    actor Emp as Employees

    Admin->>Sys: Upload circular + generate summary
    Sys-->>Admin: Summary (status: review)
    Admin->>Sys: Submit for approval\n(category + departments)
    Sys->>Sys: status = pending_approval
    Sys-->>CO: Notify: awaiting approval
    CO->>Sys: Review summary
    alt Approve
        CO->>Sys: Approve
        Sys->>Sys: status = published; record approver
        Sys->>Emp: Route + notify + email
        Sys-->>Admin: Notify: approved & published
    else Reject
        CO->>Sys: Reject (with reason)
        Sys->>Sys: status = review
        Sys-->>Admin: Notify: rejected + reason
    end
    Note over Sys: Every step written to immutable audit log
```

---

## Figure 5.4 — Distribution & acknowledgement flow

```mermaid
flowchart TB
    P["Circular published"] --> R["Resolve target departments\n(distribution_intent)"]
    R --> U["Active Employees & Managers\nin those departments"]
    U --> A["Create Acknowledgement (Unread)"]
    U --> N["In-app notification (deep link)"]
    U --> E["Email with summary"]
    A --> O["Employee opens -> Read"]
    O --> AK["Employee confirms -> Acknowledged"]
    A --> RM{"Deadline near/passed\n& not acknowledged?"}
    RM -- yes --> REM["Reminder + flag late"]
```

---

## Figure 5.5 — AI service layer (class diagram)

```mermaid
classDiagram
    class NLPPipeline {
        <<base>>
        #load spaCy / BERT / SBERT
    }
    class AIEngine {
        +summarize(text) SummaryResult
        +classify(text) list
        +extract_entities(text, top_n) list
        +extract_keywords(text, top_n, reference) list
        +answer_with_context(question, context)
    }
    class LLMSummarizer {
        +available() bool
        +summarize(text, target_words) str
        +answer(question, context) str
        +refine_query(question) str
        +keywords(text, n) list
    }
    class VectorIndex {
        +build(circulars) dict
        +search(query, top_k, circular_id) list
        +is_empty() bool
        +stats() dict
    }
    class ChatbotService {
        +answer(question, top_k, circular_id) dict
    }

    NLPPipeline <|-- AIEngine : extends
    AIEngine ..> LLMSummarizer : uses (LLM summary,\nBART fallback)
    ChatbotService ..> VectorIndex : hybrid retrieval\n+ relevance gate
    ChatbotService ..> LLMSummarizer : query rewrite\n+ grounded answer
    ChatbotService ..> AIEngine : extractive fallback
```

> `AIEngine` extends `NLPPipeline` (inheriting the loaded spaCy/BERT/SBERT
> models) and delegates fluent summarization to `LLMSummarizer`, falling back to
> its own BART path when Ollama is unavailable. `ChatbotService` composes
> `VectorIndex` (retrieval + the relevance gate) and `LLMSummarizer` (query
> rewriting and grounded generation), with `AIEngine`'s QA reader as the
> extractive fallback.
