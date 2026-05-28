import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function AnnouncementBar() {
  return (
    <div className="fixed inset-x-0 top-0 z-[60] flex h-10 items-center justify-center bg-primary px-4">
      <Link
        to="/changelog"
        className="flex items-center gap-2.5 text-xs font-extrabold text-white transition duration-200 hover:text-gold"
      >
        <span className="hidden rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.12em] text-gold sm:inline">
          New
        </span>
        <span className="text-slate-200">
          CI Golden gates in open beta — real LLM replay on production incidents
        </span>
        <ArrowRight className="h-3.5 w-3.5 text-gold" />
      </Link>
    </div>
  );
}
