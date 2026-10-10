import type { ReactNode } from 'react';

// The e-paper page frame: a centred book-serif title, an optional line under
// it, and the content in a calm column (Montblanc Digital Paper's home).
export function PaperPage({
  title,
  subtitle,
  children,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="flex-1 overflow-y-auto px-4 sm:px-8 pt-10 pb-12">
      <div className={`${wide ? 'max-w-5xl' : 'max-w-3xl'} mx-auto`}>
        <header className="text-center mb-8">
          <h1 className="paper-title">{title}</h1>
          {subtitle && (
            <p className="mt-2 text-[13.5px]" style={{ color: 'var(--color-text-secondary)' }}>
              {subtitle}
            </p>
          )}
        </header>
        {children}
      </div>
    </div>
  );
}

// A section heading in letter-spaced capitals with a hairline, like
// «Marked» / «All · Notebooks · Documents» on the e-paper home.
export function PaperSection({ label, children, aside }: { label: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="mb-9">
      <div className="flex items-end justify-between pb-2 mb-4" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <h2 className="paper-label">{label}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
