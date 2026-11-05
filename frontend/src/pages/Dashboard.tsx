import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { getMe, getSkillStats, getDomainStats, getAttemptHistory } from '../api/analytics'
import { Button } from '../components/ui/Button'

export function Dashboard() {
  const navigate = useNavigate()

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: getMe, staleTime: 30_000 })
  const { data: skills } = useQuery({ queryKey: ['skills'], queryFn: getSkillStats, staleTime: 30_000 })
  const { data: domains } = useQuery({ queryKey: ['domains'], queryFn: getDomainStats, staleTime: 30_000 })
  const { data: history } = useQuery({ queryKey: ['history'], queryFn: getAttemptHistory, staleTime: 30_000 })

  const weakestSkills = (skills ?? [])
    .filter((s) => s.total > 0)
    .sort((a, b) => (a.accuracy_pct ?? 100) - (b.accuracy_pct ?? 100))
    .slice(0, 8)

  const domainChartData = (domains ?? []).map((d) => ({
    name: d.domain_name.replace('Information and Ideas', 'Info & Ideas'),
    accuracy: d.accuracy_pct ?? 0,
    total: d.total,
  }))

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <Button onClick={() => navigate('/')}>Start New Test</Button>
        </div>

        {/* Summary cards */}
        {me && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <StatCard label="Tests Taken" value={String(me.total_attempts)} />
            <StatCard label="Overall Accuracy" value={me.overall_accuracy != null ? `${me.overall_accuracy}%` : '—'} />
            <StatCard label="Best Score" value={me.best_score != null ? String(me.best_score) : '—'} />
            <StatCard label="Latest Score" value={me.latest_score != null ? String(me.latest_score) : '—'} />
          </div>
        )}

        {/* Domain accuracy chart */}
        {domainChartData.length > 0 && (
          <section aria-label="Domain accuracy chart">
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Domain Accuracy</h2>
            <div className="bg-white rounded-xl shadow-sm p-4">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={domainChartData} margin={{ left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(val: number) => [`${val}%`, 'Accuracy']}
                    contentStyle={{ fontSize: 12 }}
                  />
                  <Bar dataKey="accuracy" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}

        {/* Weakest skills */}
        {weakestSkills.length > 0 && (
          <section aria-label="Skill breakdown">
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Skills to Improve</h2>
            <div className="bg-white rounded-xl shadow-sm divide-y">
              {weakestSkills.map((s) => (
                <div key={s.skill_id} className="flex items-center px-4 py-3 gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{s.skill_name}</p>
                    <p className="text-xs text-gray-400">{s.domain}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-gray-700">
                      {s.accuracy_pct != null ? `${s.accuracy_pct}%` : '—'}
                    </p>
                    <p className="text-xs text-gray-400">{s.correct}/{s.total}</p>
                  </div>
                  <div className="w-24">
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${s.accuracy_pct ?? 0}%` }}
                        aria-hidden="true"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Attempt history */}
        {history && history.length > 0 && (
          <section aria-label="Attempt history">
            <h2 className="text-lg font-semibold text-gray-800 mb-3">Recent Attempts</h2>
            <div className="bg-white rounded-xl shadow-sm divide-y">
              {history.slice(0, 10).map((a) => (
                <div key={a.attempt_id} className="flex items-center px-4 py-3 gap-4">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-800">
                      {new Date(a.started_at).toLocaleDateString(undefined, {
                        month: 'short', day: 'numeric', year: 'numeric',
                      })}
                    </p>
                    {a.stage2_level && (
                      <p className="text-xs text-gray-400">Routed → {a.stage2_level}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-gray-700">
                      {a.rw_raw != null ? `${a.rw_raw} raw` : a.completed_at ? 'Completed' : 'In progress'}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {!me && !skills && !history && (
          <p className="text-gray-400 text-center py-12">
            Complete a test to see your stats.
          </p>
        )}
      </div>
    </main>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl shadow-sm px-4 py-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  )
}
