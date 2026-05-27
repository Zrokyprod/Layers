import { redirect } from "next/navigation";

export default function JudgeRedirect() {
  redirect("/settings/evaluation?workspace=judge");
}
