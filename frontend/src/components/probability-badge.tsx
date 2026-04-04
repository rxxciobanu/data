import { Badge } from "@/components/ui/badge";
import { formatPercent } from "@/lib/utils";

interface ProbabilityBadgeProps {
  value: number;
  label?: string;
}

export function ProbabilityBadge({ value, label }: ProbabilityBadgeProps) {
  const variant = value >= 0.7 ? "success" : value >= 0.4 ? "warning" : "destructive";
  return (
    <Badge variant={variant}>
      {label && `${label}: `}
      {formatPercent(value)}
    </Badge>
  );
}
