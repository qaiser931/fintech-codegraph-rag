import Link from "next/link"
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Building2,
  Check,
  ChevronRight,
  Code2,
  FileCheck2,
  GitPullRequest,
  Layers3,
  LockKeyhole,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react"
import { StackwiseBrand } from "@/components/stackwise-brand"

function GitHubIcon({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  )
}

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
          <a href="#audience">Who it&apos;s for</a>
          <a href="#features">Features</a>
          <a href="#workflow">How it works</a>
          <a href="#principles">Our approach</a>
        </nav>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <a
            className="sw-btn sw-btn-github sw-btn-small"
            href="/api/auth/github"
            aria-label="Continue with GitHub"
          >
            <GitHubIcon size={15} />
            <span>Sign in with GitHub</span>
          </a>
          <Link className="sw-btn sw-btn-dark sw-btn-small" href="/dashboard">
            Open workspace <ArrowUpRight size={14} />
          </Link>
        </div>
      </header>
      <main id="main">
        <section className="sw-hero">
          <div className="sw-hero-copy">
            <div className="sw-eyebrow">
              <span className="sw-live-dot" /> CODE QUALITY &amp; REPOSITORY
              INTELLIGENCE FOR TEAMS
            </div>
            <h1>
              Know which
              <br />
              repository needs
              <br />
              <em>you next.</em>
            </h1>
            <p>
              Stackwise helps software agencies, fast-growing startups, and
              engineering teams understand code quality, review pull requests
              with real context, analyze repositories, and track maintenance
              progress — all backed by inspectable evidence.
            </p>
            <div className="sw-hero-actions">
              <a
                className="sw-btn sw-btn-github"
                href="/api/auth/github"
                aria-label="Continue with GitHub"
              >
                <GitHubIcon size={17} />
                <span>Continue with GitHub</span>
              </a>
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
            <strong>Across every client &amp; codebase.</strong>
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

        {/* TARGET AUDIENCE & PROBLEMS SOLVED */}
        <section id="audience" className="sw-section">
          <div className="sw-section-intro">
            <div>
              <span className="sw-eyebrow">
                BUILT FOR TEAMS RESPONSIBLE FOR CODE HEALTH
              </span>
              <h2>
                Who Stackwise is
                <br />
                <em>designed for.</em>
              </h2>
            </div>
            <p>
              Different teams face distinct maintenance challenges. Stackwise
              adapts to your workflow, whether managing dozens of client
              deliverables or scaling your core startup product.
            </p>
          </div>
          <div className="sw-audience-grid">
            <article className="sw-audience-card">
              <div className="sw-audience-top">
                <Building2 size={24} strokeWidth={1.7} />
                <h3>Software agencies</h3>
              </div>
              <p>
                Manage ongoing maintenance contracts, client codebases, and
                retainer deliverables across multiple client organizations with
                strict multi-tenant isolation.
              </p>
              <div className="sw-audience-problem">
                <strong>Challenge:</strong> Context switching across client
                repos and explaining technical maintenance value to
                non-technical clients.
              </div>
              <div className="sw-audience-solution">
                <strong>Stackwise solution:</strong> Workspace-scoped access
                keys, encrypted repository tokens, and one-click weekly Markdown
                reports.
              </div>
            </article>

            <article className="sw-audience-card">
              <div className="sw-audience-top">
                <Sparkles size={24} strokeWidth={1.7} />
                <h3>Small software startups</h3>
              </div>
              <p>
                Ship features rapidly without letting tech debt, insecure
                patterns, or broken dependencies silently degrade product
                stability and reliability.
              </p>
              <div className="sw-audience-problem">
                <strong>Challenge:</strong> Limited engineering bandwidth to
                conduct thorough security and architecture reviews on every pull
                request.
              </div>
              <div className="sw-audience-solution">
                <strong>Stackwise solution:</strong> Context-aware PR reviews,
                grounded code Q&amp;A, and ready-to-test patch diff previews.
              </div>
            </article>

            <article className="sw-audience-card">
              <div className="sw-audience-top">
                <GitPullRequest size={24} strokeWidth={1.7} />
                <h3>Software development teams</h3>
              </div>
              <p>
                Empower software engineers to review changes in context. See
                exact callers, contract boundaries, dependency alerts, and test
                impact side-by-side.
              </p>
              <div className="sw-audience-problem">
                <strong>Challenge:</strong> Reviewing PR diffs in isolation
                without understanding upstream caller contracts or unintended
                side effects.
              </div>
              <div className="sw-audience-solution">
                <strong>Stackwise solution:</strong> Deep code-graph context,
                heuristic line-by-line evidence, and human-verified review
                decisions.
              </div>
            </article>

            <article className="sw-audience-card">
              <div className="sw-audience-top">
                <Users size={24} strokeWidth={1.7} />
                <h3>Engineering &amp; product managers</h3>
              </div>
              <p>
                Gain visibility into repository health, review status, open risks,
                and team progress across all repositories without ambiguous
                metrics.
              </p>
              <div className="sw-audience-problem">
                <strong>Challenge:</strong> Lacking a consolidated, truthful
                view of pull request backlogs and repository maintenance state.
              </div>
              <div className="sw-audience-solution">
                <strong>Stackwise solution:</strong> Unified audit trails,
                explicit review decisions (Needs review, Approved, Changes
                requested), and honest coverage boundaries.
              </div>
            </article>
          </div>
        </section>

        {/* MAIN FEATURES (ONLY THOSE THAT WORK) */}
        <section id="features" className="sw-section">
          <div className="sw-section-intro">
            <div>
              <span className="sw-eyebrow">
                CORE CAPABILITIES — REAL, VERIFIED &amp; WORKING
              </span>
              <h2>
                Features built for
                <br />
                <em>practical code maintenance.</em>
              </h2>
            </div>
            <p>
              Every capability below is fully functional in the Stackwise
              codebase. We prioritize transparency: no fabricated features, no
              autonomous merges.
            </p>
          </div>
          <div className="sw-features-grid">
            <div className="sw-feature-card">
              <div className="sw-feature-icon">
                <Sparkles size={20} />
              </div>
              <h3>AI code review &amp; reports</h3>
              <p>
                Automated pull request analysis highlighting security risks and
                logic flaws with verifiable line-by-line evidence, downloadable
                patch previews, and stakeholder reports.
              </p>
              <span className="sw-badge sw-badge-green sw-feature-badge">
                Active feature
              </span>
            </div>

            <div className="sw-feature-card">
              <div className="sw-feature-icon">
                <Layers3 size={20} />
              </div>
              <h3>Workspace management</h3>
              <p>
                Multi-tenant organization partitioning. Manage isolated client
                workspaces with custom access keys, fine-grained permissions
                (owner, reviewer, viewer), and encrypted tokens.
              </p>
              <span className="sw-badge sw-badge-green sw-feature-badge">
                Active feature
              </span>
            </div>

            <div className="sw-feature-card">
              <div className="sw-feature-icon">
                <Code2 size={20} />
              </div>
              <h3>Multiple repository analysis</h3>
              <p>
                Connect and index repositories up to 350 files and 3 MB of source
                code in-memory. Extract AST symbols, map dependencies, and
                inspect package security advisories.
              </p>
              <span className="sw-badge sw-badge-green sw-feature-badge">
                Active feature
              </span>
            </div>

            <div className="sw-feature-card">
              <div className="sw-feature-icon">
                <ShieldCheck size={20} />
              </div>
              <h3>Repository issues &amp; insights</h3>
              <p>
                Prioritize findings by severity (High, Medium, Low, Info). Manage
                issue status (Open, Dismissed, Resolved) and capture engineer
                feedback (Useful, False positive, Uncertain).
              </p>
              <span className="sw-badge sw-badge-green sw-feature-badge">
                Active feature
              </span>
            </div>

            <div className="sw-feature-card">
              <div className="sw-feature-icon">
                <GitPullRequest size={20} />
              </div>
              <h3>Pull request &amp; merge history</h3>
              <p>
                Track pull requests across active branches, observe CI run
                outcomes, and record explicit review decisions (Needs review,
                Approved, Changes requested) with complete audit history.
              </p>
              <span className="sw-badge sw-badge-green sw-feature-badge">
                Active feature
              </span>
            </div>

            <div className="sw-feature-card">
              <div className="sw-feature-icon">
                <Search size={20} />
              </div>
              <h3>Ask Your Code</h3>
              <p>
                Query your indexed codebase using natural language. Get grounded
                answers and explanations citing exact file locations, function
                definitions, and line ranges.
              </p>
              <span className="sw-badge sw-badge-green sw-feature-badge">
                Active feature
              </span>
            </div>
          </div>
        </section>

        {/* HOW IT WORKS */}
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
                title: "Connect & Index",
                body: "Sign in with GitHub or add repository tokens. Stackwise securely inspects code in-memory without cloning or executing untrusted code.",
              },
              {
                icon: ShieldCheck,
                n: "02",
                title: "Review With Context",
                body: "Inspect pull requests alongside callers, tests, and dependency advisories with exact line citations and suggested patch previews.",
              },
              {
                icon: FileCheck2,
                n: "03",
                title: "Decide & Report",
                body: "Record human review decisions, track resolved items, and download structured Markdown maintenance reports for clients and teams.",
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

        {/* PLATFORM PREVIEW */}
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
            <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
              <a
                className="sw-btn sw-btn-github sw-btn-small"
                href="/api/auth/github"
              >
                <GitHubIcon size={14} /> Continue with GitHub
              </a>
              <Link className="sw-text-link" href="/dashboard?demo=1">
                Take a look inside <ArrowRight size={16} />
              </Link>
            </div>
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

        {/* PRINCIPLES */}
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
          <div style={{ display: "flex", gap: "14px", justifyContent: "center" }}>
            <a className="sw-btn sw-btn-github" href="/api/auth/github">
              <GitHubIcon size={16} /> Sign up with GitHub
            </a>
            <Link className="sw-btn sw-btn-green" href="/dashboard?demo=1">
              Explore a sample review <ArrowRight size={16} />
            </Link>
          </div>
        </section>

        {/* CTA BANNER */}
        <section className="sw-cta-banner">
          <div className="sw-eyebrow">READY TO ELEVATE YOUR CODE MAINTENANCE?</div>
          <h2>
            Start reviewing code with
            <br />
            clarity and evidence today.
          </h2>
          <p>
            Connect your repositories in seconds with GitHub OAuth. Keep your
            client projects healthy, review pull requests with real context, and
            ship with confidence.
          </p>
          <div className="sw-cta-actions">
            <a
              className="sw-btn sw-btn-dark sw-btn-github"
              href="/api/auth/github"
              style={{ padding: "14px 24px", fontSize: "13px" }}
            >
              <GitHubIcon size={18} /> Continue with GitHub
            </a>
            <Link
              className="sw-btn sw-btn-green"
              href="/dashboard"
              style={{ padding: "14px 24px", fontSize: "13px" }}
            >
              Launch live workspace <ArrowRight size={16} />
            </Link>
            <Link
              className="sw-btn sw-btn-outline"
              href="/dashboard?demo=1"
              style={{ padding: "14px 24px", fontSize: "13px" }}
            >
              Try interactive demo <ArrowUpRight size={16} />
            </Link>
          </div>
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
