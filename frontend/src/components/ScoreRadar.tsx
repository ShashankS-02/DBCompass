import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";

const DIMENSION_LABELS: Record<string, string> = {
  performance: "Performance",
  cost: "Cost",
  reliability: "Reliability",
  ops: "Ops",
  ecosystem: "Ecosystem",
  compliance: "Compliance",
  portability: "Portability",
};

export default function ScoreRadar({ scores }: { scores: Record<string, number> }) {
  const data = Object.keys(DIMENSION_LABELS).map((dimension) => ({
    dimension: DIMENSION_LABELS[dimension],
    score: Math.round(scores[dimension] ?? 0),
  }));

  return (
    <div className="h-56 w-full" role="img" aria-label="Score by dimension">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="70%">
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11, fill: "#475569" }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar dataKey="score" stroke="#0f172a" fill="#0f172a" fillOpacity={0.15} isAnimationActive={false} />
          <Tooltip formatter={(value: number) => [`${value}/100`, "Score"]} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
