"""Versioned annotation contract; definitions are shared by prompts and documentation."""

VERSION = "sev-taxonomy-0.1"
STATES = ("YES", "NO", "UNKNOWN", "INSUFFICIENT_CONTEXT")
STATE_DEFINITIONS = {
    "YES": "Supplied evidence establishes the defined change or relevance; this does not mean vulnerable.",
    "NO": "Supplied evidence establishes that the defined change or relevance is absent; this does not mean secure.",
    "UNKNOWN": "Supplied evidence is conflicting or semantically ambiguous and does not support YES or NO.",
    "INSUFFICIENT_CONTEXT": "A specific missing fact outside the supplied input is needed to decide YES or NO.",
}

# Deliberately omit generic security-review and audit requirements: they need an
# organisation's policy. Each definition describes the actual before -> after edit.
_ROWS = [
    ("AUTHENTICATION_CHANGE",
     "Does this change how a principal proves identity or how an authenticated session is established, validated, or revoked?",
     "Includes credentials, MFA, token verification, login/session lifetime and revocation. Excludes permission decisions and cosmetic login UI edits.",
     "Require MFA before session creation.", "Change the login button colour.",
     "Switch between two authentication modes whose documented semantics conflict.",
     "Replace authenticate() with establish() without either helper's definition."),
    ("AUTHORIZATION_RELEVANT",
     "Does this change a decision, operation, or resource selection whose behaviour depends on which principal may act on which resource?",
     "Includes access checks, protected routes, ownership filters, role assignments and IAM. A correct security fix is still relevant. Mere security words or a pure rename are not sufficient.",
     "Add a correctly protected invoice-download route.", "Rename a local variable without changing access or resource selection.",
     "Change a flag described both as display-only and as an access switch.",
     "Change dispatch(op) with no description of op or dispatch."),
    ("AUTHORIZATION_BOUNDARY_CHANGE",
     "Does this change the rule or enforcement point that determines which principals may perform which operations on which resources?",
     "Includes strengthening and weakening gates, IAM rules and ownership conditions. Adding an operation under a visibly unchanged gate is authorization-relevant but does not alone prove this label.",
     "Add an ownership predicate to an existing read route.", "Optimise the implementation while preserving the visible allow predicate.",
     "Two supplied policy declarations disagree about which gate is authoritative.",
     "Replace authorize(user, item) with permit(user, item) without either helper's enforcement semantics."),
    ("PRIVILEGE_INCREASE",
     "Does the after-state allow a principal an action or resource scope that the before-state denied?",
     "Directional and about effective permissions: scope expansion, weaker conditions and new delegation count. Permission reductions are NO. A new route with unknown inherited access policy is not proof of an increase.",
     "Change a self-contained allow policy from read to read plus write.", "Remove write from a fully supplied policy.",
     "Supplied policy precedence rules are mutually inconsistent.",
     "Add an IAM Allow when the applicable boundary or explicit Deny policy is missing."),
    ("TENANT_BOUNDARY_CHANGE",
     "Does this change how a tenant is selected, attached, checked, or isolated when accessing tenant-scoped resources?",
     "Tenant means an explicit organisation/account partition, not any user ID. Covers query filters, caches, storage namespaces and routing. Includes fixes that strengthen isolation.",
     "Add tenant_id to a shared cache key.", "Change a single-tenant theme constant.",
     "The supplied contract uses account to mean both a tenant and a user.",
     "Change workspace scoping without a definition of whether workspaces are tenant boundaries."),
    ("SENSITIVE_DATA_HANDLING",
     "Does this change the collection, use, transformation, storage, transmission, logging, or deletion of data identified as sensitive?",
     "Sensitive includes credentials, tokens, personal contact/identity, health and financial records, or an explicit supplied data classification. Access to a table called data alone is insufficient.",
     "Add email addresses to an export, or redact them from logs.", "Change the rendering of explicitly public product names.",
     "Supplied data classifications disagree about a field.",
     "Log payload without its schema or classification."),
    ("DATA_EXPOSURE_CHANGE",
     "Does this change the audience or surface through which existing data can be observed?",
     "Includes response fields, logs, exports, public storage and analytics recipients; either direction counts, regardless of sensitivity. Internal computations with unchanged observability are NO.",
     "Remove a field from a public response.", "Refactor local calculation with identical observable output.",
     "Output contracts disagree about whether a field is observable.",
     "Pass a record into an unseen emit() helper."),
    ("UNTRUSTED_INPUT_HANDLING_CHANGE",
     "Does this change parsing, validation, transformation, or use of input supplied by a less-trusted actor?",
     "Requires a visible or stated source such as requests, uploads or external messages. Includes safe validation fixes. Variable names alone do not prove attacker control.",
     "Validate a request path parameter before using it in a query.", "Sort a literal list of internal constants.",
     "The supplied contract contradicts itself about who controls a value.",
     "Change parsing of value without its source or calling contract."),
    ("TRUST_BOUNDARY_CHANGE",
     "Does this change a mechanism by which data or authority crosses between explicitly different trust domains?",
     "Includes delegation, sandbox boundaries and external webhook acceptance. An external destination alone is not proof of different trust. Use more concrete labels alongside this one and retain only if agreement supports it.",
     "Allow an external webhook to trigger an internal privileged operation.", "Refactor communication within a stated single trust domain.",
     "Two supplied architecture descriptions assign different trust to a service.",
     "Replace an internal service call with a new endpoint of unknown ownership/trust."),
    ("NETWORK_EGRESS_CHANGE",
     "Does this change outbound connection initiation, destination, protocol, routing, or permissions to send network traffic?",
     "Includes HTTP destinations, DNS, proxies and outbound firewall rules. Excludes inbound-only exposure and pure changes to a payload sent through an otherwise unchanged connection.",
     "Change a webhook destination from an internal host to an external host.", "Change an inbound listener port only.",
     "Conflicting supplied routing rules disagree about which destination is used.",
     "Change a transport configuration key without its meaning or default."),
    ("CODE_EXECUTION_RELEVANT",
     "Does this change launching processes, interpreting code, loading executable plugins, or selecting executable content?",
     "Includes shell/process APIs, eval and dynamic executable loading. Ordinary application calculations and SQL alone are excluded; this is relevance, not a claim of injection.",
     "Replace shell interpolation with an argument-array subprocess call.", "Change arithmetic in a normal application function.",
     "An interpreter's supplied specification contradicts itself about executable expressions.",
     "Call a new run() helper whose implementation is absent."),
    ("FILESYSTEM_ACCESS_CHANGE",
     "Does this change file or directory targets, operations, access modes, permissions, or path resolution at runtime?",
     "Covers reads, writes, deletes, traversal, symlinks and storage mounts. A source-code file being edited does not itself count.",
     "Constrain uploaded filenames before writing them to disk.", "Edit an in-memory sorting function.",
     "Supplied path mappings resolve the same mount to contradictory locations.",
     "Change save(blob) without knowing whether save uses memory, database or filesystem."),
    ("DESTRUCTIVE_OPERATION",
     "Does this change an operation that deletes or irreversibly overwrites durable data/resources, or disrupts their availability?",
     "Includes adding, removing, guarding or broadening delete/drop/truncate operations and destructive infrastructure changes. Removing an item from a temporary local list is NO.",
     "Add a WHERE restriction to an existing durable-record delete.", "Remove an element from a temporary list.",
     "The supplied transaction contract gives contradictory rollback guarantees.",
     "Change purge() without its side effects or persistence contract."),
    ("ADDITIONAL_CONTEXT_REQUIRED",
     "Is a specific missing fact necessary to decide at least one of the other thirteen taxonomy questions for this change?",
     "YES requires naming the missing fact and affected question. Merely wanting more repository context is not enough. NO means these narrow questions can be judged, never that security is established. Judge this last over the whole taxonomy, even when only a subset is requested.",
     "Effective privilege cannot be decided without the inherited role policy.", "A fully shown literal-only UI colour edit resolves all narrow questions.",
     "It is unclear whether the conflicting information can be resolved by an external fact.",
     "A binary-only diff has no decodable description of the changed component."),
]

EVALS = {
    row[0]: dict(zip(("question", "definition", "positive", "negative", "ambiguous", "insufficient_context"), row[1:]))
    for row in _ROWS
}


def contract():
    return {"version": VERSION, "states": STATE_DEFINITIONS, "evals": EVALS}


def select(names=None):
    names = list(EVALS) if names is None else names
    if not names or len(set(names)) != len(names) or any(name not in EVALS for name in names):
        raise ValueError("evals must be unique names from the taxonomy")
    return {name: EVALS[name] for name in names}
