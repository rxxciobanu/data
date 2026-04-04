"use client";

import { useState } from "react";
import Link from "next/link";
import { useAlerts } from "@/hooks/use-alerts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatPercent, formatCurrency, formatDate } from "@/lib/utils";

export default function AlertsPage() {
  const [page, setPage] = useState(1);
  const { data: alerts, isLoading } = useAlerts(page, 20);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Alerts</h1>

      {isLoading ? (
        <p className="text-muted-foreground">Loading alerts...</p>
      ) : !alerts || alerts.length === 0 ? (
        <p className="text-muted-foreground">
          No alerts found. Alerts are generated after each debate cycle based on
          your threshold settings.
        </p>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Market</TableHead>
                <TableHead>Side</TableHead>
                <TableHead>AI Prob</TableHead>
                <TableHead>Market Prob</TableHead>
                <TableHead>Divergence</TableHead>
                <TableHead>Bet Amount</TableHead>
                <TableHead>Cycle</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {alerts.map((alert) => (
                <TableRow key={alert.id}>
                  <TableCell>
                    <Link
                      href={`/alerts/${alert.id}`}
                      className="font-medium hover:underline"
                    >
                      {alert.market_question.length > 50
                        ? alert.market_question.slice(0, 50) + "..."
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
                    {formatPercent(alert.ai_probability)}
                  </TableCell>
                  <TableCell className="font-mono">
                    {formatPercent(alert.polymarket_probability)}
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
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(alert.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
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
              disabled={alerts.length < 20}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
