import { redirectToAuthAlias, type AuthAliasSearchParams } from "@/app/auth/redirect-alias";

type LegacyVerifyEmailPageProps = {
  searchParams: AuthAliasSearchParams;
};

export default async function LegacyVerifyEmailPage({ searchParams }: LegacyVerifyEmailPageProps) {
  await redirectToAuthAlias("/verify-email", searchParams);
}
