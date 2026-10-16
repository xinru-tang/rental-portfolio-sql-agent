# Rental Portfolio SQL Agent

A 14-table apartment-portfolio database with a natural-language query assistant and Streamlit interface.

## Features

- SQLite schema for properties, units, tenants, leases, payments, parking, maintenance, and technicians.
- Faker-generated synthetic data and checks for lease overlaps, parking overlaps, and renewal chains.
- LLM-generated SQL with a single-statement SELECT/WITH filter and retry on invalid queries.
- Streamlit UI displaying the SQL, results, and retry trace.

## Run locally

Python 3.10+:

```bash
python -m venv .venv
# Activate the environment for your operating system.
pip install -r requirements.txt
python seed_data.py
# Copy .env.example to .env and supply your own OPENAI_API_KEY.
streamlit run app.py
```

For the CLI, use `python agent.py`. Run commands from the repository root. The SQLite database is generated locally; all seeded records are synthetic.

Try “Which property has the lowest occupancy rate?” or “Who are the top three technicians by completed maintenance requests?”

## Evaluation

`python eval_apartment.py` runs the supplied answer and adversarial-request evaluation using your API key. It makes paid calls and was not rerun against the live API during packaging. The SQL filter is a demo guardrail, not a complete security boundary; use only the synthetic demonstration database.

## Attribution

The original Group 2 design is by Linyu Zhao, Yuhan Luan, Xin Cai, and Xinru Tang. The group report is in `reports/`. The Python/SQLite implementation and AI assistant are presented as Xinru Tang's independent extension. Original implementation notes are in `docs/original-project-notes.md`.
