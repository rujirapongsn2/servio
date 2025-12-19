"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Legend,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  LineChart,
  Line,
} from "recharts";
import { getApiBaseUrl } from "@/lib/api";
import ReactMarkdown from "react-markdown";

interface AnalyticsSummary {
  total_conversations: number;
  resolution_rate: number;
  avg_messages: number;
  avg_sentiment: number;
  outcome_breakdown?: Record<string, number>;
  sentiment_breakdown?: Record<string, number>;
  topic_breakdown?: Record<string, number>;
}

interface Conversation {
  id: number;
  session_id: string;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  total_messages: number;
  user_messages: number;
  agent_messages: number;
  agents_involved: string[];
  outcome: string;
  enrichment_status?: string;
  overall_sentiment?: string;
  sentiment_score?: number;
  primary_topic?: string;
  resolution_quality?: string;
  urgency_level?: string;
}

interface ConversationDetail {
  conversation: any;
  messages: any[];
  analytics: any;
}

interface TrendsData {
  daily_volume: Array<{ date: string; count: number }>;
  daily_sentiment: Array<{ date: string; sentiment: number }>;
  agent_performance: Array<{
    agent: string;
    conversations: number;
    performance: number;
    empathy: number;
    clarity: number;
    resolution_rate: number;
  }>;
}

