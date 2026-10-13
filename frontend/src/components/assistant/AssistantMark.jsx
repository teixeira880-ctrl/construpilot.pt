/** Shared vector identity: a construction helmet inside a conversation bubble. */
export function AssistantMark({ size = 40, className = "", ...props }) {
  return <svg width={size} height={size} viewBox="0 0 64 64" fill="none" className={className} aria-hidden="true" focusable="false" {...props}>
    <path d="M19 4h26c8.3 0 15 6.7 15 15v24c0 8.3-6.7 15-15 15H22L4 62V19C4 10.7 10.7 4 19 4Z" fill="#244D3D" />
    <path d="M19 36v-3c0-7.2 5.8-13 13-13s13 5.8 13 13v3" stroke="#FBF8F4" strokeWidth="3.5" strokeLinecap="round" />
    <path d="M29 29V18a3 3 0 0 1 6 0v11" fill="#CF9165" />
    <path d="M16 37h32v3a3 3 0 0 1-3 3H19a3 3 0 0 1-3-3v-3Z" fill="#FBF8F4" />
  </svg>;
}
