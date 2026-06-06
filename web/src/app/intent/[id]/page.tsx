import { Suspense } from "react";
import IntentDashboard from "./IntentDashboard";

export default async function IntentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense fallback={<div className="p-6 text-sm text-neutral-500">Loading…</div>}>
      <IntentDashboard intentId={id} />
    </Suspense>
  );
}