export default function AnalyticsPage() {
  const apiBaseUrl = getApiBaseUrl();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [trends, setTrends] = useState<TrendsData | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<ConversationDetail | null>(null);
  const [period, setPeriod] = useState<string>("today");
  const [trendPeriod, setTrendPeriod] = useState<string>("week");
  const [filterOutcome, setFilterOutcome] = useState<string>("");
  const [filterSentiment, setFilterSentiment] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch analytics summary
  useEffect(() => {
    fetchSummary();
  }, [period]);

  // Fetch trends
  useEffect(() => {
    fetchTrends();
  }, [trendPeriod]);

  // Fetch conversations
  useEffect(() => {
    fetchConversations();
  }, [filterOutcome, filterSentiment]);

  const fetchSummary = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/analytics/summary?period=${period}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) throw new Error("Failed to fetch summary");

      const data = await response.json();
      setSummary(data);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const fetchTrends = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/analytics/trends?period=${trendPeriod}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) throw new Error("Failed to fetch trends");

      const data = await response.json();
      setTrends(data);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const fetchConversations = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem("adminToken");

      const params = new URLSearchParams({
        limit: "50",
        offset: "0",
      });

      if (filterOutcome) params.append("outcome", filterOutcome);
      if (filterSentiment) params.append("sentiment", filterSentiment);

      const response = await fetch(
        `${apiBaseUrl}/api/admin/analytics/conversations?${params}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) throw new Error("Failed to fetch conversations");

      const data = await response.json();
      setConversations(data.conversations);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchConversationDetail = async (id: number) => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/analytics/conversations/${id}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) throw new Error("Failed to fetch conversation detail");

      const data = await response.json();
      setSelectedConversation(data);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const formatDuration = (seconds: number) => {
    if (!seconds) return "N/A";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return "N/A";
    return new Date(dateString).toLocaleString();
  };

  const getSentimentColor = (sentiment?: string) => {
    switch (sentiment) {
      case "positive": return "text-green-600 bg-green-50";
      case "negative": return "text-red-600 bg-red-50";
      case "neutral": return "text-gray-600 bg-gray-50";
      default: return "text-gray-400 bg-gray-50";
    }
  };

  const getOutcomeColor = (outcome: string) => {
    switch (outcome) {
      case "resolved": return "text-green-600 bg-green-50";
      case "escalated": return "text-orange-600 bg-orange-50";
      case "abandoned": return "text-red-600 bg-red-50";
      case "ongoing": return "text-blue-600 bg-blue-50";
      default: return "text-gray-600 bg-gray-50";
    }
  };

  const getEnrichmentStatusColor = (status?: string) => {
    switch (status) {
      case "pending": return "text-yellow-600 bg-yellow-50";
      case "processing": return "text-blue-600 bg-blue-50";
      case "completed": return "text-green-600 bg-green-50";
      case "failed": return "text-red-600 bg-red-50";
      case "skipped": return "text-gray-500 bg-gray-50";
      default: return "text-gray-400 bg-gray-50";
    }
  };

  const ensureArray = (data: any) => {
    if (!data) return [];
    if (Array.isArray(data)) return data;
    if (typeof data === "string") {
      try {
        const parsed = JSON.parse(data);
        return Array.isArray(parsed) ? parsed : [];
      } catch (e) {
        return [];
      }
    }
    return [];
  };

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          Error: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">Analytics Dashboard</h1>

        {/* Period selector */}
        <div className="flex gap-2">
          {["today", "week", "month", "all"].map((p) => (
            <Button
              key={p}
              size="sm"
              variant={period === p ? "primary" : "outline"}
              onClick={() => setPeriod(p)}
            >
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
            <div className="text-sm font-medium text-gray-600">Total Conversations</div>
            <div className="text-3xl font-bold text-gray-900 mt-2">
              {summary.total_conversations}
            </div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
            <div className="text-sm font-medium text-gray-600">Resolution Rate</div>
            <div className="text-3xl font-bold text-green-600 mt-2">
              {summary.resolution_rate}%
            </div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
            <div className="text-sm font-medium text-gray-600">Avg Messages</div>
            <div className="text-3xl font-bold text-blue-600 mt-2">
              {summary.avg_messages}
            </div>
          </div>

          <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
            <div className="text-sm font-medium text-gray-600">Avg Sentiment</div>
            <div className="text-3xl font-bold text-purple-600 mt-2">
              {summary.avg_sentiment >= 0 ? "+" : ""}{summary.avg_sentiment.toFixed(2)}
            </div>
          </div>
        </div>
      )}

      {/* Pie Charts */}
      {summary && (summary.outcome_breakdown || summary.sentiment_breakdown) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Outcome Distribution */}
          {summary.outcome_breakdown && Object.keys(summary.outcome_breakdown).length > 0 && (
            <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Outcome Distribution</h3>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={Object.entries(summary.outcome_breakdown).map(([name, value]) => ({
                      name: name.charAt(0).toUpperCase() + name.slice(1),
                      value,
                    }))}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent = 0 }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {Object.entries(summary.outcome_breakdown).map(([name], index) => {
                      const colors: Record<string, string> = {
                        resolved: "#9BC53D",
                        escalated: "#F39C4F",
                        abandoned: "#FDD835",
                        ongoing: "#2E8BC0",
                        completed: "#9BC53D",
                      };
                      return <Cell key={`cell-${index}`} fill={colors[name] || "#9BC53D"} />;
                    })}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Sentiment Distribution */}
          {summary.sentiment_breakdown && Object.keys(summary.sentiment_breakdown).length > 0 && (
            <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Sentiment Distribution</h3>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={Object.entries(summary.sentiment_breakdown).map(([name, value]) => ({
                      name: name.charAt(0).toUpperCase() + name.slice(1),
                      value,
                    }))}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent = 0 }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {Object.entries(summary.sentiment_breakdown).map(([name], index) => {
                      const colors: Record<string, string> = {
                        positive: "#9BC53D",
                        neutral: "#2E8BC0",
                        negative: "#F39C4F",
                      };
                      return <Cell key={`cell-${index}`} fill={colors[name] || "#2E8BC0"} />;
                    })}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Topic Distribution Bar Chart */}
      {summary && summary.topic_breakdown && Object.keys(summary.topic_breakdown).length > 0 && (
        <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Top Topics</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={Object.entries(summary.topic_breakdown)
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .slice(0, 10)
                .map(([name, value]) => ({
                  topic: name.replace(/_/g, " ").charAt(0).toUpperCase() + name.replace(/_/g, " ").slice(1),
                  count: value,
                }))}
              margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="topic" angle={-45} textAnchor="end" height={100} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#2E8BC0" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Trend Charts */}
      {trends && (
        <div className="space-y-6">
          {/* Trend Period Selector */}
          <div className="flex justify-end gap-2">
            <span className="text-sm text-gray-600 self-center mr-2">Trend Period:</span>
            {["week", "month"].map((p) => (
              <Button
                key={p}
                size="sm"
                variant={trendPeriod === p ? "primary" : "outline"}
                onClick={() => setTrendPeriod(p)}
              >
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </Button>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Conversation Volume Trend */}
            {trends.daily_volume && trends.daily_volume.length > 0 && (
              <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Conversation Volume Trend</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={trends.daily_volume}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(value) => {
                        const date = new Date(value);
                        return `${date.getMonth() + 1}/${date.getDate()}`;
                      }}
                    />
                    <YAxis />
                    <Tooltip
                      labelFormatter={(value) => new Date(value).toLocaleDateString()}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="count"
                      stroke="#2E8BC0"
                      strokeWidth={2}
                      activeDot={{ r: 6 }}
                      dot={{ fill: "#2E8BC0" }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Sentiment Trend */}
            {trends.daily_sentiment && trends.daily_sentiment.length > 0 && (
              <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Sentiment Trend</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={trends.daily_sentiment}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(value) => {
                        const date = new Date(value);
                        return `${date.getMonth() + 1}/${date.getDate()}`;
                      }}
                    />
                    <YAxis domain={[-1, 1]} />
                    <Tooltip
                      labelFormatter={(value) => new Date(value).toLocaleDateString()}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="sentiment"
                      stroke="#9BC53D"
                      strokeWidth={2}
                      activeDot={{ r: 6 }}
                      dot={{ fill: "#9BC53D" }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Agent Performance */}
          {trends.agent_performance && trends.agent_performance.length > 0 && (
            <div className="bg-white p-6 rounded-lg shadow border border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Agent Performance</h3>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart
                  data={trends.agent_performance}
                  margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="agent" angle={-45} textAnchor="end" height={100} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="performance" fill="#2E8BC0" name="Performance %" />
                  <Bar dataKey="empathy" fill="#9BC53D" name="Empathy %" />
                  <Bar dataKey="clarity" fill="#FDD835" name="Clarity %" />
                  <Bar dataKey="resolution_rate" fill="#F39C4F" name="Resolution %" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="bg-white p-4 rounded-lg shadow border border-gray-200">
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Outcome
            </label>
            <select
              id="filterOutcome"
              title="Filter by Outcome"
              value={filterOutcome}
              onChange={(e) => setFilterOutcome(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All</option>
              <option value="resolved">Resolved</option>
              <option value="escalated">Escalated</option>
              <option value="abandoned">Abandoned</option>
              <option value="ongoing">Ongoing</option>
            </select>
          </div>

          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Sentiment
            </label>
            <select
              id="filterSentiment"
              title="Filter by Sentiment"
              value={filterSentiment}
              onChange={(e) => setFilterSentiment(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All</option>
              <option value="positive">Positive</option>
              <option value="neutral">Neutral</option>
              <option value="negative">Negative</option>
            </select>
          </div>
        </div>
      </div>

      {/* Conversations Table */}
      <div className="bg-white rounded-lg shadow border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">Conversations</h2>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading conversations...</div>
        ) : conversations.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No conversations found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Started
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Duration
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Messages
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Topic
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Sentiment
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Outcome
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    AI Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {conversations.map((conv) => (
                  <tr key={conv.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {formatDate(conv.started_at)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {formatDuration(conv.duration_seconds)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {conv.total_messages}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {conv.primary_topic ? (
                        <span className="px-2 py-1 text-xs font-medium rounded-full bg-blue-50 text-blue-700">
                          {conv.primary_topic.replace(/_/g, " ")}
                        </span>
                      ) : (
                        <span className="text-gray-400">N/A</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {conv.overall_sentiment ? (
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${getSentimentColor(conv.overall_sentiment)}`}>
                          {conv.overall_sentiment}
                        </span>
                      ) : (
                        <span className="text-gray-400">N/A</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span className={`px-2 py-1 text-xs font-medium rounded-full ${getOutcomeColor(conv.outcome)}`}>
                        {conv.outcome}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span className={`px-2 py-1 text-xs font-medium rounded-full ${getEnrichmentStatusColor(conv.enrichment_status)}`}>
                        {conv.enrichment_status || "N/A"}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => fetchConversationDetail(conv.id)}
                      >
                        View Details
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedConversation && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <h2 className="text-2xl font-bold text-gray-900">
                Conversation Details
              </h2>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setSelectedConversation(null)}
              >
                Close
              </Button>
            </div>

            <div className="p-6 space-y-6">
              {/* Conversation Info */}
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-3">Overview</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-sm text-gray-600">Started:</span>
                    <div className="text-sm font-medium">{formatDate(selectedConversation.conversation.started_at)}</div>
                  </div>
                  <div>
                    <span className="text-sm text-gray-600">Ended:</span>
                    <div className="text-sm font-medium">{formatDate(selectedConversation.conversation.ended_at)}</div>
                  </div>
                  <div>
                    <span className="text-sm text-gray-600">Duration:</span>
                    <div className="text-sm font-medium">{formatDuration(selectedConversation.conversation.duration_seconds)}</div>
                  </div>
                  <div>
                    <span className="text-sm text-gray-600">Messages:</span>
                    <div className="text-sm font-medium">{selectedConversation.conversation.total_messages}</div>
                  </div>
                </div>
              </div>

              {/* Analytics */}
              {selectedConversation.analytics && (
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">AI Analysis</h3>

                  {/* Sentiment */}
                  <div className="mb-4">
                    <div className="text-sm text-gray-600 mb-1">Sentiment</div>
                    <div className="flex items-center gap-2">
                      <span className={`px-3 py-1 text-sm font-medium rounded-full ${getSentimentColor(selectedConversation.analytics.overall_sentiment)}`}>
                        {selectedConversation.analytics.overall_sentiment}
                      </span>
                      <span className="text-sm text-gray-600">
                        Score: {selectedConversation.analytics.sentiment_score}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 mt-2">{selectedConversation.analytics.sentiment_explanation}</p>
                  </div>

                  {/* Topics */}
                  <div className="mb-4">
                    <div className="text-sm text-gray-600 mb-1">Topics</div>
                    <div className="flex flex-wrap gap-2">
                      {ensureArray(selectedConversation.analytics.topics).map((topic: string, i: number) => (
                        <span key={i} className="px-2 py-1 text-xs font-medium rounded-full bg-blue-50 text-blue-700">
                          {topic.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Quality */}
                  <div className="mb-4">
                    <div className="text-sm text-gray-600 mb-2">Quality Metrics</div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <span className="text-xs text-gray-500">Resolution:</span>
                        <div className="text-sm font-medium">{selectedConversation.analytics.resolution_quality}</div>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Agent Performance:</span>
                        <div className="text-sm font-medium">{(selectedConversation.analytics.agent_performance_score * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Clarity:</span>
                        <div className="text-sm font-medium">{(selectedConversation.analytics.response_clarity_score * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <span className="text-xs text-gray-500">Empathy:</span>
                        <div className="text-sm font-medium">{(selectedConversation.analytics.empathy_score * 100).toFixed(0)}%</div>
                      </div>
                    </div>
                  </div>

                  {/* Issues & Suggestions */}
                  {ensureArray(selectedConversation.analytics.issues_identified).length > 0 && (
                    <div className="mb-4">
                      <div className="text-sm text-gray-600 mb-1">Issues Identified</div>
                      <ul className="list-disc list-inside text-sm text-gray-700">
                        {ensureArray(selectedConversation.analytics.issues_identified).map((issue: string, i: number) => (
                          <li key={i}>{issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {ensureArray(selectedConversation.analytics.suggestions).length > 0 && (
                    <div className="mb-4">
                      <div className="text-sm text-gray-600 mb-1">Suggestions</div>
                      <ul className="list-disc list-inside text-sm text-gray-700">
                        {ensureArray(selectedConversation.analytics.suggestions).map((suggestion: string, i: number) => (
                          <li key={i}>{suggestion}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Messages */}
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-3">Messages</h3>
                <div className="space-y-3">
                  {ensureArray(selectedConversation.messages).map((msg: any, i: number) => (
                    <div
                      key={i}
                      className={`p-3 rounded-lg ${msg.role === "user"
                        ? "bg-gray-100 ml-8"
                        : "bg-blue-50 mr-8"
                        }`}
                    >
                      <div className="text-xs text-gray-600 mb-1">
                        {msg.role === "user" ? "User" : msg.agent_name || "Agent"}
                      </div>
                      <div className="text-sm text-gray-900 prose prose-sm max-w-none dark:prose-invert">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
