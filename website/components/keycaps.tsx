/** Key caps for a shortcut, e.g. ["Alt", "Alt"]. Read aloud as one phrase. */
export function Keycaps({
  keys,
  label,
  className = "",
}: {
  keys: readonly string[];
  label: string;
  className?: string;
}) {
  return (
    <span role="img" aria-label={label} className={`inline-flex items-center gap-[0.4em] ${className}`}>
      {keys.map((key, i) => (
        <kbd key={i} aria-hidden="true" className="keycap">
          {key}
        </kbd>
      ))}
    </span>
  );
}
