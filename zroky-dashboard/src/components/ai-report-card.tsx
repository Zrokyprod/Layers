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
        return {
          icon: ShieldAlert,
          color: 'var(--dashboard-danger, #c94b5f)',
          bg: 'var(--dashboard-danger-soft, rgba(132, 40, 55, 0.2))',
          border: 'var(--dashboard-danger-border, rgba(201, 75, 95, 0.34))',
        };
      case 'high':
        return {
          icon: AlertTriangle,
          color: 'var(--dashboard-accent, #f8fafc)',
          bg: 'var(--dashboard-accent-soft, rgba(248, 250, 252, 0.085))',
          border: 'rgba(248, 250, 252, 0.28)',
        };
      case 'medium':
        return {
          icon: Info,
          color: 'var(--dashboard-warning, #c49a2c)',
          bg: 'var(--dashboard-warning-soft, rgba(124, 97, 15, 0.18))',
          border: 'var(--dashboard-warning-border, rgba(196, 154, 44, 0.34))',
        };
      case 'low':
      default:
        return {
          icon: CheckCircle2,
          color: 'var(--dashboard-info, #5088b7)',
          bg: 'var(--dashboard-info-soft, rgba(42, 86, 124, 0.18))',
          border: 'var(--dashboard-info-border, rgba(80, 136, 183, 0.34))',
        };
    }
  };

  const config = getSeverityConfig(severity);
  const Icon = config.icon;

  return (
    <div
      className={cn("p-5 rounded-xl border shadow-sm", className)}
      style={{ background: config.bg, borderColor: config.border }}
    >
      <div className="flex items-center gap-3 mb-4 border-b pb-3 border-opacity-50" style={{ borderColor: 'inherit' }}>
        <Icon className="h-6 w-6" style={{ color: config.color }} />
        <div className="flex-1">
          <h3 className="font-semibold text-lg" style={{ color: config.color }}>AI Diagnosis</h3>
          <p className="text-xs text-gray-500 uppercase tracking-wider font-semibold">
            {severity} SEVERITY
          </p>
        </div>
        {confidenceScore !== undefined && (
          <div className="flex items-center gap-1 bg-white/60 px-2 py-1 rounded-md border shadow-sm">
            <Cpu className="h-4 w-4" style={{ color: 'var(--dashboard-info, #5088b7)' }} />
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
            <CheckCircle2 className="h-4 w-4" style={{ color: 'var(--dashboard-success, #3a9663)' }} /> Suggested Fix
          </h4>
          <p className="text-sm text-gray-800 bg-white/50 p-3 rounded border border-emerald-100">
            {suggestedFix}
          </p>
        </div>
      </div>
    </div>
  );
}
