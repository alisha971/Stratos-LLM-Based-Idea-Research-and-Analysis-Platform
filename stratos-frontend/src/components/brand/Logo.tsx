type LogoMarkProps = {
  className?: string;
};

/**
 * Stratos mark: an isometric stack of three "strata" layers.
 * Inherits text color for the lower layers; top layer is always moss.
 */
export function LogoMark({ className = "h-6 w-6" }: LogoMarkProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      aria-hidden="true"
      fill="none"
    >
      <path
        d="M16 15.5 28.5 22.5 16 29.5 3.5 22.5Z"
        fill="var(--paper)"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path
        d="M16 9.5 28.5 16.5 16 23.5 3.5 16.5Z"
        fill="var(--paper)"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path
        d="M16 3.5 28.5 10.5 16 17.5 3.5 10.5Z"
        fill="#245c3d"
        stroke="#1a4730"
        strokeWidth="1"
        strokeLinejoin="round"
      />
    </svg>
  );
}

type LogoProps = {
  markClassName?: string;
  textClassName?: string;
};

/** Mark + serif wordmark, baseline-aligned for headers. */
export function Logo({
  markClassName = "h-6 w-6",
  textClassName = "font-serif text-2xl font-medium tracking-tight",
}: LogoProps) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark className={markClassName} />
      <span className={textClassName}>Stratos</span>
    </span>
  );
}
