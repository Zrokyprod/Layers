import type { ReactNode } from 'react';

export type LegalSection = {
  heading: string;
  body: ReactNode;
};

export default function LegalPage({
  title,
  updated,
  intro,
  sections,
}: {
  title: string;
  updated: string;
  intro: string;
  sections: LegalSection[];
}) {
  return (
    <div className="w-full bg-[#fbfcfa] text-[#20231f]">
      <section className="mx-auto max-w-3xl px-6 pb-24 pt-32">
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#4f5a52]">Legal</p>
        <h1 className="mt-3 text-balance text-[2.25rem] font-semibold leading-[1.08] tracking-[-0.025em] text-[#20231f] md:text-[3rem]">
          {title}
        </h1>
        <p className="mt-3 text-sm text-[#8b9288]">Last updated {updated}</p>
        <p className="mt-6 text-[1.02rem] leading-[1.7] text-[#5b615a]">{intro}</p>

        <div className="mt-12 space-y-10">
          {sections.map((section) => (
            <div key={section.heading}>
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.015em] text-[#20231f]">{section.heading}</h2>
              <div className="mt-3 space-y-3 text-[0.98rem] leading-[1.7] text-[#5b615a]">{section.body}</div>
            </div>
          ))}
        </div>

        <div className="mt-14 rounded-[16px] border border-[#d8dbd2] bg-[#f4f6f1] p-6">
          <p className="text-sm leading-relaxed text-[#5b615a]">
            Questions about this policy? Contact{' '}
            <a href="mailto:hello@zroky.com" className="font-semibold text-[#3f4942] underline underline-offset-2">
              hello@zroky.com
            </a>
            .
          </p>
        </div>
      </section>
    </div>
  );
}
