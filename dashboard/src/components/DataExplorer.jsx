import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  FolderTree, File, HardDrive, Layers, ArrowRight, RefreshCw,
} from 'lucide-react';

const LAKE_STRUCTURE = {
  raw: {
    'ecommerce-events': { files: 312, size: '48 MB', lastModified: '2 min ago' },
    'iot-sensors': { files: 380, size: '67 MB', lastModified: '5 min ago' },
    'web-analytics': { files: 200, size: '23 MB', lastModified: '8 min ago' },
  },
  clean: {
    'ecommerce-events': { files: 298, size: '31 MB', lastModified: '3 min ago' },
    'iot-sensors': { files: 365, size: '42 MB', lastModified: '6 min ago' },
    'web-analytics': { files: 189, size: '15 MB', lastModified: '9 min ago' },
  },
  agg: {
    'ecommerce-events': { files: 156, size: '4.2 MB', lastModified: '3 min ago' },
    'iot-sensors': { files: 192, size: '5.8 MB', lastModified: '6 min ago' },
    'web-analytics': { files: 98, size: '2.1 MB', lastModified: '9 min ago' },
  },
};

const ZONE_COLORS = {
  raw: { bg: 'bg-amber-500/10', text: 'text-amber-400', bar: '#f59e0b' },
  clean: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', bar: '#10b981' },
  agg: { bg: 'bg-forge-500/10', text: 'text-forge-400', bar: '#2e88ff' },
};

function sizeToMB(sizeStr) {
  const num = parseFloat(sizeStr);
  return num;
}

