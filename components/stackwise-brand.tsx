export function StackwiseBrand({ small = false }: { small?: boolean }) {
  return (
    <span className={`sw-brand ${small ? "sw-brand-small" : ""}`}>
      <span className="sw-mark" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span>
        stackwise<span className="sw-brand-dot">.</span>
      </span>
    </span>
  )
}
