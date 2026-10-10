# Online demo and GitHub submission

A public GitHub repository is required by the lab. Store the clean `project/`
folder from this bundle there. It includes the public UI fix and final documentation.
For publication, create an empty Public repo at https://github.com/new and use the
commands in GITHUB_SUBMISSION.md with the actual repository URL. Do not use GitHub
Pages for this app; Pages serves static sites, while this project runs Python servers.

## Fast temporary demo

Keep Docker Desktop, the deployed API and Ollama running. In the existing project:

```powershell
& .\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\project10-online\share_online_demo.py" --project "$PWD"
```

The helper applies only the reviewed UI change, fixes the API destination on the
server, verifies ownership before stopping the old project UI, starts the new UI,
and opens a Cloudflare Quick Tunnel for port 8501. It downloads the official
64-bit Windows cloudflared executable into a new ignored telemetry folder. No
Docker rebuild, index rebuild, provider change or live LLM request is submitted.
The real HTTPS trycloudflare.com URL appears in the terminal. Open it on another
browser/device and check Explore, role switching and Open source. Sharing is not
verified until that remote browser check succeeds. Ctrl+C stops the tunnel this
helper started. Leave the laptop and local services running during the demo.

This is a temporary testing link, not permanent cloud hosting or a durable
submission artifact. Submit the public GitHub URL and recorded video as required.
If you later need independent hosting, use a server for FastAPI + Streamlit and
provide Ollama there or configure an external LLM provider through server secrets.
Never set a remote cloud UI's backend address to your laptop's loopback address.

The role selector is a demonstration over public synthetic sample code; it does
not authenticate website users. Do not use this public demo as a private production
codebase portal. Real private code requires an authenticated UI/user role binding.

Official references checked 2026-10-10:
- https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
- https://developers.cloudflare.com/tunnel/downloads/
- https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github

A pre-existing cloudflared config can prevent a Quick Tunnel; the helper does not
rename or delete a user's Cloudflare configuration. Share any actual error output
for a scoped fix. The Windows tunnel and public browser result are not verified
by the offline UI tests included with this bundle.
