# Using goose safely

goose works like Claude Cowork: you give it a folder and a task, and it reads files, writes files, and runs commands to get it done. It runs a **local model**, so it is slower and makes more mistakes than Claude. Check its work.

## The one rule: read before you click "Allow"

goose is set to **ask before every action**. When it wants to write a file or run a command, you'll see **Allow** / **Deny**.

- **Allow** only if you understand what it's about to do and it's what you asked for.
- **Deny** anything that deletes files, touches folders you didn't give it, connects to the internet (`curl`, `wget`, `Invoke-WebRequest`, URLs), or installs software.
- A document can contain hidden instructions that try to hijack the assistant ("prompt injection"). If goose suddenly wants to do something unrelated to your request after reading a file, **Deny** and tell Rob.

## Data

- **P1–P2 data only** until Rob says otherwise. No client records, PHI, or anything under a data use agreement.
- Work in a dedicated folder (e.g., `Documents/AVAL-AI-work`) and give goose only that folder.

## Good first tasks

- "Summarize `report.pdf` in 5 bullets for a county director."
- "Clean `survey.csv`: trim whitespace, standardize the date column, save as `survey_clean.csv`."
- "Draft a reply to the email in `email.txt`, friendly and short."

## Don't

- Don't switch goose to **Autonomous** or **Smart Approval** mode.
- Don't install extensions yourself. Ask Rob, who will vet and add them for everyone.
- Don't change the model or provider in Settings. The next update resets it anyway.
- Don't treat answers as facts. Local models make up citations and numbers. Verify anything you'll send or publish.
