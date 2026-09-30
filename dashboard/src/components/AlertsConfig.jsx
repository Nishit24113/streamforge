import React, { useState, useEffect } from 'react';

/**
 * Alerts Configuration Dashboard
 *
 * Configure alert channels, severity thresholds, and notification preferences.
 */

const AlertsConfig = ({ pipelineId }) => {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [alertHistory, setAlertHistory] = useState([]);

  // Form state
  const [channels, setChannels] = useState([]);
  const [severityThreshold, setSeverityThreshold] = useState('warning');
  const [enabledAlertTypes, setEnabledAlertTypes] = useState([]);
  const [slackWebhook, setSlackWebhook] = useState('');
  const [emailTopicArn, setEmailTopicArn] = useState('');
  const [quietHoursEnabled, setQuietHoursEnabled] = useState(false);
  const [quietHoursStart, setQuietHoursStart] = useState('22:00');
  const [quietHoursEnd, setQuietHoursEnd] = useState('08:00');
  const [rateLimitEnabled, setRateLimitEnabled] = useState(true);
  const [maxAlerts, setMaxAlerts] = useState(10);
  const [windowMinutes, setWindowMinutes] = useState(60);

  const ALERT_TYPES = [
    { id: 'failure', label: 'Pipeline Failures', description: 'Lambda errors, timeouts, processing failures' },
    { id: 'anomaly', label: 'Data Anomalies', description: 'Unusual patterns detected by ML models' },
    { id: 'cost_spike', label: 'Cost Spikes', description: 'Unexpected increase in AWS costs' },
    { id: 'quality_issue', label: 'Data Quality Issues', description: 'Invalid data, schema violations, missing fields' }
  ];

  const CHANNELS = [
    { id: 'slack', label: 'Slack', icon: '💬', requiresConfig: 'slackWebhook' },
    { id: 'email', label: 'Email (SNS)', icon: '📧', requiresConfig: 'emailTopicArn' },
    { id: 'sns', label: 'SNS Topic', icon: '📡', requiresConfig: 'snsTopicArn' },
    { id: 'webhook', label: 'Custom Webhook', icon: '🔗', requiresConfig: 'webhookUrl' }
  ];

  useEffect(() => {
    fetchConfig();
    fetchAlertHistory();
  }, [pipelineId]);

  const fetchConfig = async () => {
    try {
      const response = await fetch(`https://api.streamforge.com/alerts/config/${pipelineId}`);
      const data = await response.json();

      if (data) {
        setConfig(data);
        setChannels(data.channels || []);
        setSeverityThreshold(data.severity_threshold || 'warning');
        setEnabledAlertTypes(data.enabled_alert_types || []);
        setSlackWebhook(data.slack_webhook_url || '');
        setEmailTopicArn(data.email_topic_arn || '');

        if (data.quiet_hours) {
          setQuietHoursEnabled(true);
          setQuietHoursStart(data.quiet_hours.start);
          setQuietHoursEnd(data.quiet_hours.end);
        }

        if (data.rate_limit) {
          setMaxAlerts(data.rate_limit.max_alerts);
          setWindowMinutes(data.rate_limit.window_minutes);
        }
      }
    } catch (error) {
      console.error('Error fetching alert config:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchAlertHistory = async () => {
    try {
      const response = await fetch(`https://api.streamforge.com/alerts/history/${pipelineId}`);
      const data = await response.json();
      setAlertHistory(data.alerts || []);
    } catch (error) {
      console.error('Error fetching alert history:', error);
    }
  };

  const handleSave = async () => {
    setSaving(true);

    const configData = {
      pipeline_id: pipelineId,
      channels,
      severity_threshold: severityThreshold,
      enabled_alert_types: enabledAlertTypes,
      slack_webhook_url: slackWebhook || null,
      email_topic_arn: emailTopicArn || null,
      quiet_hours: quietHoursEnabled ? { start: quietHoursStart, end: quietHoursEnd } : null,
      rate_limit: rateLimitEnabled ? { max_alerts: maxAlerts, window_minutes: windowMinutes } : null
    };

    try {
      const response = await fetch(`https://api.streamforge.com/alerts/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configData)
      });

      if (response.ok) {
        alert('Alert configuration saved successfully!');
        fetchConfig();
      } else {
        alert('Failed to save configuration');
      }
    } catch (error) {
      console.error('Error saving config:', error);
      alert('Error saving configuration');
    } finally {
      setSaving(false);
    }
  };

  const toggleChannel = (channelId) => {
    setChannels(prev =>
      prev.includes(channelId)
        ? prev.filter(c => c !== channelId)
        : [...prev, channelId]
    );
  };

  const toggleAlertType = (typeId) => {
    setEnabledAlertTypes(prev =>
      prev.includes(typeId)
        ? prev.filter(t => t !== typeId)
        : [...prev, typeId]
    );
  };

  if (loading) {
    return <div className="p-6 text-white">Loading alert configuration...</div>;
  }

  return (
    <div className="p-6 bg-gray-900 min-h-screen text-white">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Alerts Configuration</h1>
        <p className="text-gray-400">Configure notification channels and alert preferences for {pipelineId}</p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Configuration Panel */}
        <div className="col-span-2 space-y-6">

          {/* Alert Channels */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Notification Channels</h2>
            <div className="grid grid-cols-2 gap-4">
              {CHANNELS.map(channel => (
                <div
                  key={channel.id}
                  onClick={() => toggleChannel(channel.id)}
                  className={`p-4 border rounded-lg cursor-pointer transition ${
                    channels.includes(channel.id)
                      ? 'border-blue-500 bg-blue-900/20'
                      : 'border-gray-600 hover:border-gray-500'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-2xl">{channel.icon}</span>
                    <span className="font-semibold">{channel.label}</span>
                  </div>
                  {channels.includes(channel.id) && (
                    <div className="mt-3">
                      {channel.id === 'slack' && (
                        <input
                          type="text"
                          placeholder="Slack webhook URL"
                          value={slackWebhook}
                          onChange={(e) => setSlackWebhook(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-full px-3 py-2 bg-gray-700 rounded text-sm"
                        />
                      )}
                      {channel.id === 'email' && (
                        <input
                          type="text"
                          placeholder="SNS topic ARN"
                          value={emailTopicArn}
                          onChange={(e) => setEmailTopicArn(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-full px-3 py-2 bg-gray-700 rounded text-sm"
                        />
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Alert Types */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Alert Types</h2>
            <div className="space-y-3">
              {ALERT_TYPES.map(type => (
                <label key={type.id} className="flex items-start gap-3 p-3 bg-gray-700 rounded cursor-pointer hover:bg-gray-600">
                  <input
                    type="checkbox"
                    checked={enabledAlertTypes.includes(type.id)}
                    onChange={() => toggleAlertType(type.id)}
                    className="mt-1"
                  />
                  <div>
                    <div className="font-semibold">{type.label}</div>
                    <div className="text-sm text-gray-400">{type.description}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Severity Threshold */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">Severity Threshold</h2>
            <p className="text-sm text-gray-400 mb-4">Only send alerts at or above this severity level</p>
            <div className="flex gap-3">
              {['info', 'warning', 'error', 'critical'].map(severity => (
                <button
                  key={severity}
                  onClick={() => setSeverityThreshold(severity)}
                  className={`px-4 py-2 rounded font-medium ${
                    severityThreshold === severity
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {severity.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Quiet Hours */}
          <div className="bg-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Quiet Hours</h2>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={quietHoursEnabled}
                  onChange={(e) => setQuietHoursEnabled(e.target.checked)}
                />
                <span className="text-sm">Enable</span>
              </label>
            </div>
            {quietHoursEnabled && (
              <div className="flex items-center gap-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Start Time</label>
                  <input
                    type="time"
                    value={quietHoursStart}
                    onChange={(e) => setQuietHoursStart(e.target.value)}
                    className="px-3 py-2 bg-gray-700 rounded"
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">End Time</label>
                  <input
                    type="time"
                    value={quietHoursEnd}
                    onChange={(e) => setQuietHoursEnd(e.target.value)}
                    className="px-3 py-2 bg-gray-700 rounded"
                  />
                </div>
                <div className="text-sm text-gray-400 mt-6">
                  (Only critical alerts during quiet hours)
                </div>
              </div>
            )}
          </div>

          {/* Rate Limiting */}
          <div className="bg-gray-800 rounded-lg p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold">Rate Limiting</h2>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rateLimitEnabled}
                  onChange={(e) => setRateLimitEnabled(e.target.checked)}
                />
                <span className="text-sm">Enable</span>
              </label>
            </div>
            {rateLimitEnabled && (
              <div className="flex items-center gap-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Max Alerts</label>
                  <input
                    type="number"
                    value={maxAlerts}
                    onChange={(e) => setMaxAlerts(parseInt(e.target.value))}
                    className="px-3 py-2 bg-gray-700 rounded w-24"
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-1">Time Window (minutes)</label>
                  <input
                    type="number"
                    value={windowMinutes}
                    onChange={(e) => setWindowMinutes(parseInt(e.target.value))}
                    className="px-3 py-2 bg-gray-700 rounded w-24"
                  />
                </div>
                <div className="text-sm text-gray-400 mt-6">
                  Suppress alerts after limit is reached
                </div>
              </div>
            )}
          </div>

          {/* Save Button */}
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>

        {/* Alert History Sidebar */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Recent Alerts</h2>
          <div className="space-y-3 max-h-[800px] overflow-y-auto">
            {alertHistory.length === 0 ? (
              <div className="text-center text-gray-500 py-8">No alerts sent yet</div>
            ) : (
              alertHistory.map((alert) => (
                <AlertHistoryCard key={alert.alert_id} alert={alert} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const AlertHistoryCard = ({ alert }) => {
  const severityColors = {
    info: 'border-l-blue-500 bg-blue-900/10',
    warning: 'border-l-yellow-500 bg-yellow-900/10',
    error: 'border-l-red-500 bg-red-900/10',
    critical: 'border-l-red-700 bg-red-900/20'
  };

  const severityIcons = {
    info: 'ℹ️',
    warning: '⚠️',
    error: '❌',
    critical: '🚨'
  };

  return (
    <div className={`p-3 border-l-4 rounded ${severityColors[alert.severity]}`}>
      <div className="flex items-start gap-2 mb-1">
        <span className="text-lg">{severityIcons[alert.severity]}</span>
        <div className="flex-1">
          <div className="font-semibold text-sm">{alert.title}</div>
          <div className="text-xs text-gray-400 mt-1">
            {alert.alert_type.replace('_', ' ')} • {new Date(alert.timestamp).toLocaleString()}
          </div>
        </div>
      </div>
      <div className="text-xs text-gray-300 mt-2">{alert.message}</div>
      {alert.delivered_to && alert.delivered_to.length > 0 && (
        <div className="flex gap-1 mt-2">
          {alert.delivered_to.map(channel => (
            <span key={channel} className="px-2 py-0.5 bg-gray-700 rounded text-xs">
              {channel}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

export default AlertsConfig;
