export default function Placeholder({ title, milestone }: { title: string; milestone: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
      <p className="mt-2 text-slate-600">Coming in {milestone}.</p>
    </div>
  );
}
