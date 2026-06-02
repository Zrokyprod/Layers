import { redirectToAuthAlias, type AuthAliasSearchParams } from "@/app/auth/redirect-alias";

type LegacyRegisterPageProps = {
  searchParams: AuthAliasSearchParams;
};

export default async function LegacyRegisterPage({ searchParams }: LegacyRegisterPageProps) {
  await redirectToAuthAlias("/signup", searchParams);
}
