import { redirect } from "next/navigation";

export default function CalibrationRedirect() {
  redirect("/settings/evaluation?workspace=calibration");
}
