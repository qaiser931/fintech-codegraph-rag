# CodeGraph workspace interface

The Streamlit UI uses a compact light dashboard: a short workspace header, a left question editor, a right starter-investigation panel, and a slim access sidebar. Blue actions, white cards and a soft gray background replace the large dark hero. Source, call-path and code-match tabs remain below the investigation. Styling is local in `ui/styles.css`; no external fonts, images or additional UI packages are required.

The native Streamlit light palette is configured in `.streamlit/config.toml`. Restart Streamlit from the project root after applying the update, then refresh the browser. The stylesheet also gives custom cards explicit readable colors when a browser has a saved dark preference. `.streamlit/secrets.toml` remains ignored and is never included in this update.

Choose an access role, then use **Explore code** to retrieve evidence or **Generate answer** to ask the configured model. Sample-question buttons fill the editor without sending a request. The optional stack trace is collapsed until needed. Opening a source uses the existing authenticated client and the selected role.

Changing the question, trace, role, mode or API target clears the previous result and opened sources. Public demo visitors cannot edit the API target. Connection settings are available in the local sidebar. API health is checked manually, clearly marked as the last check, and cleared if the API address changes. A successful HTTP response is only shown as healthy if its status is `healthy`.

Answer evidence status remains visible above the answer. Insufficient or conflicting evidence is not presented as a supported answer. Query telemetry is available in an expander; source references are directly accessible. The flat returned call sequence counts as one path, with individually numbered steps in the Call path tab.

Run the existing offline suite and the added UI interaction checks:

```powershell
& .\.venv\Scripts\python.exe scripts\run_offline_tests.py
& .\.venv\Scripts\python.exe -m pytest tests\test_ui_polish.py -q
```

The tests use mocked API calls. They do not establish live retrieval latency or generated-answer quality. The earlier limited Q01 diagnostic and its relevance/correctness limitations still apply.

After changing the UI/theme files, restart Streamlit from the canonical D project using the existing API URL and authentication environment. Do not expose the API or Ollama to share the UI. In the terminal that is running only the project UI, press Ctrl+C, then run:

```powershell
Set-Location 'D:\Personal\fintech-codegraph-rag'
$env:CODEGRAPH_API_URL = 'http://127.0.0.1:8001'
& .\.venv\Scripts\python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501
```
