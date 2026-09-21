import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  GitBranch, Play, Clock, CheckCircle2, XCircle, Loader2,
  ChevronDown, ChevronRight, Send, Plus,
} from 'lucide-react';
import { listPipelines, getPipelineRuns, ingestEvents } from '../utils/api';

const STATUS_STYLES = {
  ACTIVE: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', icon: CheckCircle2 },
  COMPLETED: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', icon: CheckCircle2 },
  PROCESSING: { bg: 'bg-blue-500/10', text: 'text-blue-400', icon: Loader2 },
  INGESTED: { bg: 'bg-amber-500/10', text: 'text-amber-400', icon: Clock },
  VALIDATED: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', icon: CheckCircle2 },
  TRANSFORMED: { bg: 'bg-violet-500/10', text: 'text-violet-400', icon: CheckCircle2 },
  FAILED: { bg: 'bg-red-500/10', text: 'text-red-400', icon: XCircle },
};

function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.PROCESSING;
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${style.bg} ${style.text}`}>
      <Icon className={`w-3 h-3 ${status === 'PROCESSING' ? 'animate-spin' : ''}`} />
      {status}
    </span>
  );
}

function PipelineCard({ pipeline }) {
  const [expanded, setExpanded] = useState(false);

  const { data: runsData } = useQuery({
    queryKey: ['runs', pipeline.pipeline_id],
    queryFn: () => getPipelineRuns(pipeline.pipeline_id),
    enabled: expanded,
  });

  const runs = runsData?.runs || [];

  return (
    <motion.div
      layout
      className="glass-card overflow-hidden"
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-5 hover:bg-gray-800/30 transition-colors"
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-forge-600/20">
            <GitBranch className="w-5 h-5 text-forge-400" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-white">{pipeline.name || pipeline.pipeline_id}</h3>
            <p className="text-xs text-gray-500 mt-0.5">{pipeline.pipeline_id}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <StatusBadge status={pipeline.status || 'ACTIVE'} />
          <motion.div animate={{ rotate: expanded ? 180 : 0 }}>
            <ChevronDown className="w-4 h-4 text-gray-500" />
          </motion.div>
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="border-t border-gray-800/50 px-5 py-4">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                Recent Runs
              </h4>
              {runs.length === 0 ? (
                <p className="text-sm text-gray-500">No runs yet</p>
              ) : (
                <div className="space-y-2">
                  {runs.slice(0, 8).map((run) => (
                    <div
                      key={run.run_id}
                      className="flex items-center justify-between py-2 px-3 rounded-lg bg-gray-800/30"
                    >
                      <div className="flex items-center gap-3">
                        <StatusBadge status={run.status} />
                        <span className="text-xs text-gray-500 font-mono">{run.run_id}</span>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-gray-400">
                        <span>{run.events_count || 0} events</span>
                        {run.anomaly_count > 0 && (
                          <span className="text-amber-400">{run.anomaly_count} anomalies</span>
                        )}
                        <span>
                          {new Date((run.started_at || 0) * 1000).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function SendTestData() {
  const [pipeline, setPipeline] = useState('ecommerce-events');
  const [eventCount, setEventCount] = useState(10);
  const [result, setResult] = useState(null);

  const mutation = useMutation({
    mutationFn: ({ pipeline, events }) => ingestEvents(pipeline, events),
    onSuccess: (data) => setResult(data),
  });

  const generateEvents = () => {
    const events = [];
    for (let i = 0; i < eventCount; i++) {
      if (pipeline === 'ecommerce-events') {
        events.push({
          user_id: `user-${Math.floor(Math.random() * 1000)}`,
          action: ['purchase', 'add_to_cart', 'page_view', 'signup'][Math.floor(Math.random() * 4)],
          amount: Math.round(Math.random() * 500 * 100) / 100,
          product_id: `prod-${Math.floor(Math.random() * 200)}`,
          timestamp: Date.now(),
          event_type: 'transaction',
        });
      } else if (pipeline === 'iot-sensors') {
        events.push({
          device_id: `sensor-${Math.floor(Math.random() * 50)}`,
          sensor_type: ['temperature', 'humidity', 'pressure'][Math.floor(Math.random() * 3)],
          value: Math.round((Math.random() * 60 + 10) * 100) / 100,
          location: ['floor-1', 'floor-2', 'outdoor'][Math.floor(Math.random() * 3)],
          timestamp: Date.now(),
          event_type: 'reading',
        });
      } else {
        events.push({
          page_url: ['/home', '/products', '/cart', '/checkout'][Math.floor(Math.random() * 4)],
          session_id: `sess-${Math.floor(Math.random() * 500)}`,
          session_duration: Math.floor(Math.random() * 300),
          referrer: ['google', 'direct', 'twitter', 'email'][Math.floor(Math.random() * 4)],
          device_type: ['desktop', 'mobile', 'tablet'][Math.floor(Math.random() * 3)],
          timestamp: Date.now(),
          event_type: 'page_view',
        });
      }
    }
    return events;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-6"
    >
      <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
        <Send className="w-4 h-4 text-forge-400" />
        Send Test Data
      </h3>
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <label className="text-xs text-gray-400 block mb-1.5">Pipeline</label>
          <select
            value={pipeline}
            onChange={(e) => setPipeline(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800/50 border border-gray-700 rounded-lg text-sm text-white focus:ring-2 focus:ring-forge-500 focus:border-transparent"
          >
            <option value="ecommerce-events">E-Commerce</option>
            <option value="iot-sensors">IoT Sensors</option>
            <option value="web-analytics">Web Analytics</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1.5">Event Count</label>
          <input
            type="number"
            value={eventCount}
            onChange={(e) => setEventCount(parseInt(e.target.value) || 1)}
            min={1}
            max={500}
            className="w-full px-3 py-2 bg-gray-800/50 border border-gray-700 rounded-lg text-sm text-white focus:ring-2 focus:ring-forge-500 focus:border-transparent"
          />
        </div>
        <div className="flex items-end">
          <button
            onClick={() => mutation.mutate({ pipeline, events: generateEvents() })}
            disabled={mutation.isPending}
            className="w-full px-4 py-2 bg-forge-600 hover:bg-forge-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {mutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            Send
          </button>
        </div>
      </div>

      {result && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="mt-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20"
        >
          <p className="text-xs text-emerald-400 font-mono">
            {JSON.stringify(result, null, 2)}
          </p>
        </motion.div>
      )}
    </motion.div>
  );
}

export default function PipelineMonitor() {
  const { data, isLoading } = useQuery({
    queryKey: ['pipelines'],
    queryFn: listPipelines,
  });

  const pipelines = data?.pipelines || [];

  return (
    <div className="space-y-6">
      <SendTestData />

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Pipelines ({pipelines.length})
        </h2>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 text-forge-500 animate-spin" />
        </div>
      ) : (
        <div className="space-y-3">
          {pipelines.map((pipeline) => (
            <PipelineCard key={pipeline.pipeline_id} pipeline={pipeline} />
          ))}
        </div>
      )}
    </div>
  );
}