export default function DataExplorer() {
  const [selectedZone, setSelectedZone] = useState('raw');
  const [selectedPipeline, setSelectedPipeline] = useState(null);

  const zones = Object.entries(LAKE_STRUCTURE).map(([zone, pipelines]) => {
    const totalFiles = Object.values(pipelines).reduce((sum, p) => sum + p.files, 0);
    const totalSize = Object.values(pipelines).reduce(
      (sum, p) => sum + sizeToMB(p.size), 0
    ).toFixed(1);
    return { zone, totalFiles, totalSize: `${totalSize} MB`, pipelines: Object.keys(pipelines).length };
  });

  const sizeByZone = Object.entries(LAKE_STRUCTURE).map(([zone, pipelines]) => ({
    zone: zone.charAt(0).toUpperCase() + zone.slice(1),
    size: Object.values(pipelines).reduce((sum, p) => sum + sizeToMB(p.size), 0),
    files: Object.values(pipelines).reduce((sum, p) => sum + p.files, 0),
    fill: ZONE_COLORS[zone]?.bar || '#64748b',
  }));

  const container = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.06 } },
  };
  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 },
  };

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      {/* Data Lake Architecture */}
      <motion.div variants={item} className="glass-card p-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Layers className="w-4 h-4 text-forge-400" />
          Three-Zone Data Lake Architecture
        </h3>
        <div className="flex items-center justify-center gap-4">
          {zones.map((z, i) => (
            <div key={z.zone} className="flex items-center gap-4">
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setSelectedZone(z.zone)}
                className={`relative flex flex-col items-center p-6 rounded-2xl border-2 transition-all w-56 ${
                  selectedZone === z.zone
                    ? `${ZONE_COLORS[z.zone].bg} border-current ${ZONE_COLORS[z.zone].text}`
                    : 'bg-gray-800/30 border-gray-700/50 text-gray-400 hover:border-gray-600'
                }`}
              >
                <FolderTree className="w-8 h-8 mb-2" />
                <span className="text-lg font-bold capitalize">{z.zone}</span>
                <div className="mt-2 text-center">
                  <p className="text-xs opacity-70">{z.totalFiles} files</p>
                  <p className="text-xs opacity-70">{z.totalSize}</p>
                </div>
              </motion.button>
              {i < zones.length - 1 && (
                <ArrowRight className="w-5 h-5 text-gray-600 flex-shrink-0" />
              )}
            </div>
          ))}
        </div>
      </motion.div>

      {/* Zone Details + Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* File Browser */}
        <motion.div variants={item} className="glass-card overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-800/50 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-300">
              s3://streamforge-lake/<span className={ZONE_COLORS[selectedZone]?.text}>{selectedZone}</span>/
            </h3>
            <RefreshCw className="w-4 h-4 text-gray-500 cursor-pointer hover:text-gray-300 transition-colors" />
          </div>
          <div className="divide-y divide-gray-800/30">
            {Object.entries(LAKE_STRUCTURE[selectedZone] || {}).map(([pipeline, info]) => (
              <motion.button
                key={pipeline}
                whileHover={{ x: 4 }}
                onClick={() => setSelectedPipeline(
                  selectedPipeline === pipeline ? null : pipeline
                )}
                className={`w-full flex items-center justify-between px-6 py-4 transition-colors ${
                  selectedPipeline === pipeline ? 'bg-gray-800/40' : 'hover:bg-gray-800/20'
                }`}
              >
                <div className="flex items-center gap-3">
                  <FolderTree className={`w-4 h-4 ${ZONE_COLORS[selectedZone]?.text}`} />
                  <div className="text-left">
                    <p className="text-sm font-medium text-white">{pipeline}/</p>
                    <p className="text-xs text-gray-500">Partitioned by year/month/day</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-300">{info.files} files</p>
                  <p className="text-xs text-gray-500">{info.size} / {info.lastModified}</p>
                </div>
              </motion.button>
            ))}
          </div>

          {selectedPipeline && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="px-6 py-4 bg-gray-800/20 border-t border-gray-800/50"
            >
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                Sample Partitions
              </h4>
              <div className="space-y-1.5 font-mono text-xs text-gray-400">
                <div className="flex items-center gap-2">
                  <FolderTree className="w-3 h-3" />
                  <span>year=2026/month=09/day=18/</span>
                  <span className="text-gray-600">12 files, 2.3 MB</span>
                </div>
                <div className="flex items-center gap-2">
                  <FolderTree className="w-3 h-3" />
                  <span>year=2026/month=09/day=17/</span>
                  <span className="text-gray-600">15 files, 3.1 MB</span>
                </div>
                <div className="flex items-center gap-2 pl-6">
                  <File className="w-3 h-3 text-forge-400" />
                  <span className="text-forge-400">run-a1b2c3d4e5f6.parquet</span>
                  <span className="text-gray-600">256 KB, Snappy</span>
                </div>
                <div className="flex items-center gap-2 pl-6">
                  <File className="w-3 h-3 text-forge-400" />
                  <span className="text-forge-400">run-f6e5d4c3b2a1.parquet</span>
                  <span className="text-gray-600">189 KB, Snappy</span>
                </div>
              </div>
            </motion.div>
          )}
        </motion.div>

        {/* Storage Chart */}
        <motion.div variants={item} className="glass-card p-6">
          <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-forge-400" />
            Storage by Zone
          </h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={sizeByZone}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="zone" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={11} unit=" MB" />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '12px',
                  fontSize: '12px',
                }}
                formatter={(value) => [`${value} MB`, 'Size']}
              />
              <Bar dataKey="size" radius={[8, 8, 0, 0]}>
                {sizeByZone.map((entry) => (
                  <motion.rect key={entry.zone} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {/* Data format info */}
          <div className="mt-6 p-4 rounded-xl bg-gray-800/30">
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Data Format
            </h4>
            <div className="grid grid-cols-2 gap-3 text-xs text-gray-400">
              <div>
                <p className="text-white font-medium">Apache Parquet</p>
                <p>Columnar storage format</p>
              </div>
              <div>
                <p className="text-white font-medium">Snappy Compression</p>
                <p>~90% size reduction</p>
              </div>
              <div>
                <p className="text-white font-medium">Date Partitioned</p>
                <p>year/month/day for query efficiency</p>
              </div>
              <div>
                <p className="text-white font-medium">Glue Catalog</p>
                <p>Auto schema discovery</p>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
