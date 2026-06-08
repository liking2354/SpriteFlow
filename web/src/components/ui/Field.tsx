import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

interface FieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Field({ label, hint, children, className = "" }: FieldProps) {
  return (
    <div className={`mb-3 ${className}`}>
      {label && (
        <label className="block text-[11px] text-txt-2 mb-1.5">{label}</label>
      )}
      {children}
      {hint && (
        <div className="mt-1 text-[10.5px] text-txt-3 font-mono">{hint}</div>
      )}
    </div>
  );
}

export function TextInput({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full px-3 h-9 bg-bg-0 border border-line rounded-s text-[12px] text-txt-0 font-mono focus:border-[var(--acc)] focus:shadow-[0_0_0_3px_var(--acc-soft)] transition-all placeholder:text-txt-3 ${className}`}
    />
  );
}

export function TextArea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full px-3 py-2 bg-bg-0 border border-line rounded-s text-[12px] text-txt-1 leading-relaxed focus:border-[var(--acc)] focus:shadow-[0_0_0_3px_var(--acc-soft)] transition-all placeholder:text-txt-3 resize-y ${className}`}
    />
  );
}

export function Select({ className = "", children, ...props }: InputHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <div className="relative">
      <select
        {...(props as object)}
        className={`w-full px-3 pr-8 h-9 bg-bg-0 border border-line rounded-s text-[12px] text-txt-0 font-mono focus:border-[var(--acc)] focus:shadow-[0_0_0_3px_var(--acc-soft)] transition-all appearance-none cursor-pointer ${className}`}
      >
        {children}
      </select>
      <span
        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2"
        style={{ color: "var(--txt-3)" }}
      >
        <svg width="10" height="10" viewBox="0 0 10 10">
          <path d="M3 3.5L5 5.5L7 3.5" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />
        </svg>
      </span>
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: ReactNode;
}) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer select-none">
      <span
        onClick={() => onChange(!checked)}
        className={`relative w-9 h-5 rounded-full transition-colors ${checked ? "bg-[var(--acc)]" : "bg-bg-3 border border-line"}`}
      >
        <span
          className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${checked ? "left-[18px]" : "left-0.5"}`}
        />
      </span>
      {label && <span className="text-[12px] text-txt-1">{label}</span>}
    </label>
  );
}
