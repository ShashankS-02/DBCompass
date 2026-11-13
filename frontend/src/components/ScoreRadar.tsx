import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";

const DIMENSION_LABELS: Record<string, string> = {
  performance: "Performance",
  cost: "Cost",
  reliability: "Reliability",
  ops: "Operations",
  ecosystem: "Ecosystem",
  compliance: "Compliance",
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
          <PolarGrid stroke="#E9D3C3" />
          <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11, fill: "#665A52" }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar dataKey="score" stroke="#F96246" strokeWidth={2} fill="#F96246" fillOpacity={0.22} isAnimationActive animationDuration={900} />
          <Tooltip formatter={(value: number) => [`${value}/100`, "Score"]} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
