import { redirect } from "next/navigation";

export type AuthAliasSearchParams = Promise<Record<string, string | string[] | undefined>>;

export function buildAuthAliasUrl(path: string, params: Record<string, string | string[] | undefined>): string {
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        query.append(key, item);
      }
      continue;
    }

    if (typeof value === "string") {
      query.set(key, value);
    }
  }

  const serialized = query.toString();
  return serialized ? `${path}?${serialized}` : path;
}

export async function redirectToAuthAlias(path: string, searchParams: AuthAliasSearchParams) {
  redirect(buildAuthAliasUrl(path, await searchParams));
}
