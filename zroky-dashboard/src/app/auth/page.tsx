import { redirect } from "next/navigation";

type AuthIndexPageProps = {
  searchParams: Promise<{
    next?: string | string[];
  }>;
};

function normalizeNextPath(value: string | string[] | undefined): string | null {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw) {
    return null;
  }

  const normalized = raw.trim();
  if (!normalized.startsWith("/")) {
    return null;
  }
  if (normalized.startsWith("//")) {
    return null;
  }
  return normalized;
}

export default async function AuthIndexPage({ searchParams }: AuthIndexPageProps) {
  const resolvedSearchParams = await searchParams;
  const nextPath = normalizeNextPath(resolvedSearchParams.next);

  if (nextPath) {
    redirect(`/auth/login?next=${encodeURIComponent(nextPath)}`);
  }

  redirect("/auth/login");
}
