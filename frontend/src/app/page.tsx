"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Hero } from "@/components/marketing/Hero";
import { StatStrip } from "@/components/marketing/StatStrip";
import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { HowItWorks } from "@/components/marketing/HowItWorks";
import { FinalCTA } from "@/components/marketing/FinalCTA";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";

export default function LandingPage() {
  const router = useRouter();

  // Already-signed-in visitors skip the marketing page — best-effort only, the
  // landing page itself renders regardless so there's no loading gate/flash.
  useEffect(() => {
    fetch("/api/auth/me")
      .then((res) => {
        if (res.ok) router.replace("/workspaces");
      })
      .catch(() => {});
  }, [router]);

  return (
    <div className="bg-bg">
      <MarketingNav />
      <Hero />
      <StatStrip />
      <FeatureGrid />
      <HowItWorks />
      <FinalCTA />
      <MarketingFooter />
    </div>
  );
}
