'use client'

import { useEffect, useState } from 'react'

interface IntentStatistics {
  total_active_sessions: number
  by_intent: Record<string, number>
  unclassified: number
  timestamp: number
  intent_groups: Array<{
    group: string
    color: string
    count: number
  }>
}

function getTextColor(bgColor: string): string {
  // Return white text for dark colors, dark text for light colors
  switch (bgColor) {
    case '#2ECC71': // Green - light
      return 'text-green-800'
    case '#F39C12': // Orange - light
      return 'text-orange-800'
    case '#F1C40F': // Yellow - light
      return 'text-yellow-800'
    case '#E74C3C': // Red - medium
      return 'text-white'
    case '#8E0E00': // Dark red
      return 'text-white'
    default:
      return 'text-gray-800'
  }
}

export default function IntentMonitor({ teamAgentId }: { teamAgentId?: number | null }) {
  const [stats, setStats] = useState<IntentStatistics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const token = localStorage.getItem('adminToken')
        const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : ''
        const response = await fetch(`/api/admin/intent-statistics${params}`, {
          headers: {
            Authorization: `Bearer ${token}`
          }
        })

        if (!response.ok) {
          throw new Error(`Failed to fetch intent statistics: ${response.statusText}`)
        }

        const data = await response.json()
        setStats(data)
        setError(null)
      } catch (err) {
        console.error('Error fetching intent statistics:', err)
        setError(err instanceof Error ? err.message : 'Failed to fetch data')
      } finally {
        setLoading(false)
      }
    }

    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => clearInterval(interval)
  }, [teamAgentId])

  if (loading) {
    return (
      <div>
        <div className="text-center text-gray-500 py-4">Loading intent data...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center text-red-500 py-4">{error}</div>
    )
  }

  return (
    <>
      {/* Section Title */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Real-Time Intent Distribution</h2>
        {stats && (
          <span className="text-xs text-gray-500">
            Last updated: {new Date(stats.timestamp * 1000).toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Metric Cards Grid */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Total Active Sessions Card */}
          <div className="bg-blue-50 border border-blue-200 p-6 rounded-lg shadow">
            <div className="text-sm font-medium text-gray-600">Total Active Sessions</div>
            <div className="text-4xl font-bold text-blue-600 mt-3">
              {stats.total_active_sessions}
            </div>
          </div>

          {/* Intent Group Cards */}
          {stats.intent_groups.map(intent => (
            <div
              key={intent.group}
              className="p-6 rounded-lg shadow border border-gray-200 transition-all hover:shadow-lg"
              style={{ backgroundColor: intent.color }}
            >
              <div className={`text-sm font-medium mb-2 ${getTextColor(intent.color)} opacity-90`}>
                {intent.group}
              </div>
              <div className={`text-3xl font-bold ${getTextColor(intent.color)}`}>
                {intent.count}
              </div>
              <div className={`text-xs mt-2 ${getTextColor(intent.color)} opacity-75`}>
                {stats.total_active_sessions > 0
                  ? `${((intent.count / stats.total_active_sessions) * 100).toFixed(1)}%`
                  : '0%'
                }
              </div>
            </div>
          ))}

          {/* Unclassified Card */}
          {stats.unclassified > 0 && (
            <div className="bg-gray-100 border border-gray-300 p-6 rounded-lg shadow">
              <div className="text-sm font-medium text-gray-700">Unclassified</div>
              <div className="text-3xl font-bold text-gray-700 mt-3">
                {stats.unclassified}
              </div>
              <div className="text-xs text-gray-600 mt-2">
                {stats.total_active_sessions > 0
                  ? `${((stats.unclassified / stats.total_active_sessions) * 100).toFixed(1)}%`
                  : '0%'
                }
              </div>
            </div>
          )}
        </div>
      )}

      {/* No active sessions message */}
      {stats && stats.total_active_sessions === 0 && (
        <div className="text-center text-gray-500 py-8 bg-gray-50 rounded-lg">
          No active sessions at the moment
        </div>
      )}
    </>
  )
}
