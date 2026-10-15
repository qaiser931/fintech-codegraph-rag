import Link from "next/link"
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Code2,
  FileCheck2,
  GitPullRequest,
  Layers3,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react"
import { StackwiseBrand } from "@/components/stackwise-brand"

export default function HomePage() {
  return (
    <div className="sw-site">
      <a className="sw-skip" href="#main">
        Skip to content
      </a>
      <header className="sw-site-nav">
        <Link href="/" aria-label="Stackwise home">
          <StackwiseBrand />
        </Link>
        <nav aria-label="Main navigation">
          <a href="#workflow">How it works</a>
          <a href="#platform">The platform</a>
          <a href="#principles">Our approach</a>
        </nav>
        <Link className="sw-btn sw-btn-dark" href="/dashboard">
          Open workspace <ArrowUpRight size={15} />
        </Link>
      </header>
      <main id="main">
        <section className="sw-hero">
          <div className="sw-hero-copy">
            <div className="sw-eyebrow">
              <span className="sw-live-dot" /> YOUR AGENCY’S MAINTENANCE DESK
            </div>
            <h1>
              Know which
              <br />
              repository needs
              <br />
              <em>you next.</em>
            </h1>
            <p>
              Less time chasing issues. More time shipping good work. Review
              pull requests, keep client code healthy, and explain what matters
              — all in one place.
            </p>
            <div className="sw-hero-actions">
              <Link className="sw-btn sw-btn-green" href="/dashboard">
                Open your workspace <ArrowRight size={17} />
              </Link>
              <Link className="sw-text-link" href="/dashboard?demo=1">
                Explore the demo <ArrowUpRight size={16} />
              </Link>
            </div>
            <div className="sw-hero-note">
              <ShieldCheck size={15} /> Evidence with every finding. A human
              behind every change.
            </div>
          </div>
          <div
            className="sw-hero-art"
            aria-label="Illustrative Stackwise review preview"
          >
            <div className="sw-art-orbit sw-orbit-1" />
            <div className="sw-art-orbit sw-orbit-2" />
            <div className="sw-preview-card">
              <div className="sw-preview-top">
                <StackwiseBrand small />
                <span className="sw-badge sw-badge-green">Review ready</span>
              </div>
              <div className="sw-preview-label">CLIENT ALPHA / API-SERVICE</div>
              <h2>
                A small change.
                <br />
                The full picture.
              </h2>
              <div className="sw-preview-code">
                <span className="sw-code-file">
                  <Code2 size={13} /> auth/routes.py
                </span>
                <code>
                  <span>07</span> @router.get(&quot;/account&quot;)
                  <br />
                  <span>08</span> def get_account(user_id: str):
                  <br />
                  <span>09</span> return fetch_account(user_id)
                </code>
              </div>
              <div className="sw-preview-finding">
                <div>
                  <span className="sw-badge sw-badge-high">HIGH</span>
                  <small>Potential issue</small>
                </div>
                <strong>Who owns this account?</strong>
                <p>Check caller ownership before returning account data.</p>
                <div className="sw-mini-evidence">
                  <Check size={13} /> Source location checked{" "}
                  <span>Lines 7–9</span>
                </div>
              </div>
              <Link href="/dashboard?demo=1" className="sw-preview-action">
                Inspect the evidence <ArrowRight size={15} />
              </Link>
              <small className="sw-preview-caption">
                Illustrative sample · no client data
              </small>
            </div>
            <div className="sw-floating-note">
              <span className="sw-float-icon">
                <GitPullRequest size={18} />
              </span>
              <div>
                <strong>Context, connected.</strong>
                <span>Changed code + callers + tests</span>
              </div>
            </div>
            <span className="sw-art-label">
              DESIGNED FOR THE PEOPLE BEHIND THE CODE
            </span>
          </div>
        </section>
        <div className="sw-value-strip">
          <span>
            One clear view.
            <br />
            <strong>Across every client.</strong>
          </span>
          <span>
            <Layers3 size={19} /> Client workspaces
          </span>
          <span>
            <GitPullRequest size={19} /> Context-aware reviews
          </span>
          <span>
            <ShieldCheck size={19} /> Dependency visibility
          </span>
          <span>
            <FileCheck2 size={19} /> Client-ready reports
          </span>
        </div>
        <section id="workflow" className="sw-section">
          <div className="sw-section-intro">
            <div>
              <span className="sw-eyebrow">
                FROM PULL REQUEST TO PEACE OF MIND
              </span>
              <h2>
                Understand first.
                <br />
                <em>Change with confidence.</em>
              </h2>
            </div>
            <p>
              Good maintenance starts with the right context. Stackwise brings
              the code, the evidence, and the next step together.
            </p>
          </div>
          <div className="sw-steps">
            {[
              {
                icon: GitPullRequest,
                n: "01",
                title: "Review the change",
                body: "Read a pull request alongside relevant callers, tests, contracts and earlier reviews.",
              },
              {
                icon: ShieldCheck,
                n: "02",
                title: "Verify the evidence",
                body: "Inspect the exact file, line and commit behind a potential bug or security concern.",
              },
              {
                icon: FileCheck2,
                n: "03",
                title: "Make the call",
                body: "Preview a suggested patch, record your decision and share a clear maintenance report.",
              },
            ].map((s) => (
              <article key={s.n}>
                <div className="sw-step-top">
                  <s.icon size={24} strokeWidth={1.5} />
                  <span>{s.n}</span>
                </div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </article>
            ))}
          </div>
        </section>
        <section id="platform" className="sw-platform-section">
          <div className="sw-platform-copy">
            <span className="sw-eyebrow">
              THE BIG PICTURE, WITHOUT THE NOISE
            </span>
            <h2>
              Your clients are different.
              <br />
              <em>The standard stays high.</em>
            </h2>
            <p>
              Move from a portfolio overview to a single changed line. Keep
              client workspaces separate, prioritize open risks, and turn
              technical findings into practical next steps.
            </p>
            <Link className="sw-text-link" href="/dashboard?demo=1">
              Take a look inside <ArrowRight size={16} />
            </Link>
          </div>
          <div className="sw-workspace-preview">
            <div className="sw-panel-heading">
              <h3>Workspace health</h3>
              <span className="sw-badge">Sample portfolio</span>
            </div>
            {[
              {
                n: "Client Alpha",
                c: "A",
                p: "API service",
                s: "Needs attention",
                color: "high",
              },
              {
                n: "Client Beta",
                c: "B",
                p: "Web application",
                s: "Not indexed",
                color: "neutral",
              },
              {
                n: "Internal tools",
                c: "I",
                p: "Release CLI",
                s: "Not indexed",
                color: "neutral",
              },
            ].map((w) => (
              <div className="sw-workspace-preview-row" key={w.n}>
                <span className="sw-avatar">{w.c}</span>
                <div>
                  <strong>{w.n}</strong>
                  <small>{w.p}</small>
                </div>
                <span className={`sw-badge sw-badge-${w.color}`}>{w.s}</span>
                <ChevronRight size={16} />
              </div>
            ))}
            <p>
              <LockKeyhole size={13} /> Workspace access is checked before
              retrieving code.
            </p>
          </div>
        </section>
        <section id="principles" className="sw-section sw-principles">
          <span className="sw-eyebrow">BUILT ON A SIMPLE PRINCIPLE</span>
          <h2>
            AI brings the context.
            <br />
            <em>You bring the judgment.</em>
          </h2>
          <p>
            Stackwise suggests and explains. Your team approves. No autonomous
            merges, no silent deployments, and no test results that never
            happened.
          </p>
          <div>
            <span>
              <Check size={16} /> Inspectable code evidence
            </span>
            <span>
              <Check size={16} /> Downloadable patch previews
            </span>
            <span>
              <Check size={16} /> Clear coverage limits
            </span>
          </div>
          <Link className="sw-btn sw-btn-green" href="/dashboard?demo=1">
            Explore a sample review <ArrowRight size={16} />
          </Link>
        </section>
      </main>
      <footer className="sw-site-footer">
        <Link href="/">
          <StackwiseBrand />
        </Link>
        <span>Know which repository needs you next.</span>
        <a
          href="https://github.com/qaiser931/fintech-codegraph-rag"
          target="_blank"
          rel="noreferrer"
        >
          View source <ArrowUpRight size={14} />
        </a>
        <a href="#main" aria-label="Back to top">
          <ArrowDown className="sw-up" size={17} />
        </a>
      </footer>
    </div>
  )
}
