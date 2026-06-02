interface Item<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  items: Item<T>[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}

export function Segment<T extends string>({
  items,
  value,
  onChange,
  className = "",
}: Props<T>) {
  return (
    <div
      className={`flex bg-bg-0 border border-line rounded-s p-[3px] gap-[3px] ${className}`}
    >
      {items.map((it) => (
        <button
          key={it.value}
          type="button"
          onClick={() => onChange(it.value)}
          className={`flex-1 h-7 px-3 text-[11px] rounded-[6px] font-medium transition-colors ${
            value === it.value
              ? "text-[var(--acc)]"
              : "text-txt-2 hover:text-txt-0"
          }`}
          style={
            value === it.value
              ? { background: "var(--acc-soft)" }
              : undefined
          }
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
