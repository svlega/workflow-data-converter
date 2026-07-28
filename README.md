# OpsData-Ingest: Partner Sanitize & RL Transformer

A single-file Streamlit prototype demonstrating an end-to-end pipeline for
sanitizing partner operational data (Slack/Jira-style exports) and
transforming it into a reinforcement-learning-ready execution trace schema.

## What it does

1. **Ingests** raw operational logs — either an uploaded JSON file or an
   embedded sample dataset (mock Jira tickets / Slack threads).
2. **Scrubs PII** using regex-based detection:
   - Email addresses → `[ANONYMIZED_EMAIL]`
   - Phone numbers → `[ANONYMIZED_PHONE]`
   - Personal names → consistent synthetic IDs (`User_101`, `User_102`, ...)
3. **Transforms** the cleaned records into a flat RL execution-trace schema:
   `trace_id`, `source_platform`, `prompt_context`, `action_taken`,
   `result_outcome`, `anonymization_status`.
4. **Displays** side-by-side tabs (highlighted raw input vs. clean RL-ready
   output), summary metrics, a JSON download button, and a mock webhook
   dispatch action.

## Requirements

- Python 3
- `streamlit` (see `requirements.txt`)

## Run locally

```bash
pip3 install -r requirements.txt
python3 -m streamlit run app.py
```

Then open `http://localhost:8501` in your browser (Streamlit opens it
automatically in most setups).

## Usage

1. In the sidebar, toggle which PII types to scrub (emails, phone numbers,
   names).
2. Click **Load Sample Dataset** to instantly populate the pipeline, or
   upload your own JSON file.
3. Review the **Raw Input JSON** tab (sensitive data highlighted in place)
   and the **Transformed RL-Ready JSON** tab (cleaned execution traces).
4. Use **Download Transformed RL JSON** to export the result, or
   **Simulate Webhook to Ingestion Bucket** to preview the downstream
   dispatch step.

## Project structure

```
workflow-data-converter/
├── app.py            # Full Streamlit app: UI, PII scrubbing, RL transform
├── requirements.txt   # Python dependencies
└── .gitignore
```

## Deployment

This app is designed to deploy as-is on
[Streamlit Community Cloud](https://share.streamlit.io): point it at this
repo, branch `main`, main file `app.py`.
