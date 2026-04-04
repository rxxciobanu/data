import { cn, formatPercent } from "@/lib/utils";

interface DivergenceBarProps {
  aiProb: number;
  marketProb: number;
  className?: string;
}

export function DivergenceBar({ aiProb, marketProb, className }: DivergenceBarProps) {
  const divergence = aiProb - marketProb;
  const absDivergence = Math.abs(divergence);
  const barColor =
    absDivergence >= 0.15
      ? "bg-emerald-500"
      : absDivergence >= 0.08
        ? "bg-amber-500"
        : "bg-slate-400";

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Market: {formatPercent(marketProb)}</span>
        <span>AI: {formatPercent(aiProb)}</span>
      </div>
      <div className="h-2 w-full rounded-full bg-secondary">
        <div
          className={cn("h-full rounded-full transition-all", barColor)}
          style={{ width: `${Math.min(absDivergence * 500, 100)}%` }}
        />
      </div>
      <p className="text-xs font-medium">
        Divergence: {divergence > 0 ? "+" : ""}
        {formatPercent(divergence)}
      </p>
    </div>
  );
}
