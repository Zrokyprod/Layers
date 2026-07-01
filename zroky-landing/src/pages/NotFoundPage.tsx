import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div className="grid min-h-[70vh] w-full place-items-center bg-[#fbfcfa] px-6 text-center text-[#20231f]">
      <div>
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[#4f5a52]">404</p>
        <h1 className="mt-3 text-balance text-[2rem] font-semibold leading-[1.1] tracking-[-0.025em] text-[#20231f] md:text-[2.75rem]">
          This page could not be found.
        </h1>
        <p className="mx-auto mt-4 max-w-md text-[1.02rem] leading-[1.6] text-[#5b615a]">
          The link may be broken or the page may have moved.
        </p>
        <Link
          to="/"
          className="mt-8 inline-flex h-11 items-center justify-center gap-2 rounded-[10px] bg-[linear-gradient(180deg,#5f675f,#343a34)] px-5 text-sm font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_10px_24px_-12px_rgba(42,45,40,0.55)] transition hover:-translate-y-px hover:bg-[#4f5a52]"
        >
          <ArrowLeft size={16} /> Back to home
        </Link>
      </div>
    </div>
  );
}
