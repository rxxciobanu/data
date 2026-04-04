import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ProbabilityBadge } from "@/components/probability-badge";
import type { AgentOpinion } from "@/types/api";
import { formatPercent } from "@/lib/utils";

interface DebatePanelProps {
  opinions: AgentOpinion[];
  synthesisReasoning: string | null;
  consensusProbability: number;
}

export function DebatePanel({
  opinions,
  synthesisReasoning,
  consensusProbability,
}: DebatePanelProps) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        {opinions.map((opinion) => (
          <Card key={opinion.agent_name}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">{opinion.agent_name}</CardTitle>
                <Badge variant="outline">
                  {formatPercent(opinion.confidence)} conf
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-2">
                <ProbabilityBadge value={opinion.probability} />
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {opinion.reasoning}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm">Consensus (Extremized)</CardTitle>
            <ProbabilityBadge value={consensusProbability} />
          </div>
        </CardHeader>
        {synthesisReasoning && (
          <CardContent>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {synthesisReasoning}
            </p>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
