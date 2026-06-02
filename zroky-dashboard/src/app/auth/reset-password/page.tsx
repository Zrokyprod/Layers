import { redirectToAuthAlias, type AuthAliasSearchParams } from "@/app/auth/redirect-alias";

type LegacyResetPasswordPageProps = {
  searchParams: AuthAliasSearchParams;
};

export default async function LegacyResetPasswordPage({ searchParams }: LegacyResetPasswordPageProps) {
  await redirectToAuthAlias("/reset-password", searchParams);
}
