import { redirectToAuthAlias, type AuthAliasSearchParams } from "@/app/auth/redirect-alias";

type LegacyCheckEmailPageProps = {
  searchParams: AuthAliasSearchParams;
};

export default async function LegacyCheckEmailPage({ searchParams }: LegacyCheckEmailPageProps) {
  await redirectToAuthAlias("/verify-email", searchParams);
}
