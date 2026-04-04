import { Badge } from "@/components/ui/badge";
import { formatCurrency, truncateAddress } from "@/lib/utils";
import type { WhaleSignal } from "@/types/api";

interface WhaleSignalRowProps {
  signal: WhaleSignal;
}

export function WhaleSignalRow({ signal }: WhaleSignalRowProps) {
  return (
    <div className="flex items-center justify-between rounded-md border p-3">
      <div className="flex items-center gap-3">
        <span className="font-mono text-sm">
          {signal.label || truncateAddress(signal.wallet)}
        </span>
        <Badge variant={signal.side === "BUY" ? "success" : "destructive"}>
          {signal.side}
        </Badge>
      </div>
      <span className="font-semibold">{formatCurrency(signal.size)}</span>
    </div>
  );
}
