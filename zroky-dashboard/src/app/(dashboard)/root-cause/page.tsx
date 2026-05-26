import { redirect } from "next/navigation";

export default function RootCauseRedirect() {
  redirect("/issues");
}
