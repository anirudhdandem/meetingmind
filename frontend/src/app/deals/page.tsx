import { redirect } from "next/navigation";

// Deals merged into Companies: one company == one deal here, so the pipeline
// health/stage now lives on the Companies list and each company's detail page.
// Kept as a redirect so old links/bookmarks land somewhere sensible.
export default function DealsPage() {
  redirect("/companies");
}
