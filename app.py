"""
OpsData-Ingest: Partner Sanitize & RL Transformer
-----------------------------------------------------
A single-file Streamlit prototype demonstrating an end-to-end pipeline that:
  1. Ingests raw operational data (Slack / Jira style exports).
  2. Scrubs PII (emails, phone numbers, personal names).
  3. Transforms the cleaned data into an RL-ready execution trace schema.

Run with:
    pip install streamlit
    streamlit run app.py
"""

import copy
import json
import re
import uuid

import streamlit as st

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------
# Embedded "raw" operational logs so the app works instantly during a live
# demo without requiring a manual file upload. Each record represents a
# support/ops thread (Jira ticket or Slack channel) with a clear
# Context -> Action -> Outcome narrative, plus mock PII sprinkled throughout
# to exercise the scrubbing pipeline.
SAMPLE_DATA = [
    {
        "ticket_id": "JIRA-4521",
        "source_platform": "Jira",
        "thread": [
            {
                "author": "Sarah Connor",
                "email": "sarah.connor@acme.com",
                "phone": "(555) 123-4567",
                "text": (
                    "Context: Customer reported the checkout page timing out "
                    "during the payment step for orders over $500. Sarah Connor "
                    "escalated after reproducing on staging."
                ),
            },
            {
                "author": "Mike Chen",
                "email": "mike.chen@acme.com",
                "phone": "555-987-6543",
                "text": (
                    "Action: Mike Chen investigated the payment gateway logs, "
                    "found the timeout config set to 5s, increased it to 30s, "
                    "and redeployed payment-service v2.3.1. Reach me at "
                    "mike.chen@acme.com or 555-987-6543 if follow-up is needed."
                ),
            },
            {
                "author": "Sarah Connor",
                "email": "sarah.connor@acme.com",
                "phone": "(555) 123-4567",
                "text": (
                    "Outcome: Verified the fix in staging, checkout success "
                    "rate restored to 99.8%. Closing ticket."
                ),
            },
        ],
    },
    {
        "ticket_id": "SLACK-eng-ops-8831",
        "source_platform": "Slack",
        "thread": [
            {
                "author": "Devon Park",
                "email": "devon.park@acme.com",
                "phone": "555-234-9981",
                "text": (
                    "Context: Devon Park flagged that the nightly ETL job into "
                    "the warehouse has been failing silently for 3 days, "
                    "customer dashboards are showing stale data."
                ),
            },
            {
                "author": "Priya Sharma",
                "email": "priya.sharma@acme.com",
                "phone": "(555) 445-1120",
                "text": (
                    "Action: Priya Sharma traced it to a schema drift in the "
                    "orders table, patched the Airflow DAG's schema validator, "
                    "and backfilled the missing partitions. Ping "
                    "priya.sharma@acme.com or (555) 445-1120 for details."
                ),
            },
            {
                "author": "Devon Park",
                "email": "devon.park@acme.com",
                "phone": "555-234-9981",
                "text": (
                    "Outcome: Devon Park confirmed dashboards are current as "
                    "of the latest run. Added a schema-drift alert to prevent "
                    "recurrence."
                ),
            },
        ],
    },
    {
        "ticket_id": "JIRA-4599",
        "source_platform": "Jira",
        "thread": [
            {
                "author": "Alex Rivera",
                "email": "alex.rivera@acme.com",
                "phone": "555-678-2234",
                "text": (
                    "Context: Alex Rivera reported that partner API "
                    "credentials for a Tier-1 customer were rotated but the "
                    "webhook endpoint kept receiving 401s."
                ),
            },
            {
                "author": "Sarah Connor",
                "email": "sarah.connor@acme.com",
                "phone": "(555) 123-4567",
                "text": (
                    "Action: Sarah Connor rotated the stored secret in the "
                    "vault, updated the webhook signing key, and re-ran the "
                    "partner's integration test suite."
                ),
            },
            {
                "author": "Alex Rivera",
                "email": "alex.rivera@acme.com",
                "phone": "555-678-2234",
                "text": (
                    "Outcome: Webhook deliveries returned to 200 OK, partner "
                    "confirmed data flow resumed normally."
                ),
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# Regex patterns used for PII detection
# ---------------------------------------------------------------------------
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_PATTERN = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")


# ---------------------------------------------------------------------------
# Pipeline: Step 1 - PII scrubbing
# ---------------------------------------------------------------------------
def build_name_map(data):
    """Collect distinct author names in the dataset and map each to a
    synthetic, stable user ID (User_101, User_102, ...)."""
    names = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("author"), str):
                names.add(node["author"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    # Sorted for deterministic, stable ID assignment across runs.
    return {name: f"User_{101 + i}" for i, name in enumerate(sorted(names))}


def scrub_pii(data, options):
    """Scrub emails, phone numbers, and personal names from a nested JSON
    structure according to the toggles in `options`.

    Returns a tuple of (cleaned_data, stats) where stats counts how many
    entities of each type were scrubbed.
    """
    cleaned = copy.deepcopy(data)
    stats = {"emails": 0, "phones": 0, "names": 0}

    name_map = build_name_map(cleaned) if options["scrub_names"] else {}
    # Longest names first so "Sarah Connor" is replaced before a lone "Sarah"
    # could accidentally match a different person.
    ordered_names = sorted(name_map, key=len, reverse=True)

    def scrub_text(text):
        if options["scrub_emails"]:
            text, count = EMAIL_PATTERN.subn("[ANONYMIZED_EMAIL]", text)
            stats["emails"] += count
        if options["scrub_phones"]:
            text, count = PHONE_PATTERN.subn("[ANONYMIZED_PHONE]", text)
            stats["phones"] += count
        if options["scrub_names"]:
            for name in ordered_names:
                text, count = re.subn(re.escape(name), name_map[name], text)
                stats["names"] += count
        return text

    def walk(node, key=None):
        if isinstance(node, dict):
            return {k: walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, str):
            if key == "author" and options["scrub_names"]:
                if node in name_map:
                    stats["names"] += 1
                return name_map.get(node, node)
            return scrub_text(node)
        return node

    return walk(cleaned), stats


# ---------------------------------------------------------------------------
# Pipeline: Step 2 - RL schema transformation
# ---------------------------------------------------------------------------
def transform_to_rl_schema(cleaned_data):
    """Restructure cleaned, nested ticket/thread JSON into flat RL-ready
    execution traces with a Context -> Action -> Outcome shape."""
    traces = []
    for record in cleaned_data:
        prompt_context, action_taken, result_outcome = "", "", ""
        for message in record.get("thread", []):
            text = message.get("text", "")
            if text.startswith("Context:"):
                prompt_context = text.removeprefix("Context:").strip()
            elif text.startswith("Action:"):
                action_taken = text.removeprefix("Action:").strip()
            elif text.startswith("Outcome:"):
                result_outcome = text.removeprefix("Outcome:").strip()

        traces.append({
            "trace_id": record.get("ticket_id", str(uuid.uuid4())),
            "source_platform": record.get("source_platform", "Unknown"),
            "prompt_context": prompt_context,
            "action_taken": action_taken,
            "result_outcome": result_outcome,
            "anonymization_status": "Cleaned & PII Verified",
        })
    return traces


# ---------------------------------------------------------------------------
# Display helper: highlight raw PII so the "before" state is obviously messy
# ---------------------------------------------------------------------------
def highlight_raw_json(raw_data):
    """Return an HTML-escaped, pretty-printed JSON string with emails,
    phone numbers, and known author names wrapped in <mark> for visual
    emphasis in the Raw Input tab."""
    raw_str = json.dumps(raw_data, indent=2)
    raw_str = (
        raw_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )

    def mark(pattern, text, color):
        return pattern.sub(
            lambda m: f'<mark style="background:{color};">{m.group(0)}</mark>',
            text,
        )

    raw_str = mark(EMAIL_PATTERN, raw_str, "#ffb3b3")
    raw_str = mark(PHONE_PATTERN, raw_str, "#ffd699")

    for name in build_name_map(raw_data):
        raw_str = re.sub(
            re.escape(name),
            f'<mark style="background:#b3d9ff;">{name}</mark>',
            raw_str,
        )
    return raw_str


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="OpsData-Ingest",
    page_icon="\U0001F9F9",
    layout="wide",
)

st.title("OpsData-Ingest: Partner Sanitize & RL Transformer")
st.caption(
    "PII scrubbing + RL execution-trace transformation for partner "
    "operational data (Slack, Jira, and similar exports)."
)

# --- Sidebar: scrubbing controls -------------------------------------------
with st.sidebar:
    st.header("Scrubbing Settings")
    scrub_emails = st.toggle("Scrub Emails", value=True)
    scrub_phones = st.toggle("Scrub Phone Numbers", value=True)
    scrub_names = st.toggle("Anonymize User Names", value=True)

    st.divider()
    st.header("Data Source")
    uploaded_file = st.file_uploader("Upload a JSON file", type=["json"])
    load_sample = st.button("Load Sample Dataset", use_container_width=True)

options = {
    "scrub_emails": scrub_emails,
    "scrub_phones": scrub_phones,
    "scrub_names": scrub_names,
}

# --- Data loading (persisted in session state) ------------------------------
if load_sample:
    st.session_state["raw_data"] = SAMPLE_DATA
elif uploaded_file is not None:
    st.session_state["raw_data"] = json.load(uploaded_file)

raw_data = st.session_state.get("raw_data")

if raw_data is None:
    st.info("Upload a JSON file or click **Load Sample Dataset** in the sidebar to begin.")
    st.stop()

# --- Run the pipeline --------------------------------------------------------
cleaned_data, pii_stats = scrub_pii(raw_data, options)
rl_traces = transform_to_rl_schema(cleaned_data)
total_pii_scrubbed = sum(pii_stats.values())

# --- Summary metrics ---------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Total Records Processed", len(raw_data))
col2.metric("PII Entities Scrubbed", total_pii_scrubbed)
col3.metric("Pipeline Status", "Ready for Training")

with st.expander("PII Scrub Breakdown"):
    st.write(
        f"Emails: **{pii_stats['emails']}** &nbsp;|&nbsp; "
        f"Phone numbers: **{pii_stats['phones']}** &nbsp;|&nbsp; "
        f"Names: **{pii_stats['names']}**"
    )

st.divider()

# --- Raw vs. transformed views ------------------------------------------------
tab_raw, tab_rl = st.tabs(["\U0001F4C4 Raw Input JSON", "✅ Transformed RL-Ready JSON"])

with tab_raw:
    st.caption("Sensitive data highlighted in place: emails (red), phone numbers (orange), names (blue).")
    st.markdown(
        f'<div style="max-height:600px; overflow-y:auto; padding:1rem; '
        f'background:rgba(128,128,128,0.08); border-radius:0.5rem; '
        f'font-family:monospace; white-space:pre-wrap; font-size:0.85rem;">'
        f"{highlight_raw_json(raw_data)}</div>",
        unsafe_allow_html=True,
    )

with tab_rl:
    st.caption("Flattened execution traces, ready to feed into an RL training pipeline.")
    st.json(rl_traces)

st.divider()

# --- Export & downstream actions ---------------------------------------------
action_col1, action_col2 = st.columns(2)

with action_col1:
    st.download_button(
        label="\U0001F4E5 Download Transformed RL JSON",
        data=json.dumps(rl_traces, indent=2),
        file_name="processed_rl_dataset.json",
        mime="application/json",
        use_container_width=True,
    )

with action_col2:
    if st.button("\U0001F680 Simulate Webhook to Ingestion Bucket", use_container_width=True):
        with st.spinner("Dispatching payload..."):
            st.success("Payload dispatched to S3 Ingestion Bucket!")
