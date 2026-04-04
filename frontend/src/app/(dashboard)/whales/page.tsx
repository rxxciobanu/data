"use client";

import { useWhaleLeaderboard, useWhaleSignals } from "@/hooks/use-whales";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency, formatPercent, truncateAddress } from "@/lib/utils";

export default function WhalesPage() {
  const { data: leaderboard, isLoading: lbLoading } = useWhaleLeaderboard();
  const { data: signals } = useWhaleSignals();

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Whale Tracker</h1>

      <Card>
        <CardHeader>
          <CardTitle>Leaderboard</CardTitle>
        </CardHeader>
        <CardContent>
          {lbLoading ? (
            <p className="text-muted-foreground">Loading...</p>
          ) : !leaderboard || leaderboard.length === 0 ? (
            <p className="text-muted-foreground">
              No whale data available yet. Data appears after a debate cycle
              with whale scanning enabled.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Wallet</TableHead>
                  <TableHead>ROI</TableHead>
                  <TableHead>Win Rate</TableHead>
                  <TableHead>Volume</TableHead>
                  <TableHead>Expertise</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {leaderboard.map((whale) => (
                  <TableRow key={whale.wallet_address}>
                    <TableCell className="font-mono">
                      {whale.wallet_label ||
                        truncateAddress(whale.wallet_address)}
                    </TableCell>
                    <TableCell className="font-mono">
                      {formatPercent(whale.wallet_stats.roi)}
                    </TableCell>
                    <TableCell className="font-mono">
                      {formatPercent(whale.wallet_stats.win_rate)}
                    </TableCell>
                    <TableCell>
                      {formatCurrency(whale.wallet_stats.total_volume)}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {whale.wallet_stats.theme_expertise
                          .slice(0, 3)
                          .map((theme) => (
                            <Badge key={theme} variant="outline">
                              {theme}
                            </Badge>
                          ))}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {signals && Array.isArray(signals) && (signals as unknown[]).length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Your Whale Signals</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Signals from wallets matching your tracked addresses.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
