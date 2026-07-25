import { redirect } from "next/navigation";

export default function IncidentsPage() {
  redirect("/operations?filter=incidents");
}
