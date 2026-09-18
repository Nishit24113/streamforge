import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  GitBranch,
  Search,
  AlertTriangle,
  Database,
  Activity,
  Zap,
  ChevronLeft,
  ChevronRight,
  CircleDot,
} from 'lucide-react';
import { checkHealth, getStats } from './utils/api';
import PipelineMonitor from './components/PipelineMonitor';
import DataExplorer from './components/DataExplorer';
import QueryEditor from './components/QueryEditor';
import AnomalyTimeline from './components/AnomalyTimeline';
import Overview from './components/Overview';

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'pipelines', label: 'Pipelines', icon: GitBranch },
  { id: 'anomalies', label: 'Anomalies', icon: AlertTriangle },
  { id: 'explorer', label: 'Data Explorer', icon: Database },
  { id: 'query', label: 'SQL Query', icon: Search },
];

export default function App() {
  const [activeView, setActiveView] = useState('overview');
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: checkHealth,
    refetchInterval: 30000,
  });

  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    refetchInterval: 15000,
  });

  const isHealthy = health?.status === 'healthy' || health?.status === 'local';

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Sidebar */}
      <motion.aside
        animate={{ width: sidebarOpen ? 240 : 72 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="relative flex flex-col bg-gray-900/80 border-r border-gray-800/50 backdrop-blur-xl z-10"
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 h-16 border-b border-gray-800/50">
          <motion.div
            whileHover={{ rotate: 180 }}
            transition={{ duration: 0.5 }}
            className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-forge-500 to-blue-600"
          >
            <Zap className="w-5 h-5 text-white" />
          </motion.div>
          <AnimatePresence>
            {sidebarOpen && (
              <motion.span
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                className="text-lg font-bold bg-gradient-to-r from-forge-400 to-blue-400 bg-clip-text text-transparent"
              >
                StreamForge
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeView === item.id;
            return (
              <motion.button
                key={item.id}
                whileHover={{ x: 4 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setActiveView(item.id)}
                className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-xl transition-all ${
                  isActive
                    ? 'bg-forge-600/20 text-forge-400'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                }`}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <AnimatePresence>
                  {sidebarOpen && (
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="text-sm font-medium whitespace-nowrap"
                    >
                      {item.label}
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>
            );
          })}
        </nav>

        {/* Status */}
        <div className="px-3 pb-4">
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${
            isHealthy ? 'bg-emerald-500/10' : 'bg-red-500/10'
          }`}>
            <CircleDot className={`w-4 h-4 ${isHealthy ? 'text-emerald-400' : 'text-red-400'}`} />
            <AnimatePresence>
              {sidebarOpen && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className={`text-xs font-medium ${isHealthy ? 'text-emerald-400' : 'text-red-400'}`}
                >
                  {isHealthy ? 'System Healthy' : 'Disconnected'}
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Toggle */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="absolute -right-3 top-20 w-6 h-6 bg-gray-800 border border-gray-700 rounded-full flex items-center justify-center hover:bg-gray-700 transition-colors"
        >
          {sidebarOpen ? <ChevronLeft className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </button>
      </motion.aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        {/* Header */}
        <header className="sticky top-0 z-10 flex items-center justify-between px-8 h-16 bg-gray-950/80 backdrop-blur-xl border-b border-gray-800/50">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-white">
              {NAV_ITEMS.find(n => n.id === activeView)?.label}
            </h1>
            {stats && (
              <span className="px-2 py-0.5 text-xs font-medium bg-forge-600/20 text-forge-400 rounded-full">
                {(stats.total_events || 0).toLocaleString()} events
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <Activity className="w-4 h-4" />
              <span>{stats?.active_pipelines || 0} active pipelines</span>
            </div>
            {stats?.total_anomalies > 0 && (
              <div className="flex items-center gap-2 text-sm text-amber-400">
                <AlertTriangle className="w-4 h-4" />
                <span>{stats.total_anomalies.toLocaleString()} anomalies</span>
              </div>
            )}
          </div>
        </header>

        {/* Content */}
        <div className="p-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeView}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              {activeView === 'overview' && <Overview stats={stats} />}
              {activeView === 'pipelines' && <PipelineMonitor />}
              {activeView === 'anomalies' && <AnomalyTimeline />}
              {activeView === 'explorer' && <DataExplorer />}
              {activeView === 'query' && <QueryEditor />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
