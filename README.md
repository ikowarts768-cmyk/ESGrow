# ESGrow

ESGrow is a simple ESG tracking system for monitoring Environmental, Social, and Governance performance for companies, with a practical focus on Zambia.

The goal is to build a real-world business tool while learning Python step by step.

## Why This Project Exists

Companies, investors, and students need simple ways to understand how businesses perform beyond profit alone. ESGrow is designed to help track company performance across:

- Environmental responsibility
- Social impact
- Governance quality

The project is also a learning journey: it keeps the code understandable, practical, and beginner friendly.

## Current Status

ESGrow now includes a recovered working prototype from the earlier ESGPulse project.

Current setup:

- Project instructions saved in `AGENTS.md`
- GitHub repository connected
- FastAPI backend restored
- Jinja2 HTML templates restored
- SQLite database restored with sample Zambia company data
- ESG scoring engine restored
- CSV batch importer restored
- Render deployment config restored

Recovered data includes 22 companies, 7 sectors, 24 ESG indicators, and calculated ESG scores.

## Planned Features

- ESG scoring system
- Company data input
- Basic dashboard or output report
- Clear explanations of ESG scores
- Possible API integration later
- Deployment, likely using Render

## Tech Stack

- Python
- Git and GitHub
- FastAPI
- Jinja2 templates
- SQLAlchemy
- SQLite for local development
- PostgreSQL for Render deployment

More tools may be added later only when they are clearly useful.

## How To Run Locally

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

Start the app:

```bash
uvicorn api:app --reload --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

## Project Principles

- Keep the structure simple.
- Write beginner-friendly Python.
- Explain business logic clearly.
- Avoid overengineering.
- Focus on practical ESG and investment use cases.
- Make small improvements step by step.

## Creator

Created by Jonathan Ikowa.

Jonathan is a Business Administration student, graphic designer, and beginner Python learner interested in ESG, investments, and strategy.
