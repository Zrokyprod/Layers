import { redirectToAuthAlias, type AuthAliasSearchParams } from "@/app/auth/redirect-alias";

type LegacyForgotPasswordPageProps = {
  searchParams: AuthAliasSearchParams;
};

export default async function LegacyForgotPasswordPage({ searchParams }: LegacyForgotPasswordPageProps) {
  await redirectToAuthAlias("/forgot-password", searchParams);
}
