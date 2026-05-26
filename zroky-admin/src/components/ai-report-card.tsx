import React from 'react';
import { AlertTriangle, Info, CheckCircle2, ShieldAlert, Cpu } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export type SeverityLevel = 'low' | 'medium' | 'high' | 'critical';

export interface AIReportProps {
  rootCause: string;
  suggestedFix: string;
  severity: SeverityLevel;
  confidenceScore?: number;
  className?: string;
}

export function AIReportCard({
  rootCause,
  suggestedFix,
  severity,
  confidenceScore,
  className
}: AIReportProps) {
  const getSeverityConfig = (level: SeverityLevel) => {
    switch (level) {
      case 'critical':
        return { icon: ShieldAlert, color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200' };
      case 'high':
        return { icon: AlertTriangle, color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200' };
      case 'medium':
        return { icon: Info, color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-200' };
      case 'low':
      default:
        return { icon: CheckCircle2, color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-200' };
    }
  };

  const config = getSeverityConfig(severity);
  const Icon = config.icon;

  return (
    <div className={cn("p-5 rounded-xl border shadow-sm", config.bg, config.border, className)}>
      <div className="flex items-center gap-3 mb-4 border-b pb-3 border-opacity-50" style={{ borderColor: 'inherit' }}>
        <Icon className={cn("h-6 w-6", config.color)} />
        <div className="flex-1">
          <h3 className={cn("font-semibold text-lg", config.color)}>AI Diagnosis</h3>
          <p className="text-xs text-gray-500 uppercase tracking-wider font-semibold">
            {severity} SEVERITY
          </p>
        </div>
        {confidenceScore !== undefined && (
          <div className="flex items-center gap-1 bg-white/60 px-2 py-1 rounded-md border shadow-sm">
            <Cpu className="h-4 w-4 text-purple-600" />
            <span className="text-xs font-bold text-gray-700">{confidenceScore}% Confidence</span>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div>
          <h4 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-gray-500" /> Root Cause
          </h4>
          <p className="text-sm text-gray-800 bg-white/50 p-3 rounded border border-gray-100">
            {rootCause}
          </p>
        </div>

        <div>
          <h4 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" /> Suggested Fix
          </h4>
          <p className="text-sm text-gray-800 bg-white/50 p-3 rounded border border-emerald-100">
            {suggestedFix}
          </p>
        </div>
      </div>
    </div>
  );
}
