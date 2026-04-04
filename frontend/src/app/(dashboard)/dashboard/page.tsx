"use client";

import Link from "next/link";
import { Bell, BarChart3, TrendingUp, DollarSign } from "lucide-react";
import { StatsCard } from "@/components/stats-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useLatestAlerts, useAlertStats } from "@/hooks/use-alerts";
import { useMarkets } from "@/hooks/use-markets";
import { formatPercent, formatCurrency, formatDate } from "@/lib/utils";

export default function DashboardPage() {
  const { data: alerts } = useLatestAlerts();
  const { data: stats } = useAlertStats();
  const { data: markets } = useMarkets(1, 5);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Dashboard</h1>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Total Alerts"
          value={String(stats?.total_alerts ?? 0)}
          description="Across all cycles"
          icon={Bell}
        />
        <StatsCard
          title="Avg Divergence"
          value={stats?.avg_divergence ? formatPercent(stats.avg_divergence) : "N/A"}
          description="AI vs Market spread"
          icon={TrendingUp}
        />
        <StatsCard
          title="Total Exposure"
          value={
            stats?.total_bet_amount
              ? formatCurrency(stats.total_bet_amount)
              : "$0"
          }
          description="Recommended bets"
          icon={DollarSign}
        />
        <StatsCard
          title="Active Markets"
          value={String(markets?.length ?? 0)}
          description="Being analyzed"
          icon={BarChart3}
        />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Recent Alerts</CardTitle>
            <Link
              href="/alerts"
              className="text-sm text-muted-foreground hover:underline"
            >
              View all
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {!alerts || alerts.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No alerts yet. Alerts are generated after each debate cycle.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Market</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Divergence</TableHead>
                  <TableHead>Bet</TableHead>
                  <TableHead>Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.slice(0, 5).map((alert) => (
                  <TableRow key={alert.id}>
                    <TableCell>
                      <Link
                        href={`/alerts/${alert.id}`}
                        className="font-medium hover:underline"
                      >
                        {alert.market_question.length > 60
                          ? alert.market_question.slice(0, 60) + "..."
                          : alert.market_question}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          alert.recommended_side === "YES"
                            ? "success"
                            : "destructive"
                        }
                      >
                        {alert.recommended_side}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono">
                      {alert.divergence > 0 ? "+" : ""}
                      {formatPercent(alert.divergence)}
                    </TableCell>
                    <TableCell>
                      {alert.bet_amount
                        ? formatCurrency(alert.bet_amount)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {formatDate(alert.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
