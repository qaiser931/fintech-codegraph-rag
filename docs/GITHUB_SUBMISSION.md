# Public GitHub delivery

The lab requires a public repository, not only a ZIP. Publish the clean `project/`
folder from this bundle. It excludes the laptop's real `.env`, virtual environment,
stored indices and raw telemetry. Do not replace the laptop deployment with this
folder: use the guarded patch/helper for that existing deployment.

Create an empty public GitHub repository under your account. In a terminal opened
inside this clean project folder, use the actual repository URL:

```powershell
git init
git add .
git commit -m "Submit Project 10 fintech codebase graph RAG"
git branch -M main
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
git push -u origin main
```

The URL above is a placeholder, not an existing repository. Replace it before running.
If a repo already exists, use its existing checkout/remote rather than force-pushing.
Confirm the repository opens publicly and the README Mermaid diagram renders.
Submit its real URL along with the real demo-video URL. No repository was published
or remote Git history modified by preparation of this bundle.
