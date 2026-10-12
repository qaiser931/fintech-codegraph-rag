import Link from "next/link"
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  Code2,
  GitBranch,
  GitFork,
  Layers3,
  LockKeyhole,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { CodeGraphBrand, GraphIllustration } from "@/components/codegraph-brand"

const repository = "https://github.com/qaiser931/fintech-codegraph-rag"

export default function HomePage() {
  return (
    <div className="cg-site">
      <a className="cg-skip" href="#main-content">
        Skip to content
      </a>
      <header className="cg-site-header">
        <Link href="/" aria-label="CodeGraph home">
          <CodeGraphBrand />
        </Link>
        <nav aria-label="Main navigation" className="cg-site-nav">
          <a href="#capabilities">Capabilities</a>
          <a href="#workflow">How it works</a>
          <a href="#project">The project</a>
        </nav>
        <Link className="cg-button cg-button-small" href="/dashboard">
          Open dashboard <ArrowUpRight size={15} />
        </Link>
      </header>
      <main id="main-content">
        <section className="cg-hero cg-container">
          <div className="cg-hero-copy">
            <span className="cg-eyebrow">
              <span className="cg-pip" /> CODE INTELLIGENCE, CONNECTED
            </span>
            <h1>
              Follow the code.
              <br />
              Find the <span>evidence.</span>
            </h1>
            <p>
              Turn a fintech codebase into a conversation you can verify.
              Explore symbols, trace payment flows, and inspect the source
              behind every answer.
            </p>
            <div className="cg-hero-actions">
              <Link className="cg-button" href="/dashboard">
                Open dashboard <ArrowRight size={18} />
              </Link>
              <a
                className="cg-button cg-button-quiet"
                href={repository}
                target="_blank"
                rel="noopener noreferrer"
              >
                <GitFork size={18} /> View source
              </a>
            </div>
            <div className="cg-hero-footnote">
              <ShieldCheck size={15} /> Role-scoped evidence <span /> Synthetic
              fintech demo
            </div>
          </div>
          <div className="cg-hero-visual">
            <div className="cg-preview-window">
              <div className="cg-window-bar">
                <div className="cg-window-dots">
                  <i />
                  <i />
                  <i />
                </div>
                <span>codegraph / investigation</span>
                <span className="cg-window-tag">Illustrative preview</span>
              </div>
              <div className="cg-preview-question">
                <Search size={17} />
                <span>How does this payment flow connect?</span>
                <kbd>↵</kbd>
              </div>
              <div className="cg-preview-graph-label">
                <GitBranch size={13} /> Connected source context{" "}
                <span>PYTHON</span>
              </div>
              <GraphIllustration />
              <div className="cg-preview-code">
                <div>
                  <Code2 size={14} /> payment_service.py{" "}
                  <span>Sample excerpt</span>
                </div>
                <pre>
                  <code>
                    <span className="cg-code-purple">with</span>{" "}
                    get_db_session() <span className="cg-code-purple">as</span>{" "}
                    session:{"\n"} account =
                    payment_repository.acquire_account_lock(...){"\n"}{" "}
                    switch_res = onelink_client.verify_switch_transaction(...)
                  </code>
                </pre>
              </div>
            </div>
            <div className="cg-evidence-float">
              <span className="cg-check-icon">
                <Check size={15} />
              </span>
              <div>
                <strong>Inspect the original source</strong>
                <p>A clear path from answer to evidence.</p>
              </div>
              <ArrowUpRight size={17} />
            </div>
            <span className="cg-visual-note">
              Illustration of the workflow · Open the dashboard for live results
            </span>
          </div>
        </section>
        <div className="cg-stack-strip cg-container">
          <span>BUILT TO CONNECT</span>
          <div>Next.js</div>
          <div>FastAPI</div>
          <div>Chroma</div>
          <div>NetworkX</div>
          <div>Groq</div>
          <span className="cg-stack-strip-end">
            <Layers3 size={16} /> One investigation workspace
          </span>
        </div>
        <section id="capabilities" className="cg-capabilities cg-container">
          <div className="cg-section-heading">
            <div>
              <span className="cg-eyebrow">THE WHOLE PICTURE</span>
              <h2>
                Less searching.
                <br />
                More understanding.
              </h2>
            </div>
            <p>
              Move from a question to the relevant code, then follow the
              connections that give it context.
            </p>
          </div>
          <div className="cg-feature-grid">
            <article className="cg-feature cg-feature-search">
              <span className="cg-feature-icon">
                <Search size={22} />
              </span>
              <h3>Search beyond keywords.</h3>
              <p>
                Dense and BM25 search work together to find symbols and code
                context. A cross-encoder reranks the candidates.
              </p>
              <div className="cg-search-mini">
                <span>
                  <Search size={14} /> 1LINK peak traffic latency
                </span>
                <div>
                  <span className="cg-mini-file">PY</span>
                  <span>
                    verify_switch_transaction
                    <small>integrations/onelink_client.py</small>
                  </span>
                  <ArrowUpRight size={15} />
                </div>
              </div>
              <span className="cg-feature-caption">
                Example symbol match from the sample code
              </span>
            </article>
            <article className="cg-feature">
              <span className="cg-feature-icon mint">
                <GitBranch size={22} />
              </span>
              <h3>Follow the execution path.</h3>
              <p>
                Explore the graph around retrieved symbols to understand
                callers, dependencies and the available call sequence.
              </p>
              <div className="cg-path-mini">
                <span>Callback</span>
                <ChevronRight size={15} />
                <span>Service</span>
                <ChevronRight size={15} />
                <span>Switch</span>
              </div>
              <span className="cg-feature-caption">
                Illustrative payment flow
              </span>
            </article>
            <article className="cg-feature">
              <span className="cg-feature-icon peach">
                <BookOpen size={22} />
              </span>
              <h3>Keep the source in view.</h3>
              <p>
                Open a reference to inspect the file and highlighted lines.
                Judge the answer alongside its actual source evidence.
              </p>
              <div className="cg-source-mini">
                <span>onelink_client.py</span>
                <div>
                  <i>36</i> LATENCY CHARACTERISTIC:
                </div>
                <div className="highlight">
                  <i>38</i> latency fluctuates between 2.0s and 6.0s
                </div>
              </div>
              <span className="cg-feature-caption">
                Documented sample behavior, not production measurements
              </span>
            </article>
            <article className="cg-feature cg-feature-roles">
              <span className="cg-feature-icon">
                <LockKeyhole size={22} />
              </span>
              <h3>The right context for each role.</h3>
              <p>
                Switch between the three demo roles. Retrieval and source access
                respect the backend&apos;s configured permissions.
              </p>
              <div className="cg-role-chips">
                <span>
                  <span className="cg-role-initial">J</span> Junior Dev
                </span>
                <span>
                  <span className="cg-role-initial">S</span> Senior Dev
                </span>
                <span>
                  <span className="cg-role-initial">L</span> Security Lead
                </span>
              </div>
            </article>
          </div>
        </section>
        <section id="workflow" className="cg-workflow-section">
          <div className="cg-container">
            <div className="cg-section-heading">
              <div>
                <span className="cg-eyebrow">FROM QUESTION TO CONTEXT</span>
                <h2>
                  One workspace.
                  <br />
                  Three useful steps.
                </h2>
              </div>
              <Link className="cg-text-link" href="/dashboard">
                Try the workflow <ArrowUpRight size={17} />
              </Link>
            </div>
            <div className="cg-steps">
              <article>
                <span className="cg-step-number">
                  01 <Search size={23} />
                </span>
                <h3>Ask a specific question</h3>
                <p>
                  Choose a role, describe the behavior you want to understand,
                  and add a stack trace if you have one.
                </p>
              </article>
              <article>
                <span className="cg-step-number">
                  02 <GitBranch size={23} />
                </span>
                <h3>Explore the code</h3>
                <p>
                  Inspect matching symbols and execution paths before requesting
                  a generated answer.
                </p>
              </article>
              <article>
                <span className="cg-step-number">
                  03 <Sparkles size={23} />
                </span>
                <h3>Verify the answer</h3>
                <p>
                  Read the evidence status, open citations and compare the
                  response with the referenced lines.
                </p>
              </article>
            </div>
          </div>
        </section>
        <section id="project" className="cg-project cg-container">
          <div className="cg-project-copy">
            <span className="cg-eyebrow">
              PROJECT 10 / FINTECH CODEGRAPH RAG
            </span>
            <h2>
              A practical lens on
              <br />
              payment integrations.
            </h2>
            <p>
              A code investigation demo built around synthetic JazzCash, 1LINK
              and EasyPaisa examples. Python symbols become a searchable
              dependency graph; retrieved context supports technical answers
              through Groq.
            </p>
            <a
              className="cg-text-link"
              href={`${repository}/blob/main/docs/PROJECT10_REQUIREMENTS.md`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Explore the project documentation <ArrowUpRight size={17} />
            </a>
          </div>
          <div className="cg-project-details">
            <details open>
              <summary>
                What does this demonstration establish?
                <span>
                  <ArrowDown size={16} />
                </span>
              </summary>
              <p>
                You can explore source references, inspect available execution
                paths and request answers grounded in retrieved code. Individual
                successful requests are diagnostics, not proof of complete
                benchmark accuracy.
              </p>
            </details>
            <details>
              <summary>
                Is this a real payment system?
                <span>
                  <ArrowDown size={16} />
                </span>
              </summary>
              <p>
                No. The sample integrations and credentials are demonstration
                fixtures. They do not establish live provider performance or
                production approval.
              </p>
            </details>
            <details>
              <summary>
                How should I read an evidence status?
                <span>
                  <ArrowDown size={16} />
                </span>
              </summary>
              <p>
                The dashboard distinguishes supported, partially supported,
                conflicting and insufficient evidence. Inspect the source when
                evaluating a claim; a status label alone is not proof of
                correctness.
              </p>
            </details>
          </div>
        </section>
        <section className="cg-cta cg-container">
          <div>
            <span className="cg-eyebrow">START WITH A QUESTION</span>
            <h2>
              Your next insight
              <br />
              is in the code.
            </h2>
            <p>Open the investigation workspace and follow the evidence.</p>
          </div>
          <Link className="cg-button cg-button-light" href="/dashboard">
            Open dashboard <ArrowUpRight size={20} />
          </Link>
          <div className="cg-cta-orbit" aria-hidden="true" />
        </section>
      </main>
      <footer className="cg-site-footer cg-container">
        <Link href="/" aria-label="CodeGraph home">
          <CodeGraphBrand compact />
        </Link>
        <span>Project 10 · Synthetic fintech demonstration</span>
        <a href={repository} target="_blank" rel="noopener noreferrer">
          GitHub <ArrowUpRight size={14} />
        </a>
      </footer>
    </div>
  )
}
