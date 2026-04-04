import { formatCurrency, formatPercent } from "@/lib/utils";
import type { SizingDetails } from "@/types/api";

interface SizingBreakdownProps {
  sizing: SizingDetails;
  betAmount: number | null;
}

export function SizingBreakdown({ sizing, betAmount }: SizingBreakdownProps) {
  return (
    <div className="space-y-2 rounded-md border p-4">
      <h4 className="text-sm font-semibold">Kelly Sizing</h4>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="text-muted-foreground">Raw Kelly</div>
        <div className="font-medium">{formatPercent(sizing.kelly_raw)}</div>
        <div className="text-muted-foreground">Capped Kelly</div>
        <div className="font-medium">{formatPercent(sizing.kelly_final)}</div>
        {betAmount != null && (
          <>
            <div className="text-muted-foreground">Bet Amount</div>
            <div className="font-bold text-emerald-600">
              {formatCurrency(betAmount)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
