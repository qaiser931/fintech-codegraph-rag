# CodeGraph workspace interface

The Streamlit UI uses a teal and navy header, compact access sidebar, an investigation card and separate source, call-path and code-match tabs. Styling is local in `ui/styles.css`; no external fonts, images or additional UI packages are required. Custom cards have responsive spacing and use the active Streamlit text and surface colors.

Choose an access role, then use **Explore code** to retrieve evidence or **Generate answer** to ask the configured model. Sample-question buttons fill the editor without sending a request. The optional stack trace is collapsed until needed. Opening a source uses the existing authenticated client and the selected role.

Changing the question, trace, role, mode or API target clears the previous result and opened sources. Public demo visitors cannot edit the API target. Connection settings are available in the local sidebar. API health is checked manually, clearly marked as the last check, and cleared if the API address changes. A successful HTTP response is only shown as healthy if its status is `healthy`.

Answer evidence status remains visible above the answer. Insufficient or conflicting evidence is not presented as a supported answer. Query telemetry is available in an expander; source references are directly accessible. The flat returned call sequence counts as one path, with individually numbered steps in the Call path tab.

Run the existing offline suite and the added UI interaction checks:

```powershell
& .\.venv\Scripts\python.exe scripts\run_offline_tests.py
& .\.venv\Scripts\python.exe -m pytest tests\test_ui_polish.py -q
```

The tests use mocked API calls. They do not establish live retrieval latency or generated-answer quality. The earlier limited Q01 diagnostic and its relevance/correctness limitations still apply.

After changing the UI files, refresh the running project UI. If a different checkout is serving the UI, launch Streamlit from the canonical D project using the existing API URL and authentication environment. Do not expose the API or Ollama to share the UI.
