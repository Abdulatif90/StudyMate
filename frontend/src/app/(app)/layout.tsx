import { AppShell } from "@/components/app-shell";
import { ReferralRedeemer } from "@/components/referral-redeemer";

export default function AppRouteGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ReferralRedeemer />
      <AppShell>{children}</AppShell>
    </>
  );
}
