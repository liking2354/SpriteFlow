interface Props {
  color?: "green" | "red" | "amber" | "acc" | "violet";
  size?: number;
  className?: string;
}

const COLORS = {
  green: "var(--green)",
  red: "var(--red)",
  amber: "var(--amber)",
  acc: "var(--acc)",
  violet: "var(--violet)",
};

export function Led({ color = "green", size = 7, className = "" }: Props) {
  const c = COLORS[color];
  return (
    <span
      className={`inline-block rounded-full ${className}`}
      style={{
        width: size,
        height: size,
        background: c,
        boxShadow: `0 0 ${size + 2}px ${c}`,
      }}
    />
  );
}
