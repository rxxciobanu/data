"use client";

import { useState } from "react";
import Link from "next/link";
import { useMarkets } from "@/hooks/use-markets";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DivergenceBar } from "@/components/divergence-bar";
import { Search } from "lucide-react";

export default function MarketsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const { data: markets, isLoading } = useMarkets(page, 50);

  const filtered = markets?.filter((m) =>
    m.market_question.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Markets</h1>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search markets..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10"
        />
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading markets...</p>
      ) : !filtered || filtered.length === 0 ? (
        <p className="text-muted-foreground">
          No markets found. Markets appear after a debate cycle runs.
        </p>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filtered.map((market) => {
              const divergence =
                market.consensus_probability - market.polymarket_price;
              return (
                <Link key={market.id} href={`/markets/${market.id}`}>
                  <Card className="h-full hover:shadow-md transition-shadow cursor-pointer">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm leading-tight">
                        {market.market_question}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <DivergenceBar
                        aiProb={market.consensus_probability}
                        marketProb={market.polymarket_price}
                      />
                      <div className="flex items-center justify-between">
                        <Badge variant="outline">{market.cycle_id}</Badge>
                        <Badge
                          variant={
                            Math.abs(divergence) >= 0.10
                              ? "success"
                              : "secondary"
                          }
                        >
                          {Math.abs(divergence) >= 0.10
                            ? "Opportunity"
                            : "In line"}
                        </Badge>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">Page {page}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={!markets || markets.length < 50}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
