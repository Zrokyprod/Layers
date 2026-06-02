import { redirectToAuthAlias, type AuthAliasSearchParams } from "@/app/auth/redirect-alias";

type LegacyLoginPageProps = {
  searchParams: AuthAliasSearchParams;
};

export default async function LegacyLoginPage({ searchParams }: LegacyLoginPageProps) {
  await redirectToAuthAlias("/login", searchParams);
}
