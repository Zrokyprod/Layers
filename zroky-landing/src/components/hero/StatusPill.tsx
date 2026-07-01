import type { HeroTone } from '../../lib/heroTimeline';

const toneClasses: Record<HeroTone, string> = {
  neutral: 'border-[#d8dbd2] bg-[#eceee8] text-[#5f665d]',
  warning: 'border-[#b87922]/25 bg-[#b87922]/10 text-[#8a5a16]',
  accent: 'border-[#4f5a52]/25 bg-[#4f5a52]/10 text-[#3f4942]',
  success: 'border-[#2f7d50]/25 bg-[#2f7d50]/10 text-[#276844]',
};

const dotClasses: Record<HeroTone, string> = {
  neutral: 'bg-[#7c837b]',
  warning: 'bg-[#b87922]',
  accent: 'bg-[#4f5a52]',
  success: 'bg-[#2f7d50]',
};

export function StatusPill({
  tone,
  children,
  active = false,
}: {
  tone: HeroTone;
  children: string;
  active?: boolean;
}) {
  return (
    <span
      className={`inline-flex h-6 max-w-full items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-semibold uppercase tracking-[0.04em] ${toneClasses[tone]}`}
    >
      <span className="relative flex h-2 w-2 shrink-0 items-center justify-center">
        {active ? <span className={`absolute h-3.5 w-3.5 rounded-full ${dotClasses[tone]} opacity-20 motion-safe:animate-ping`} /> : null}
        <span className={`relative h-1.5 w-1.5 rounded-full ${dotClasses[tone]}`} />
      </span>
      <span className="whitespace-nowrap">{children}</span>
    </span>
  );
}
