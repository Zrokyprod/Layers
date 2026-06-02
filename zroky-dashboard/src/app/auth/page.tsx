import { redirectToAuthAlias, type AuthAliasSearchParams } from "@/app/auth/redirect-alias";

type AuthIndexPageProps = {
  searchParams: AuthAliasSearchParams;
};

export default async function AuthIndexPage({ searchParams }: AuthIndexPageProps) {
  await redirectToAuthAlias("/login", searchParams);
}
