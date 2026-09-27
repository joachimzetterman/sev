# Security eval taxonomy

Version: `sev-taxonomy-0.1`. Generated from `sev/taxonomy.py`.

## Annotation rules

Judge the before-to-after behaviour using only the supplied diff and context. Labels describe relevance or change, except the explicitly directional PRIVILEGE_INCREASE. A fix can be YES. NO never certifies security. Pure renames and comments do not change runtime behaviour.

- **YES:** Supplied evidence establishes the defined change or relevance; this does not mean vulnerable.
- **NO:** Supplied evidence establishes that the defined change or relevance is absent; this does not mean secure.
- **UNKNOWN:** Supplied evidence is conflicting or semantically ambiguous and does not support YES or NO.
- **INSUFFICIENT_CONTEXT:** A specific missing fact outside the supplied input is needed to decide YES or NO.

UNKNOWN records conflicting or semantically ambiguous evidence. INSUFFICIENT_CONTEXT identifies a specific missing deciding fact. An algorithm that cannot answer may separately abstain (`probabilities: null`); this is not a gold semantic state. A model's low confidence is also not an annotation of UNKNOWN.

An absent route-level check does not establish a vulnerability. A supplied applicable middleware check can establish control evidence, while authorization relevance remains YES in both cases. PRIVILEGE_INCREASE often needs effective policy, not just a changed Allow statement. A future control-evidence eval should be separately defined if the pilot needs it.

## Overlap and excluded labels

AUTHORIZATION_RELEVANT is broad; AUTHORIZATION_BOUNDARY_CHANGE concerns enforcement; PRIVILEGE_INCREASE is directional; TENANT_BOUNDARY_CHANGE concerns an explicit partition. They may all be YES on one change, but a correctly protected new route can be relevant without proving an altered gate or effective privilege increase. Do not enforce these relations as automatic gold labels; measure annotation consistency first.

SENSITIVE_DATA_HANDLING asks what data is handled; DATA_EXPOSURE_CHANGE asks who can observe it. NETWORK_EGRESS_CHANGE is concrete transport behaviour; TRUST_BOUNDARY_CHANGE requires explicit trust-domain evidence. The latter is a candidate for removal if raters cannot agree.

SECRET_EXPOSURE_RISK is deferred to deterministic scanners plus contextual data handling. EXTERNAL_INTERACTION_CHANGE overlaps egress, exposure and trust. AUDIT_EVENT_REQUIRED and SECURITY_REVIEW_REQUIRED require an organisation's policy and are deferred to routing. Keep the 14 definitions provisional until the independent annotation pilot is complete.

## Per-eval definitions and examples

### AUTHENTICATION_CHANGE

Does this change how a principal proves identity or how an authenticated session is established, validated, or revoked?

Includes credentials, MFA, token verification, login/session lifetime and revocation. Excludes permission decisions and cosmetic login UI edits.

- **YES:** Require MFA before session creation.
- **NO:** Change the login button colour.
- **UNKNOWN:** Switch between two authentication modes whose documented semantics conflict.
- **INSUFFICIENT_CONTEXT:** Replace authenticate() with establish() without either helper's definition.

### AUTHORIZATION_RELEVANT

Does this change a decision, operation, or resource selection whose behaviour depends on which principal may act on which resource?

Includes access checks, protected routes, ownership filters, role assignments and IAM. A correct security fix is still relevant. Mere security words or a pure rename are not sufficient.

- **YES:** Add a correctly protected invoice-download route.
- **NO:** Rename a local variable without changing access or resource selection.
- **UNKNOWN:** Change a flag described both as display-only and as an access switch.
- **INSUFFICIENT_CONTEXT:** Change dispatch(op) with no description of op or dispatch.

### AUTHORIZATION_BOUNDARY_CHANGE

Does this change the rule or enforcement point that determines which principals may perform which operations on which resources?

Includes strengthening and weakening gates, IAM rules and ownership conditions. Adding an operation under a visibly unchanged gate is authorization-relevant but does not alone prove this label.

- **YES:** Add an ownership predicate to an existing read route.
- **NO:** Optimise the implementation while preserving the visible allow predicate.
- **UNKNOWN:** Two supplied policy declarations disagree about which gate is authoritative.
- **INSUFFICIENT_CONTEXT:** Replace authorize(user, item) with permit(user, item) without either helper's enforcement semantics.

### PRIVILEGE_INCREASE

Does the after-state allow a principal an action or resource scope that the before-state denied?

Directional and about effective permissions: scope expansion, weaker conditions and new delegation count. Permission reductions are NO. A new route with unknown inherited access policy is not proof of an increase.

- **YES:** Change a self-contained allow policy from read to read plus write.
- **NO:** Remove write from a fully supplied policy.
- **UNKNOWN:** Supplied policy precedence rules are mutually inconsistent.
- **INSUFFICIENT_CONTEXT:** Add an IAM Allow when the applicable boundary or explicit Deny policy is missing.

### TENANT_BOUNDARY_CHANGE

Does this change how a tenant is selected, attached, checked, or isolated when accessing tenant-scoped resources?

Tenant means an explicit organisation/account partition, not any user ID. Covers query filters, caches, storage namespaces and routing. Includes fixes that strengthen isolation.

- **YES:** Add tenant_id to a shared cache key.
- **NO:** Change a single-tenant theme constant.
- **UNKNOWN:** The supplied contract uses account to mean both a tenant and a user.
- **INSUFFICIENT_CONTEXT:** Change workspace scoping without a definition of whether workspaces are tenant boundaries.

