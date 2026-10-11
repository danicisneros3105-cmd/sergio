import type { ReactNode } from 'react';

// The title row of every page, as on the e-paper home: the title centred
// (set like the B&O wordmark), an optional control on each side.
export function PaperHead({ title, left, right }: { title: string; left?: ReactNode; right?: ReactNode }) {
  return (
    <header className="paper-head">
      <div className="flex items-center gap-1 min-w-0">{left}</div>
      <h1 className="paper-title text-center">{title}</h1>
      <div>{right}</div>
    </header>
  );
}

// The e-paper page frame: the title row, an optional line under it, and the
// content in a calm column.
export function PaperPage({
  title,
  subtitle,
  children,
  wide = false,
  left,
  right,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  wide?: boolean;
  left?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="paper-page">
      <div className="paper-page-inner" style={wide ? undefined : { maxWidth: 760 }}>
        <PaperHead title={title} left={left} right={right} />
        {subtitle && (
          <p className="-mt-6 mb-8 text-center text-[13.5px]" style={{ color: 'var(--color-text-secondary)' }}>
            {subtitle}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}

// A section heading in letter-spaced capitals with a hairline, like
// «Marked» / «All · Notebooks · Documents» on the e-paper home.
export function PaperSection({ label, children, aside }: { label: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="mb-10">
      <div className="flex items-end justify-between pb-2 mb-4" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <h2 className="paper-label">{label}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
