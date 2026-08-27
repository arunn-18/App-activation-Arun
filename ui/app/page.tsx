import { redirect } from "next/navigation";

/** App Activation only (2026-08-27 charter): the general Automations panel
 *  that used to live at "/" moved to legacy/ui/app/page.tsx along with its
 *  own backend (legacy/engine/serve_api.py, legacy/engine/serve2.py) — it
 *  built ANY Hiver automation, with or without an app action, which is out
 *  of scope now. "/apps" (serve_apps.py) is this app's real home. */
export default function Home() {
  redirect("/apps");
}
