"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useMarketDetail, useMarketDebate } from "@/hooks/use-markets";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DivergenceBar } from "@/components/divergence-bar";
import { DebatePanel } from "@/components/debate-panel";
import { formatDate } from "@/lib/utils";

export default function MarketDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: market, isLoading } = useMarketDetail(id);
  const { data: debate } = useMarketDebate(id);

  if (isLoading) return <p className="text-muted-foreground">Loading...</p>;
  if (!market) return <p className="text-muted-foreground">Market not found</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/markets">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">{market.market_question}</h1>
          <p className="text-sm text-muted-foreground">
            {formatDate(market.created_at)} &middot; Cycle: {market.cycle_id}
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Price Comparison</CardTitle>
        </CardHeader>
        <CardContent>
          <DivergenceBar
            aiProb={market.consensus_probability}
            marketProb={market.polymarket_price}
          />
        </CardContent>
      </Card>

      {debate && (
        <>
          <h2 className="text-xl font-bold">AI Debate</h2>
          <DebatePanel
            opinions={debate.opinions}
            synthesisReasoning={debate.synthesis_reasoning}
            consensusProbability={debate.consensus_probability}
          />

          {debate.news_articles.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>News Sources</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {debate.news_articles.map((article, i) => (
                    <li key={i} className="text-sm">
                      <span className="font-medium">{article.title}</span>
                      <span className="text-muted-foreground">
                        {" "}
                        — {article.source}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