### SENSITIVE_DATA_HANDLING

Does this change the collection, use, transformation, storage, transmission, logging, or deletion of data identified as sensitive?

Sensitive includes credentials, tokens, personal contact/identity, health and financial records, or an explicit supplied data classification. Access to a table called data alone is insufficient.

- **YES:** Add email addresses to an export, or redact them from logs.
- **NO:** Change the rendering of explicitly public product names.
- **UNKNOWN:** Supplied data classifications disagree about a field.
- **INSUFFICIENT_CONTEXT:** Log payload without its schema or classification.

### DATA_EXPOSURE_CHANGE

Does this change the audience or surface through which existing data can be observed?

Includes response fields, logs, exports, public storage and analytics recipients; either direction counts, regardless of sensitivity. Internal computations with unchanged observability are NO.

- **YES:** Remove a field from a public response.
- **NO:** Refactor local calculation with identical observable output.
- **UNKNOWN:** Output contracts disagree about whether a field is observable.
- **INSUFFICIENT_CONTEXT:** Pass a record into an unseen emit() helper.

### UNTRUSTED_INPUT_HANDLING_CHANGE

Does this change parsing, validation, transformation, or use of input supplied by a less-trusted actor?

Requires a visible or stated source such as requests, uploads or external messages. Includes safe validation fixes. Variable names alone do not prove attacker control.

- **YES:** Validate a request path parameter before using it in a query.
- **NO:** Sort a literal list of internal constants.
- **UNKNOWN:** The supplied contract contradicts itself about who controls a value.
- **INSUFFICIENT_CONTEXT:** Change parsing of value without its source or calling contract.

### TRUST_BOUNDARY_CHANGE

Does this change a mechanism by which data or authority crosses between explicitly different trust domains?

Includes delegation, sandbox boundaries and external webhook acceptance. An external destination alone is not proof of different trust. Use more concrete labels alongside this one and retain only if agreement supports it.

- **YES:** Allow an external webhook to trigger an internal privileged operation.
- **NO:** Refactor communication within a stated single trust domain.
- **UNKNOWN:** Two supplied architecture descriptions assign different trust to a service.
- **INSUFFICIENT_CONTEXT:** Replace an internal service call with a new endpoint of unknown ownership/trust.

### NETWORK_EGRESS_CHANGE

Does this change outbound connection initiation, destination, protocol, routing, or permissions to send network traffic?

Includes HTTP destinations, DNS, proxies and outbound firewall rules. Excludes inbound-only exposure and pure changes to a payload sent through an otherwise unchanged connection.

- **YES:** Change a webhook destination from an internal host to an external host.
- **NO:** Change an inbound listener port only.
- **UNKNOWN:** Conflicting supplied routing rules disagree about which destination is used.
- **INSUFFICIENT_CONTEXT:** Change a transport configuration key without its meaning or default.

### CODE_EXECUTION_RELEVANT

Does this change launching processes, interpreting code, loading executable plugins, or selecting executable content?

Includes shell/process APIs, eval and dynamic executable loading. Ordinary application calculations and SQL alone are excluded; this is relevance, not a claim of injection.

- **YES:** Replace shell interpolation with an argument-array subprocess call.
- **NO:** Change arithmetic in a normal application function.
- **UNKNOWN:** An interpreter's supplied specification contradicts itself about executable expressions.
- **INSUFFICIENT_CONTEXT:** Call a new run() helper whose implementation is absent.

### FILESYSTEM_ACCESS_CHANGE

Does this change file or directory targets, operations, access modes, permissions, or path resolution at runtime?

Covers reads, writes, deletes, traversal, symlinks and storage mounts. A source-code file being edited does not itself count.

- **YES:** Constrain uploaded filenames before writing them to disk.
- **NO:** Edit an in-memory sorting function.
- **UNKNOWN:** Supplied path mappings resolve the same mount to contradictory locations.
- **INSUFFICIENT_CONTEXT:** Change save(blob) without knowing whether save uses memory, database or filesystem.

### DESTRUCTIVE_OPERATION

Does this change an operation that deletes or irreversibly overwrites durable data/resources, or disrupts their availability?

Includes adding, removing, guarding or broadening delete/drop/truncate operations and destructive infrastructure changes. Removing an item from a temporary local list is NO.

- **YES:** Add a WHERE restriction to an existing durable-record delete.
- **NO:** Remove an element from a temporary list.
- **UNKNOWN:** The supplied transaction contract gives contradictory rollback guarantees.
- **INSUFFICIENT_CONTEXT:** Change purge() without its side effects or persistence contract.

### ADDITIONAL_CONTEXT_REQUIRED

Is a specific missing fact necessary to decide at least one of the other thirteen taxonomy questions for this change?

YES requires naming the missing fact and affected question. Merely wanting more repository context is not enough. NO means these narrow questions can be judged, never that security is established. Judge this last over the whole taxonomy, even when only a subset is requested.

- **YES:** Effective privilege cannot be decided without the inherited role policy.
- **NO:** A fully shown literal-only UI colour edit resolves all narrow questions.
- **UNKNOWN:** It is unclear whether the conflicting information can be resolved by an external fact.
- **INSUFFICIENT_CONTEXT:** A binary-only diff has no decodable description of the changed component.
