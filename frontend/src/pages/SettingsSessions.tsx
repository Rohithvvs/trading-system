import React, { useEffect, useState } from 'react';
import { apiUrl } from '../config';

interface Session {
  id: string;
  device_name: string;
  ip_address: string;
  last_active_at: string;
  created_at: string;
  is_current: boolean;
}

export const SettingsSessions: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchSessions = async () => {
    try {
      const response = await fetch(apiUrl('/auth/sessions'), { credentials: 'include' });
      if (!response.ok) throw new Error('Failed to fetch sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handleRevoke = async (sessionId: string) => {
    try {
      const response = await fetch(apiUrl(`/auth/sessions/${sessionId}/revoke`), {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to revoke session');
      
      // Remove from list
      setSessions(prev => prev.filter(s => s.id !== sessionId));
    } catch (err: any) {
      alert(err.message);
    }
  };

  if (loading) return <div className="p-6">Loading sessions...</div>;
  if (error) return <div className="p-6 text-red-500">{error}</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold mb-6 text-gray-900 dark:text-white">Active Sessions</h2>
      
      <div className="space-y-4">
        {sessions.map(session => (
          <div key={session.id} className="flex items-center justify-between p-4 bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700">
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="font-semibold text-gray-900 dark:text-white">{session.device_name}</h3>
                {session.is_current && (
                  <span className="px-2 py-1 text-xs bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 rounded-full">
                    Current Session
                  </span>
                )}
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                IP: {session.ip_address || 'Unknown'} • Last active: {new Date(session.last_active_at).toLocaleString()}
              </div>
            </div>
            {!session.is_current && (
              <button
                onClick={() => handleRevoke(session.id)}
                className="px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
              >
                Revoke
              </button>
            )}
          </div>
        ))}
        {sessions.length === 0 && (
          <div className="text-gray-500">No active sessions found.</div>
        )}
      </div>
    </div>
  );
};
