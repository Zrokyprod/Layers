"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function JudgePage() {
  const router = useRouter();
  useEffect(() => { router.replace("/calibration?tab=judge"); }, [router]);
  return null;
}
