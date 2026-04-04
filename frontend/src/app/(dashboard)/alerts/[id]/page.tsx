"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useAlertDetail } from "@/hooks/use-alerts";
import { useMarketDebate } from "@/hooks/use-markets";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DivergenceBar } from "@/components/divergence-bar";
import { SizingBreakdown } from "@/components/sizing-breakdown";
import { DebatePanel } from "@/components/debate-panel";
import { WhaleSignalRow } from "@/components/whale-signal-row";
import { formatDate } from "@/lib/utils";

export default function AlertDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: alert, isLoading } = useAlertDetail(id);
  const { data: debate } = useMarketDebate(
    alert?.debate_result_id ?? null
  );

  if (isLoading) return <p className="text-muted-foreground">Loading...</p>;
  if (!alert) return <p className="text-muted-foreground">Alert not found</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/alerts">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">{alert.market_question}</h1>
          <p className="text-sm text-muted-foreground">
            {formatDate(alert.created_at)} &middot; Cycle: {alert.cycle_id}
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Signal</CardTitle>
              <Badge
                variant={
                  alert.recommended_side === "YES" ? "success" : "destructive"
                }
              >
                {alert.recommended_side}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <DivergenceBar
              aiProb={alert.ai_probability}
              marketProb={alert.polymarket_probability}
            />
          </CardContent>
        </Card>

        {alert.sizing_details && (
          <SizingBreakdown
            sizing={alert.sizing_details}
            betAmount={alert.bet_amount}
          />
        )}
      </div>

      {alert.whale_signals.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Whale Signals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {alert.whale_signals.map((signal, i) => (
              <WhaleSignalRow key={i} signal={signal} />
            ))}
          </CardContent>
        </Card>
      )}

      {debate && (
        <div className="space-y-4">
          <h2 className="text-xl font-bold">AI Debate</h2>
          <DebatePanel
            opinions={debate.opinions}
            synthesisReasoning={debate.synthesis_reasoning}
            consensusProbability={debate.consensus_probability}
          />
        </div>
      )}
    </div>
  );
}
