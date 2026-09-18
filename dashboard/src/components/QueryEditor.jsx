import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Play, Loader2, Clock, Database, Copy, Check, BookOpen } from 'lucide-react';
import { runQuery, getQueryResults } from '../utils/api';

const SAMPLE_QUERIES = [
  {
    name: 'Event Count by Type',
    sql: `SELECT event_type, COUNT(*) as event_count
FROM streamforge.clean_events
WHERE year = '2026' AND month = '09'
GROUP BY event_type
ORDER BY event_count DESC
LIMIT 20`,
  },
  {
    name: 'Anomaly Summary',
    sql: `SELECT event_type,
       COUNT(*) as total,
       SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END) as anomalies,
       ROUND(AVG(anomaly_score), 4) as avg_score
FROM streamforge.clean_events
GROUP BY event_type
ORDER BY anomalies DESC`,
  },
  {
    name: 'Hourly Throughput',
    sql: `SELECT DATE_FORMAT(from_unixtime(timestamp/1000), '%Y-%m-%d %H:00') as hour,
       pipeline_id,
       COUNT(*) as events
FROM streamforge.raw_events
GROUP BY 1, 2
ORDER BY hour DESC
LIMIT 48`,
  },
  {
    name: 'Top Sources',
    sql: `SELECT source, COUNT(*) as event_count,
       COUNT(DISTINCT pipeline_id) as pipelines
FROM streamforge.raw_events
GROUP BY source
ORDER BY event_count DESC
LIMIT 10`,
  },
];

export default function QueryEditor() {
  const [sql, setSql] = useState(SAMPLE_QUERIES[0].sql);
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const executeQuery = useCallback(async () => {
    setIsRunning(true);
    setError(null);
    setResult(null);

    try {
      const response = await runQuery(sql);

      if (response.status === 'running') {
        let attempts = 0;
        const maxAttempts = 30;
        const pollInterval = 1000;

        const poll = async () => {
          if (attempts >= maxAttempts) {
            setError('Query timed out');
            setIsRunning(false);
            return;
          }

          const results = await getQueryResults(response.query_id);

          if (results.status === 'completed') {
            setResult(results);
            setIsRunning(false);
          } else if (results.status === 'failed') {
            setError(results.error || 'Query failed');
            setIsRunning(false);
          } else {
            attempts++;
            setTimeout(poll, pollInterval);
          }
        };

        setTimeout(poll, pollInterval);
      } else if (response.status === 'completed') {
        setResult(response);
        setIsRunning(false);
      }
    } catch (err) {
      setError(err.message || 'Failed to execute query');
      setIsRunning(false);
    }
  }, [sql]);

  const copyResults = () => {
    if (result?.rows) {
      const csv = [result.columns.join(',')]
        .concat(result.rows.map(r => result.columns.map(c => r[c] || '').join(',')))
        .join('\n');
      navigator.clipboard.writeText(csv);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-6">
      {/* Sample Queries */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        <BookOpen className="w-4 h-4 text-gray-400 flex-shrink-0" />
        {SAMPLE_QUERIES.map((q) => (
          <button
            key={q.name}
            onClick={() => setSql(q.sql)}
            className="px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-white bg-gray-800/50 hover:bg-gray-800 rounded-lg whitespace-nowrap transition-colors"
          >
            {q.name}
          </button>
        ))}
      </div>

      {/* Editor */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card overflow-hidden"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800/50">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-forge-400" />
            <span className="text-sm font-medium text-gray-300">SQL Editor</span>
            <span className="text-xs text-gray-500">database: streamforge</span>
          </div>
          <button
            onClick={executeQuery}
            disabled={isRunning || !sql.trim()}
            className="flex items-center gap-2 px-4 py-1.5 bg-forge-600 hover:bg-forge-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {isRunning ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {isRunning ? 'Running...' : 'Run Query'}
          </button>
        </div>

        <textarea
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          className="w-full h-48 px-4 py-3 bg-gray-950 text-white font-mono text-sm resize-none focus:outline-none leading-relaxed"
          placeholder="SELECT * FROM streamforge.raw_events LIMIT 10"
          spellCheck={false}
        />
      </motion.div>

      {/* Error */}
      {error && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="p-4 rounded-xl bg-red-500/10 border border-red-500/20"
        >
          <p className="text-sm text-red-400">{error}</p>
        </motion.div>
      )}

      {/* Results */}
      {result && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card overflow-hidden"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800/50">
            <div className="flex items-center gap-4 text-xs text-gray-400">
              <span>{result.row_count} rows</span>
              {result.bytes_scanned && (
                <span className="flex items-center gap-1">
                  <Database className="w-3 h-3" />
                  {(result.bytes_scanned / 1024 / 1024).toFixed(2)} MB scanned
                </span>
              )}
              {result.execution_time_ms && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {result.execution_time_ms}ms
                </span>
              )}
            </div>
            <button
              onClick={copyResults}
              className="flex items-center gap-1.5 px-3 py-1 text-xs text-gray-400 hover:text-white bg-gray-800/50 rounded-lg transition-colors"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              {copied ? 'Copied!' : 'Copy CSV'}
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-800/30">
                  {result.columns?.map((col) => (
                    <th
                      key={col}
                      className="px-4 py-2.5 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/30">
                {result.rows?.map((row, i) => (
                  <tr key={i} className="hover:bg-gray-800/20 transition-colors">
                    {result.columns?.map((col) => (
                      <td
                        key={col}
                        className="px-4 py-2 text-sm text-gray-300 font-mono"
                      >
                        {row[col] ?? '-'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}
    </div>
  );
}
