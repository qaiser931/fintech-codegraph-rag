import { Network } from "lucide-react"

export function CodeGraphBrand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="cg-brand">
      <span className="cg-brand-mark">
        <Network size={21} strokeWidth={1.7} aria-hidden="true" />
      </span>
      <span>
        CodeGraph
        {!compact && <span className="cg-brand-suffix"> / fintech</span>}
      </span>
    </span>
  )
}

export function GraphIllustration({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`cg-graph-art ${compact ? "is-compact" : ""}`}>
      <svg
        viewBox="0 0 540 240"
        preserveAspectRatio="none"
        aria-hidden="true"
        className="cg-graph-edges"
      >
        <defs>
          <linearGradient id={compact ? "graph-small" : "graph-large"}>
            <stop stopColor="#c4b5fd" />
            <stop offset="1" stopColor="#6b5ce7" />
          </linearGradient>
        </defs>
        <path
          d="M105 126 C195 126 164 57 264 57 M105 126 C180 126 182 177 280 177 M264 57 C357 57 359 110 446 110 M280 177 C365 177 344 110 446 110"
          fill="none"
          stroke={compact ? "url(#graph-small)" : "url(#graph-large)"}
          strokeWidth="1.5"
        />
      </svg>
      <div className="cg-graph-node node-entry">
        <span className="cg-node-dot" />
        <span>
          <small>ENTRY POINT</small>
          <strong>PaymentService</strong>
        </span>
      </div>
      <div className="cg-graph-node node-switch">
        <span className="cg-node-dot mint" />
        <span>
          <small>INTEGRATION</small>
          <strong>1LINK switch</strong>
        </span>
      </div>
      <div className="cg-graph-node node-repo">
        <span className="cg-node-dot amber" />
        <span>
          <small>DATABASE</small>
          <strong>Payment repository</strong>
        </span>
      </div>
      <div className="cg-graph-node node-output">
        <span className="cg-node-dot" />
        <span>
          <small>RESULT</small>
          <strong>Source evidence</strong>
        </span>
      </div>
    </div>
  )
}
